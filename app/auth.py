import hmac
from fastapi import Header, HTTPException, status
from .settings import settings


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    supplied = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
