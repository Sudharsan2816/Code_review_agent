"""GitHub webhook endpoint."""

import json

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from loguru import logger

from app.dependencies import get_review_service
from app.models.webhook import PullRequestEvent
from app.services.github_service import GitHubService

router = APIRouter(prefix="/webhook", tags=["webhook"])

_TRIGGER_ACTIONS = {"opened", "synchronize", "reopened"}


async def _run_review(repo_name: str, pr_number: int) -> None:
    """Complete a webhook-triggered review after GitHub has been acknowledged."""
    try:
        review, review_id = await get_review_service().run_review(
            repo_name=repo_name,
            pr_number=pr_number,
            post_comment=True,
        )
        logger.info(
            f"Webhook review completed id={review_id} verdict={review.final_verdict.value}"
        )
    except Exception as exc:
        logger.exception(f"Webhook-triggered review failed: {exc}")


@router.post("/github", summary="Receive GitHub pull_request webhook events")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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
    if not x_hub_signature_256 or not GitHubService.verify_webhook_signature(
        payload_bytes, x_hub_signature_256
    ):
        logger.warning("Missing or invalid webhook signature - rejecting request")
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

    background_tasks.add_task(_run_review, repo_name, pr_number)
    return {
        "status": "accepted",
        "repo": repo_name,
        "pr_number": pr_number,
    }
