"""run_review executes the LangGraph pipeline, including the approval branch."""

import asyncio
from types import SimpleNamespace

from app.services.github_service import PRDiff
from app.services.review_service import ReviewService


class _GitHubStub:
    def __init__(self) -> None:
        self.posted: list[tuple[str, int]] = []

    def fetch_pr_diff(self, repo_name: str, pr_number: int) -> PRDiff:
        return PRDiff(
            repo=repo_name,
            pr_number=pr_number,
            pr_title="Graph test",
            pr_url=f"https://github.com/{repo_name}/pull/{pr_number}",
            author="owner",
            base_branch="main",
            head_branch="feature",
            files_changed=[],
            diff_text="",
        )

    def post_review_comment(self, repo_name: str, pr_number: int, markdown: str) -> str:
        self.posted.append((repo_name, pr_number))
        return "https://github.com/comment/1"


class _LLMStub:
    async def generate_review(self, prompt: str) -> str:
        return "{}"

    async def parse_review_response(self, raw: str) -> dict:
        return {
            "bugs": [],
            "security": [],
            "performance": [],
            "code_quality": [],
            "suggested_fixes": [],
            "scores": {"quality": 8, "security": 8, "performance": 8},
            "final_verdict": "APPROVE",
            "summary": "",
        }


class _DBStub:
    def __init__(self) -> None:
        self.saved = 0
        self.approvals: list[str] = []

    async def save_review(self, review) -> str:
        self.saved += 1
        return "review-1"

    async def update_review_approval(self, review_id: str, approved_by: str, posted: bool) -> None:
        self.approvals.append(approved_by)


def _service(require_approval: bool) -> ReviewService:
    service = ReviewService.__new__(ReviewService)
    service._settings = SimpleNamespace(
        llm_timeout_seconds=5,
        llm_provider="claude",
        require_human_approval=require_approval,
    )
    service._github = _GitHubStub()
    service._llm = _LLMStub()
    service._db = _DBStub()
    return service


def test_graph_posts_when_auto_posting_is_allowed():
    service = _service(require_approval=False)
    review, review_id = asyncio.run(service.run_review("owner/repo", 7))
    assert review_id == "review-1"
    assert review.posted_to_github is True
    assert service._github.posted == [("owner/repo", 7)]
    assert service._db.approvals == ["auto"]


def test_graph_holds_review_when_approval_is_required():
    service = _service(require_approval=True)
    review, _ = asyncio.run(service.run_review("owner/repo", 7))
    assert review.posted_to_github is False
    assert service._github.posted == []
    assert service._db.saved == 1


def test_graph_skips_posting_when_caller_opts_out():
    service = _service(require_approval=False)
    review, _ = asyncio.run(service.run_review("owner/repo", 7, post_comment=False))
    assert service._github.posted == []
    assert review.posted_to_github is False
