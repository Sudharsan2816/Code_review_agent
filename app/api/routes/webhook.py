"""GitHub webhook endpoint."""

import json

from fastapi import APIRouter, Header, HTTPException, Request
from loguru import logger

from app.models.webhook import PullRequestEvent
from app.services.github_service import GitHubService
from app.services.review_service import ReviewService

router = APIRouter(prefix="/webhook", tags=["webhook"])
_svc = ReviewService()

_TRIGGER_ACTIONS = {"opened", "synchronize", "reopened"}


@router.post("/github", summary="Receive GitHub pull_request webhook events")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default="", alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(default="", alias="X-Hub-Signature-256"),
):
    """
    Process incoming GitHub webhook events.

    Only ``pull_request`` events with actions ``opened``, ``synchronize``,
    or ``reopened`` trigger an automatic review.
    """
    payload_bytes = await request.body()

    # Signature verification
    if x_hub_signature_256:
        if not GitHubService.verify_webhook_signature(payload_bytes, x_hub_signature_256):
            logger.warning("Webhook signature mismatch — rejecting request")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event != "pull_request":
        logger.debug(f"Ignoring webhook event type={x_github_event!r}")
        return {"status": "ignored", "reason": f"event type '{x_github_event}' not handled"}

    try:
        body = json.loads(payload_bytes)
        event = PullRequestEvent(**body)
    except Exception as exc:
        logger.error(f"Webhook payload parse error: {exc}")
        raise HTTPException(status_code=422, detail=f"Invalid payload: {exc}")

    if event.action not in _TRIGGER_ACTIONS:
        logger.info(f"PR action '{event.action}' skipped (not in trigger list)")
        return {"status": "ignored", "reason": f"action '{event.action}' not in trigger list"}

    repo_name = event.repository.full_name
    pr_number = event.number
    logger.info(f"Webhook triggered review for {repo_name}#{pr_number} action={event.action}")

    try:
        review, review_id = await _svc.run_review(
            repo_name=repo_name,
            pr_number=pr_number,
            post_comment=True,
        )
        return {
            "status": "review_triggered",
            "review_id": review_id,
            "verdict": review.final_verdict.value,
        }
    except Exception as exc:
        logger.error(f"Webhook-triggered review failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
