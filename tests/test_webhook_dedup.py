"""A pull request's head commit is reviewed once, however many times GitHub delivers it."""

import asyncio
import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.api.routes import webhook as webhook_route
from app.config import get_settings
from app.main import app
from app.services.db_service import DatabaseService

SECRET = "test-webhook-secret"
client = TestClient(app)


class _ServiceStub:
    """Stands in for ReviewService: an in-memory claim store and a counting review."""

    def __init__(self, fail_reviews: bool = False, claims_down: bool = False) -> None:
        self.claims: set[str] = set()
        self.reviews: list[tuple[str, int]] = []
        self.fail_reviews = fail_reviews
        self.claims_down = claims_down

    async def claim_webhook_review(self, key: str) -> bool:
        if self.claims_down:
            raise ConnectionError("MongoDB unavailable")
        if key in self.claims:
            return False
        self.claims.add(key)
        return True

    async def release_webhook_review(self, key: str) -> None:
        self.claims.discard(key)

    async def run_review(self, repo_name: str, pr_number: int, post_comment: bool = True):
        self.reviews.append((repo_name, pr_number))
        if self.fail_reviews:
            raise RuntimeError("LLM timed out")
        verdict = type("Verdict", (), {"value": "APPROVE"})()
        return type("Review", (), {"final_verdict": verdict})(), "review-1"


def _deliver(sha: str, action: str = "synchronize"):
    payload = json.dumps(
        {
            "action": action,
            "number": 7,
            "pull_request": {
                "number": 7,
                "title": "Fix token check",
                "html_url": "https://github.com/owner/repo/pull/7",
                "state": "open",
                "user": {"login": "owner", "id": 1},
                "head": {"sha": sha, "ref": "fix"},
                "base": {"sha": "base", "ref": "main"},
            },
            "repository": {
                "id": 1,
                "name": "repo",
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            },
            "sender": {"login": "owner", "id": 1},
        }
    ).encode()
    signature = "sha256=" + hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook/github",
        content=payload,
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": signature},
    )


def _use(monkeypatch, service: _ServiceStub) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    monkeypatch.setattr(webhook_route, "get_review_service", lambda: service)


def test_redelivery_of_the_same_commit_does_not_start_a_second_review(monkeypatch):
    service = _ServiceStub()
    _use(monkeypatch, service)

    first = _deliver("abc123")
    again = _deliver("abc123")

    assert first.json()["status"] == "accepted"
    assert again.json() == {"status": "duplicate", "repo": "owner/repo", "pr_number": 7, "head_sha": "abc123"}
    assert service.reviews == [("owner/repo", 7)]


def test_reopening_at_a_reviewed_commit_is_a_duplicate(monkeypatch):
    service = _ServiceStub()
    _use(monkeypatch, service)

    _deliver("abc123", action="opened")
    reopened = _deliver("abc123", action="reopened")

    assert reopened.json()["status"] == "duplicate"
    assert len(service.reviews) == 1


def test_a_new_push_is_reviewed(monkeypatch):
    service = _ServiceStub()
    _use(monkeypatch, service)

    _deliver("abc123")
    pushed = _deliver("def456")

    assert pushed.json()["status"] == "accepted"
    assert len(service.reviews) == 2


def test_a_failed_review_releases_its_claim_so_a_redelivery_can_retry(monkeypatch):
    service = _ServiceStub(fail_reviews=True)
    _use(monkeypatch, service)

    _deliver("abc123")
    assert service.claims == set()

    retry = _deliver("abc123")
    assert retry.json()["status"] == "accepted"
    assert len(service.reviews) == 2


def test_reviews_still_run_when_the_claim_store_is_down(monkeypatch):
    service = _ServiceStub(claims_down=True)
    _use(monkeypatch, service)

    response = _deliver("abc123")

    assert response.json()["status"] == "accepted"
    assert service.reviews == [("owner/repo", 7)]


class _ClaimsCollection:
    """Mimics MongoDB's unique _id: a second insert of the same key fails."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    async def create_index(self, field, **options):
        self.indexes.append((field, options))

    async def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("duplicate key")
        self.docs[doc["_id"]] = doc

    async def delete_one(self, query):
        self.docs.pop(query["_id"], None)


def test_database_claims_are_unique_and_expire():
    collection = _ClaimsCollection()
    db = DatabaseService.__new__(DatabaseService)
    db._db = {"review_claims": collection}
    db._claims_indexed = False

    async def scenario():
        first = await db.claim_review("owner/repo#7@abc123")
        second = await db.claim_review("owner/repo#7@abc123")
        await db.release_review_claim("owner/repo#7@abc123")
        after_release = await db.claim_review("owner/repo#7@abc123")
        return first, second, after_release

    assert asyncio.run(scenario()) == (True, False, True)
    assert collection.indexes == [("created_at", {"expireAfterSeconds": 30 * 24 * 3600})]
