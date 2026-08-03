"""REST endpoints for triggering and managing code reviews."""

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.dependencies import get_review_service
from app.models.review import ApprovalRequest, ReviewRequest
from app.security import require_api_token
from app.services.review_service import ReviewService

router = APIRouter(
    prefix="/review",
    tags=["review"],
    dependencies=[Depends(require_api_token)],
)


@router.post("", summary="Trigger a code review for a pull request")
async def create_review(
    body: ReviewRequest,
    svc: ReviewService = Depends(get_review_service),
):
    """
    Fetch the PR diff, analyse it with an LLM, persist the result, and
    (optionally) post a comment on GitHub.

    Returns the structured review JSON plus the review database id.
    """
    logger.info(f"POST /review repo={body.repo_name} pr={body.pr_number}")
    try:
        review, review_id = await svc.run_review(
            repo_name=body.repo_name,
            pr_number=body.pr_number,
            post_comment=body.post_comment,
        )
        return {"review_id": review_id, "review": review.model_dump(mode="json")}
    except Exception as exc:
        logger.error(f"Review failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{review_id}", summary="Retrieve a stored review by id")
async def get_review(
    review_id: str,
    svc: ReviewService = Depends(get_review_service),
):
    """Return a previously stored review document."""
    doc = await svc.get_review(review_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Review not found")
    return doc


@router.get("", summary="List review history")
async def list_reviews(
    repo: str | None = Query(default=None, description="Filter by repo full name"),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    svc: ReviewService = Depends(get_review_service),
):
    """Return paginated review history, optionally filtered by repository."""
    return await svc.list_reviews(repo=repo, limit=limit, skip=skip)


@router.post("/approve", summary="Approve a pending review and post it to GitHub")
async def approve_review(
    body: ApprovalRequest,
    svc: ReviewService = Depends(get_review_service),
):
    """
    When ``REQUIRE_HUMAN_APPROVAL=true``, reviews are saved but not posted.
    Call this endpoint to approve a review and publish it as a PR comment.
    """
    try:
        comment_url = await svc.approve_and_post(body.review_id, body.approved_by)
        return {"comment_url": comment_url}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Approval failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
