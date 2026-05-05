"""
LangGraph-compatible review agent.

Implements the review pipeline as a StateGraph so additional agents
(security scanner, test generator, etc.) can be composed later.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger

from app.config import get_settings
from app.models.review import CodeReview, FindingItem, Scores, SuggestedFix, Verdict
from app.services.github_service import GitHubService, PRDiff
from app.services.llm.base import BaseLLMClient
from app.services.llm.claude_client import ClaudeClient
from app.services.llm.openai_client import OpenAIClient
from app.services.review_service import _build_prompt, _parse_findings
from app.utils.markdown import review_to_markdown


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """Shared mutable state passed between graph nodes."""

    repo: str
    pr_number: int
    post_comment: bool
    pr_diff: PRDiff | None
    raw_llm_response: str
    parsed_data: dict[str, Any]
    review: CodeReview | None
    review_id: str
    error: str
    # Accumulate log messages across nodes
    logs: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


def _get_llm_client() -> BaseLLMClient:
    provider = get_settings().llm_provider
    return OpenAIClient() if provider == "openai" else ClaudeClient()


async def fetch_diff_node(state: AgentState) -> dict:
    """Node: fetch PR diff from GitHub."""
    logger.info("Agent node: fetch_diff")
    try:
        github = GitHubService()
        pr_diff = github.fetch_pr_diff(state["repo"], state["pr_number"])
        return {"pr_diff": pr_diff, "logs": [f"Fetched diff for PR #{state['pr_number']}"]}
    except Exception as exc:
        return {"error": str(exc), "logs": [f"fetch_diff failed: {exc}"]}


async def llm_review_node(state: AgentState) -> dict:
    """Node: send diff to LLM and collect raw response."""
    logger.info("Agent node: llm_review")
    if state.get("error"):
        return {}
    try:
        llm = _get_llm_client()
        prompt = _build_prompt(state["pr_diff"])
        raw = await llm.generate_review(prompt)
        return {"raw_llm_response": raw, "logs": ["LLM review generated"]}
    except Exception as exc:
        return {"error": str(exc), "logs": [f"llm_review failed: {exc}"]}


async def parse_response_node(state: AgentState) -> dict:
    """Node: parse LLM JSON response into structured data."""
    logger.info("Agent node: parse_response")
    if state.get("error"):
        return {}
    try:
        llm = _get_llm_client()
        data = await llm.parse_review_response(state["raw_llm_response"])
        return {"parsed_data": data, "logs": ["LLM response parsed"]}
    except Exception as exc:
        return {"error": str(exc), "logs": [f"parse_response failed: {exc}"]}


async def build_review_node(state: AgentState) -> dict:
    """Node: assemble CodeReview model from parsed data."""
    logger.info("Agent node: build_review")
    if state.get("error"):
        return {}
    data = state["parsed_data"]
    pr_diff = state["pr_diff"]
    scores_raw = data.get("scores", {})
    review = CodeReview(
        repo=state["repo"],
        pr_number=state["pr_number"],
        pr_title=pr_diff.pr_title,
        pr_url=pr_diff.pr_url,
        llm_provider=get_settings().llm_provider,
        bugs=_parse_findings(data.get("bugs", []), FindingItem),
        security=_parse_findings(data.get("security", []), FindingItem),
        performance=_parse_findings(data.get("performance", []), FindingItem),
        code_quality=_parse_findings(data.get("code_quality", []), FindingItem),
        suggested_fixes=_parse_findings(data.get("suggested_fixes", []), SuggestedFix),
        scores=Scores(
            quality=max(1, min(10, int(scores_raw.get("quality", 5)))),
            security=max(1, min(10, int(scores_raw.get("security", 5)))),
            performance=max(1, min(10, int(scores_raw.get("performance", 5)))),
        ),
        final_verdict=Verdict(data.get("final_verdict", "COMMENT")),
        summary=data.get("summary", ""),
    )
    return {"review": review, "logs": ["CodeReview model built"]}


async def persist_review_node(state: AgentState) -> dict:
    """Node: save review to MongoDB."""
    logger.info("Agent node: persist_review")
    if state.get("error") or not state.get("review"):
        return {}
    from app.services.db_service import DatabaseService

    db = DatabaseService()
    review_id = await db.save_review(state["review"])
    return {"review_id": review_id, "logs": [f"Review persisted id={review_id}"]}


async def post_comment_node(state: AgentState) -> dict:
    """Node: post markdown review to GitHub (if enabled and auto-approval)."""
    logger.info("Agent node: post_comment")
    settings = get_settings()
    if (
        state.get("error")
        or not state.get("review")
        or not state.get("post_comment", True)
        or settings.require_human_approval
    ):
        return {}
    try:
        github = GitHubService()
        markdown = review_to_markdown(state["review"])
        github.post_review_comment(state["repo"], state["pr_number"], markdown)
        return {"logs": ["Review comment posted to GitHub"]}
    except Exception as exc:
        return {"logs": [f"post_comment failed (non-fatal): {exc}"]}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def _should_continue(state: AgentState) -> str:
    """Conditional edge: abort the pipeline on any error."""
    return END if state.get("error") else "continue"


def build_review_graph() -> StateGraph:
    """
    Construct and compile the review StateGraph.

    The linear pipeline is::

        fetch_diff → llm_review → parse_response → build_review → persist → post_comment → END

    Each node short-circuits on ``state["error"]``.
    """
    graph = StateGraph(AgentState)

    graph.add_node("fetch_diff", fetch_diff_node)
    graph.add_node("llm_review", llm_review_node)
    graph.add_node("parse_response", parse_response_node)
    graph.add_node("build_review", build_review_node)
    graph.add_node("persist_review", persist_review_node)
    graph.add_node("post_comment", post_comment_node)

    graph.set_entry_point("fetch_diff")
    graph.add_edge("fetch_diff", "llm_review")
    graph.add_edge("llm_review", "parse_response")
    graph.add_edge("parse_response", "build_review")
    graph.add_edge("build_review", "persist_review")
    graph.add_edge("persist_review", "post_comment")
    graph.add_edge("post_comment", END)

    return graph.compile()


# Singleton compiled graph
review_graph = build_review_graph()
