"""GitHub integration service using PyGithub."""

import hashlib
import hmac
from dataclasses import dataclass

from github import Github, GithubException
from loguru import logger

from app.config import get_settings


@dataclass
class PRDiff:
    """Aggregated data extracted from a pull request."""

    repo: str
    pr_number: int
    pr_title: str
    pr_url: str
    author: str
    base_branch: str
    head_branch: str
    files_changed: list[dict]
    diff_text: str


class GitHubService:
    """Wraps PyGithub to fetch PR data and post review comments."""

    def __init__(self) -> None:
        settings = get_settings()
        self._gh = Github(settings.github_token)
        self._max_diff_chars = settings.max_diff_chars

    def fetch_pr_diff(self, repo_name: str, pr_number: int) -> PRDiff:
        """
        Fetch all file changes for a pull request and build a unified diff string.

        Args:
            repo_name: Full repository name, e.g. ``owner/repo``.
            pr_number: Pull request number.

        Returns:
            A :class:`PRDiff` containing metadata and the unified diff text.
        """
        logger.info(f"Fetching PR #{pr_number} from {repo_name}")
        try:
            repo = self._gh.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
        except GithubException as exc:
            logger.error(f"GitHub API error: {exc}")
            raise

        files_changed = []
        diff_parts: list[str] = []

        for f in pr.get_files():
            entry = {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "changes": f.changes,
                "patch": f.patch or "",
            }
            files_changed.append(entry)
            if f.patch:
                diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch}")

        diff_text = "\n\n".join(diff_parts)
        if len(diff_text) > self._max_diff_chars:
            logger.warning(
                f"Diff truncated from {len(diff_text)} to {self._max_diff_chars} chars"
            )
            diff_text = diff_text[: self._max_diff_chars] + "\n\n[... diff truncated ...]"

        return PRDiff(
            repo=repo_name,
            pr_number=pr_number,
            pr_title=pr.title,
            pr_url=pr.html_url,
            author=pr.user.login,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            files_changed=files_changed,
            diff_text=diff_text,
        )

    def post_review_comment(self, repo_name: str, pr_number: int, body: str) -> str:
        """
        Post a markdown comment on a pull request.

        Returns the URL of the created comment.
        """
        logger.info(f"Posting review comment on {repo_name}#{pr_number}")
        try:
            repo = self._gh.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            comment = pr.create_issue_comment(body)
            logger.info(f"Comment posted: {comment.html_url}")
            return comment.html_url
        except GithubException as exc:
            logger.error(f"Failed to post comment: {exc}")
            raise

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """
        Validate a GitHub webhook HMAC-SHA256 signature.

        Args:
            payload: Raw request body bytes.
            signature: Value of the ``X-Hub-Signature-256`` header.

        Returns:
            ``True`` if the signature is valid, ``False`` otherwise.
        """
        secret = get_settings().github_webhook_secret
        if not secret:
            logger.error("GITHUB_WEBHOOK_SECRET is not configured")
            return False

        expected = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
