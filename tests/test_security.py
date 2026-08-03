import hashlib
import hmac

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.llm.nvidia_client import NvidiaClient
from app.services.review_service import _build_llm_client
from app.services.github_service import GitHubService


client = TestClient(app)


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_manual_review_endpoint_requires_api_token(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-api-token")
    _reset_settings()

    response = client.post(
        "/review",
        json={"repo_name": "owner/repo", "pr_number": 42, "post_comment": False},
    )

    assert response.status_code == 401


def test_webhook_rejects_missing_signature(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    _reset_settings()

    response = client.post(
        "/webhook/github",
        content=b"{}",
        headers={"X-GitHub-Event": "ping"},
    )

    assert response.status_code == 401


def test_webhook_rejects_signature_when_secret_is_missing(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    _reset_settings()

    assert not GitHubService.verify_webhook_signature(b"{}", "sha256=invalid")


def test_webhook_accepts_valid_signature_before_filtering_event(monkeypatch):
    secret = "test-webhook-secret"
    payload = b"{}"
    signature = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    _reset_settings()

    response = client.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_nvidia_provider_builds_openai_compatible_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key")
    _reset_settings()

    assert isinstance(_build_llm_client(), NvidiaClient)
