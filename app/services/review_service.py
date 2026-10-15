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
        # The pipeline runs as a LangGraph StateGraph (see app/agents/review_agent.py):
        # fetch diff → LLM review → parse → ground → persist → post or hold for approval.
        from app.agents.review_agent import build_review_graph

        graph = getattr(self, "_graph", None)
        if graph is None:
            graph = build_review_graph(self)
            self._graph = graph

        final = await graph.ainvoke(
            {
                "repo": repo_name,
                "pr_number": pr_number,
                "post_comment": post_comment,
                "logs": [],
            }
        )
        logger.debug("Review graph steps: {}", " → ".join(final.get("logs", [])))
        return final["review"], final["review_id"]

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
