"""
LangGraph review pipeline.

``ReviewService.run_review`` executes this graph, so every review runs through it::

    fetch_diff → llm_review → parse_response → build_review → persist_review
        ├─ (auto-post allowed)    → post_comment → END
        └─ (approval required)    → END   (posted later via approve_and_post)

Nodes delegate to the ReviewService's GitHub, LLM and database clients, so the graph
and the service share one implementation. Exceptions propagate to the caller instead of
being swallowed in state, which keeps webhook and API error handling unchanged.
"""

from __future__ import annotations

import asyncio
import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger

from app.models.review import CodeReview
from app.services.github_service import PRDiff
from app.services.review_grounding import ground_review_data
from app.utils.markdown import review_to_markdown

if TYPE_CHECKING:  # pragma: no cover
    from app.services.review_service import ReviewService


class AgentState(TypedDict, total=False):
    """State passed between graph nodes."""

    repo: str
    pr_number: int
    post_comment: bool
    pr_diff: PRDiff
    raw_llm_response: str
    parsed_data: dict[str, Any]
    review: CodeReview
    review_id: str
    logs: Annotated[list[str], operator.add]


def build_review_graph(service: "ReviewService"):
    """Compile the review graph bound to one ReviewService's clients."""
    # Imported here to avoid a circular import with review_service.
    from app.services.review_service import _build_prompt

    async def fetch_diff(state: AgentState) -> dict:
        pr_diff = service._github.fetch_pr_diff(state["repo"], state["pr_number"])
        return {"pr_diff": pr_diff, "logs": [f"fetched diff for PR #{state['pr_number']}"]}

    async def llm_review(state: AgentState) -> dict:
        prompt = _build_prompt(state["pr_diff"])
        timeout = service._settings.llm_timeout_seconds
        try:
            async with asyncio.timeout(timeout):
                raw = await service._llm.generate_review(prompt)
        except TimeoutError as exc:
            logger.error("LLM provider timed out after {} seconds", timeout)
            raise TimeoutError(f"LLM provider timed out after {timeout:g} seconds") from exc
        return {"raw_llm_response": raw, "logs": ["llm review generated"]}

    async def parse_response(state: AgentState) -> dict:
        data = await service._llm.parse_review_response(state["raw_llm_response"])
        return {"parsed_data": data, "logs": ["llm response parsed"]}

    async def build_review(state: AgentState) -> dict:
        pr_diff = state["pr_diff"]
        grounded = ground_review_data(state["parsed_data"], pr_diff)
        review = CodeReview(
            repo=state["repo"],
            pr_number=state["pr_number"],
            pr_title=pr_diff.pr_title,
            pr_url=pr_diff.pr_url,
            llm_provider=service._settings.llm_provider,
            bugs=grounded.bugs,
            security=grounded.security,
            performance=grounded.performance,
            code_quality=grounded.code_quality,
            suggested_fixes=grounded.suggested_fixes,
            scores=grounded.scores,
            final_verdict=grounded.final_verdict,
            summary=grounded.summary,
        )
        return {"review": review, "logs": ["review grounded against the diff"]}

    async def persist_review(state: AgentState) -> dict:
        review_id = await service._db.save_review(state["review"])
        return {"review_id": review_id, "logs": [f"review persisted id={review_id}"]}

    def route_after_persist(state: AgentState) -> str:
        if state.get("post_comment", True) and not service._settings.require_human_approval:
            return "post_comment"
        return END

    async def post_comment(state: AgentState) -> dict:
        review = state["review"]
        markdown = review_to_markdown(review)
        service._github.post_review_comment(state["repo"], state["pr_number"], markdown)
        review.posted_to_github = True
        await service._db.update_review_approval(state["review_id"], "auto", posted=True)
        return {"review": review, "logs": ["review comment posted to GitHub"]}

    graph = StateGraph(AgentState)
    graph.add_node("fetch_diff", fetch_diff)
    graph.add_node("llm_review", llm_review)
    graph.add_node("parse_response", parse_response)
    graph.add_node("build_review", build_review)
    graph.add_node("persist_review", persist_review)
    graph.add_node("post_comment", post_comment)

    graph.set_entry_point("fetch_diff")
    graph.add_edge("fetch_diff", "llm_review")
    graph.add_edge("llm_review", "parse_response")
    graph.add_edge("parse_response", "build_review")
    graph.add_edge("build_review", "persist_review")
    graph.add_conditional_edges(
        "persist_review", route_after_persist, {"post_comment": "post_comment", END: END}
    )
    graph.add_edge("post_comment", END)
    return graph.compile()
