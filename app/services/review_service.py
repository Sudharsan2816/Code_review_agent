"""Core orchestration service that ties GitHub, LLM, and DB together."""

from loguru import logger

from app.config import get_settings
from app.models.review import CodeReview
from app.services.db_service import DatabaseService
from app.services.github_service import GitHubService, PRDiff
from app.services.llm.base import BaseLLMClient
from app.services.llm.claude_client import ClaudeClient
from app.services.llm.nvidia_client import NvidiaClient
from app.services.llm.openai_client import OpenAIClient
from app.services.review_grounding import ground_review_data
from app.utils.markdown import review_to_markdown


def _build_llm_client() -> BaseLLMClient:
    """Factory that returns the configured LLM client."""
    provider = get_settings().llm_provider
    if provider == "openai":
        return OpenAIClient()
    if provider == "nvidia":
        return NvidiaClient()
    return ClaudeClient()


def _build_prompt(pr_diff: PRDiff) -> str:
    """Construct the review prompt from PR metadata and the unified diff."""
    file_list = "\n".join(
        f"  - {f['filename']} (+{f['additions']}/-{f['deletions']})"
        for f in pr_diff.files_changed
    )
    return (
        f"Review the following pull request:\n\n"
        f"Repository : {pr_diff.repo}\n"
        f"PR #       : {pr_diff.pr_number}\n"
        f"Title      : {pr_diff.pr_title}\n"
        f"Author     : {pr_diff.author}\n"
        f"Base branch: {pr_diff.base_branch}\n"
        f"Head branch: {pr_diff.head_branch}\n\n"
        f"Allowed changed files (findings must use one of these exact paths):\n"
        f"{file_list}\n\n"
        f"Unified diff:\n```diff\n{pr_diff.diff_text}\n```\n\n"
        "Analyse only added/deleted lines in this diff. For every finding, copy one "
        "exact changed line into the evidence field. Do not report issues in files or "
        "code that are merely mentioned by documentation. For documentation or "
        "repository-metadata files, report only defects in that documentation or "
        "metadata under code_quality with low/medium severity. Text describing an "
        "application risk is not evidence that the risk exists. Produce the JSON review."
    )


class ReviewService:
    """Orchestrates the end-to-end code review pipeline."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._github = GitHubService()
        self._llm = _build_llm_client()
        self._db = DatabaseService()

    async def run_review(
        self,
        repo_name: str,
        pr_number: int,
        post_comment: bool = True,
    ) -> tuple[CodeReview, str]:
        """
        Execute a full code review for the given PR.

        Returns:
            A tuple of ``(CodeReview, review_id)``.  When
            ``require_human_approval`` is ``True`` the comment is NOT posted
            automatically; the caller must call :meth:`approve_and_post`.
        """
        # 1. Fetch diff
        pr_diff = self._github.fetch_pr_diff(repo_name, pr_number)

        # 2. Build prompt and call LLM
        prompt = _build_prompt(pr_diff)
        raw = await self._llm.generate_review(prompt)

        # 3. Parse structured response
        data = await self._llm.parse_review_response(raw)
        grounded = ground_review_data(data, pr_diff)
        review = CodeReview(
            repo=repo_name,
            pr_number=pr_number,
            pr_title=pr_diff.pr_title,
            pr_url=pr_diff.pr_url,
            llm_provider=self._settings.llm_provider,
            bugs=grounded.bugs,
            security=grounded.security,
            performance=grounded.performance,
            code_quality=grounded.code_quality,
            suggested_fixes=grounded.suggested_fixes,
            scores=grounded.scores,
            final_verdict=grounded.final_verdict,
            summary=grounded.summary,
        )

        # 4. Persist to MongoDB
        review_id = await self._db.save_review(review)

        # 5. Post to GitHub unless human approval is required
        if post_comment and not self._settings.require_human_approval:
            markdown = review_to_markdown(review)
            self._github.post_review_comment(repo_name, pr_number, markdown)
            review.posted_to_github = True
            await self._db.update_review_approval(review_id, "auto", posted=True)

        return review, review_id

    async def approve_and_post(self, review_id: str, approved_by: str) -> str:
        """
        Retrieve a pending review, post it to GitHub, and mark it approved.

        Returns the GitHub comment URL.
        """
        doc = await self._db.get_review(review_id)
        if not doc:
            raise ValueError(f"Review {review_id} not found")

        review = CodeReview(**{k: v for k, v in doc.items() if k != "_id"})
        markdown = review_to_markdown(review)
        comment_url = self._github.post_review_comment(
            review.repo, review.pr_number, markdown
        )
        await self._db.update_review_approval(review_id, approved_by, posted=True)
        return comment_url

    async def get_review(self, review_id: str) -> dict | None:
        """Return a review document by id."""
        return await self._db.get_review(review_id)

    async def list_reviews(
        self,
        repo: str | None = None,
        limit: int = 20,
        skip: int = 0,
    ) -> list[dict]:
        """Return paginated review history."""
        return await self._db.list_reviews(repo=repo, limit=limit, skip=skip)
