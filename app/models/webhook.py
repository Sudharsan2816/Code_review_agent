"""Pydantic models for GitHub webhook payloads."""

from typing import Any, Optional

from pydantic import BaseModel


class GitHubUser(BaseModel):
    login: str
    id: int


class GitHubRepo(BaseModel):
    id: int
    name: str
    full_name: str
    html_url: str


class GitHubPullRequest(BaseModel):
    number: int
    title: str
    html_url: str
    state: str
    user: GitHubUser
    body: Optional[str] = None
    head: dict[str, Any]
    base: dict[str, Any]


class PullRequestEvent(BaseModel):
    """GitHub pull_request webhook payload (partial)."""

    action: str
    number: int
    pull_request: GitHubPullRequest
    repository: GitHubRepo
    sender: GitHubUser
