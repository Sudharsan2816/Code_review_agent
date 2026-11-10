"""GitHub webhook endpoint."""

import json

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from loguru import logger

from app.dependencies import get_review_service
from app.models.webhook import PullRequestEvent
from app.services.github_service import GitHubService

router = APIRouter(prefix="/webhook", tags=["webhook"])

_TRIGGER_ACTIONS = {"opened", "synchronize", "reopened"}


def review_claim_key(repo_name: str, pr_number: int, head_sha: str) -> str:
    """One key per pull request per head commit."""
    return f"{repo_name}#{pr_number}@{head_sha}"


async def _run_review(repo_name: str, pr_number: int, claim_key: str | None = None) -> None:
    """Complete a webhook-triggered review after GitHub has been acknowledged."""
    service = get_review_service()
    try:
        review, review_id = await service.run_review(
            repo_name=repo_name,
            pr_number=pr_number,
            post_comment=True,
        )
        logger.info(
            f"Webhook review completed id={review_id} verdict={review.final_verdict.value}"
        )
    except Exception as exc:
        logger.exception(f"Webhook-triggered review failed: {exc}")
        if claim_key:
            try:
                await service.release_webhook_review(claim_key)
            except Exception as release_exc:
                logger.error(f"Could not release claim {claim_key}: {release_exc}")


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
    or ``reopened`` trigger an automatic review, and only once per head commit.
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
    head_sha = event.pull_request.head.get("sha")

    # GitHub redelivers webhooks, and opened/reopened can arrive for a commit that
    # was already reviewed. Claim the PR's head commit once; later deliveries of
    # the same commit are acknowledged without starting a second review.
    claim_key = review_claim_key(repo_name, pr_number, head_sha) if head_sha else None
    if claim_key:
        try:
            claimed = await get_review_service().claim_webhook_review(claim_key)
        except Exception as exc:
            # A missed duplicate costs one extra review; a missed review costs more.
            logger.warning(f"Could not record review claim, reviewing anyway: {exc}")
            claimed, claim_key = True, None
        if not claimed:
            logger.info(f"Duplicate delivery for {claim_key}; review already started")
            return {
                "status": "duplicate",
                "repo": repo_name,
                "pr_number": pr_number,
                "head_sha": head_sha,
            }

    logger.info(f"Webhook triggered review for {repo_name}#{pr_number} action={event.action}")

    background_tasks.add_task(_run_review, repo_name, pr_number, claim_key)
    return {
        "status": "accepted",
        "repo": repo_name,
        "pr_number": pr_number,
        "head_sha": head_sha,
    }
