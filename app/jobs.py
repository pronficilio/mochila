from datetime import datetime, timezone
from uuid import uuid4

from .db import QUEUE_KEY, job_key, r
from .settings import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(*, url: str, mode: str, max_height: int, audio_format: str) -> dict[str, str]:
    job_id = uuid4().hex
    ts = now_iso()
    data = {
        "id": job_id,
        "status": "queued",
        "url": url,
        "mode": mode,
        "max_height": str(max_height),
        "audio_format": audio_format,
        "created_at": ts,
        "updated_at": ts,
        "error": "",
        "filename": "",
    }
    key = job_key(job_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping=data)
    pipe.expire(key, settings.job_ttl_seconds)
    pipe.lpush(QUEUE_KEY, job_id)
    pipe.execute()
    return data


def get_job(job_id: str) -> dict[str, str] | None:
    data = r.hgetall(job_key(job_id))
    return data or None


def update_job(job_id: str, **fields: str) -> None:
    fields["updated_at"] = now_iso()
    key = job_key(job_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping=fields)
    pipe.expire(key, settings.job_ttl_seconds)
    pipe.execute()



def create_download_token(job_id: str, ttl_seconds: int = 60) -> str:
    import secrets
    token = secrets.token_urlsafe(32)
    r.setex(f"download-token:{token}", ttl_seconds, job_id)
    return token


def consume_download_token(token: str) -> str | None:
    # Redis >= 6.2 supports GETDEL; redis:7-alpine is used by compose.
    value = r.getdel(f"download-token:{token}")
    return value
