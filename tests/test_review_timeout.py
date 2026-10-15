import asyncio
from types import SimpleNamespace

import pytest

from app.services.github_service import PRDiff
from app.services.review_service import ReviewService


class _GitHubStub:
    def fetch_pr_diff(self, repo_name: str, pr_number: int) -> PRDiff:
        return PRDiff(
            repo=repo_name,
            pr_number=pr_number,
            pr_title="Timeout test",
            pr_url=f"https://github.com/{repo_name}/pull/{pr_number}",
            author="owner",
            base_branch="main",
            head_branch="test",
            files_changed=[],
            diff_text="",
        )


class _SlowLLMStub:
    async def generate_review(self, prompt: str) -> str:
        await asyncio.sleep(0.05)
        return "{}"


def test_review_service_enforces_provider_timeout():
    service = ReviewService.__new__(ReviewService)
    service._settings = SimpleNamespace(llm_timeout_seconds=0.01)
    service._github = _GitHubStub()
    service._llm = _SlowLLMStub()

    with pytest.raises(TimeoutError, match="LLM provider timed out after"):
        asyncio.run(service.run_review("owner/repo", 1, post_comment=False))
