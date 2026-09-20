import redis
from .settings import settings

r = redis.Redis.from_url(settings.redis_url, decode_responses=True)

QUEUE_KEY = "queue:downloads"


def job_key(job_id: str) -> str:
    return f"job:{job_id}"
