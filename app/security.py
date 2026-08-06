"""Authentication dependencies for non-webhook API routes."""

from hmac import compare_digest

from fastapi import Header, HTTPException, status

from app.config import get_settings


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def require_api_token(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Require the configured token for manually triggered review operations."""
    expected = get_settings().api_auth_token.strip()
    supplied = (x_api_key or "").strip() or _bearer_token(authorization)
    if not expected or not supplied or not compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API credentials are required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
