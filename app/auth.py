import hmac

import secrets
from fastapi import HTTPException, Request, Response, status

from .db import login_attempt_key, r, session_key
from .models import LoginRequest
from .settings import settings


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _too_many_login_attempts(client_id: str) -> bool:
    value = r.get(login_attempt_key(client_id))
    return value is not None and int(value) >= settings.login_max_attempts


def _record_failed_login(client_id: str) -> None:
    key = login_attempt_key(client_id)
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.login_window_seconds)
    pipe.execute()


def _clear_login_attempts(client_id: str) -> None:
    r.delete(login_attempt_key(client_id))


def login(request: Request, response: Response, payload: LoginRequest) -> dict[str, bool]:
    client_id = _client_id(request)
    if _too_many_login_attempts(client_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(settings.login_window_seconds)},
        )

    if not hmac.compare_digest(payload.password, settings.app_password):
        _record_failed_login(client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    _clear_login_attempts(client_id)
    token = secrets.token_urlsafe(32)
    r.setex(session_key(token), settings.session_ttl_seconds, "authenticated")
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return {"authenticated": True}


def logout(response: Response, session: str | None) -> dict[str, bool]:
    if session:
        r.delete(session_key(session))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"authenticated": False}


def is_authenticated(session: str | None) -> bool:
    return bool(session and r.get(session_key(session)) == "authenticated")


def require_session(request: Request) -> None:
    session = request.cookies.get(settings.session_cookie_name)
    if not is_authenticated(session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
