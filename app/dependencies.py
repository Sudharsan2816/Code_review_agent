"""Lazily constructed application services."""

from functools import lru_cache

from app.services.review_service import ReviewService


@lru_cache(maxsize=1)
def get_review_service() -> ReviewService:
    """Build integrations only when a protected route needs them."""
    return ReviewService()
