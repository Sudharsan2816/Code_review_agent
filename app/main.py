"""FastAPI application entry point."""

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes.review import router as review_router
from app.api.routes.webhook import router as webhook_router
from app.config import get_settings

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
    level="DEBUG" if get_settings().debug else "INFO",
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="14 days",
    compression="gz",
    level="DEBUG",
)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Code Review Agent",
    description=(
        "A production-ready AI-powered code review service that analyses GitHub "
        "pull requests and posts structured reviews as PR comments."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review_router)
app.include_router(webhook_router)


@app.get("/health", tags=["system"])
async def health_check():
    """Liveness probe."""
    return {"status": "ok", "version": "1.0.0"}


@app.on_event("startup")
async def _startup():
    settings = get_settings()
    logger.info(
        f"AI Code Review Agent started | provider={settings.llm_provider} "
        f"| human_approval={settings.require_human_approval}"
    )
