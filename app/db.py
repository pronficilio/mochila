import redis
from .settings import settings

r = redis.Redis.from_url(settings.redis_url, decode_responses=True)

QUEUE_KEY = "queue:downloads"
SESSION_KEY_PREFIX = "session:"
LOGIN_ATTEMPT_KEY_PREFIX = "login-attempts:"


def job_key(job_id: str) -> str:
    return f"job:{job_id}"


def session_key(token: str) -> str:
    return f"{SESSION_KEY_PREFIX}{token}"


def login_attempt_key(client_id: str) -> str:
    return f"{LOGIN_ATTEMPT_KEY_PREFIX}{client_id}"
