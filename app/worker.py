import logging
import time

from .db import QUEUE_KEY, r
from .downloader import DownloadError, cleanup_old_files, run_download
from .jobs import get_job, update_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("worker")


def handle(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        log.warning("job disappeared before execution: %s", job_id)
        return

    update_job(job_id, status="running", error="")
    try:
        output = run_download(job)
    except DownloadError as exc:
        log.exception("job failed: %s", job_id)
        update_job(job_id, status="failed", error=str(exc)[-5000:])
        return
    except Exception as exc:
        log.exception("unexpected worker error: %s", job_id)
        update_job(job_id, status="failed", error=f"Unexpected error: {exc}")
        return

    update_job(job_id, status="done", filename=output.name, error="")
    log.info("job complete: %s -> %s", job_id, output.name)
    cleanup_old_files()


def main() -> None:
    log.info("worker online")
    while True:
        try:
            item = r.brpop(QUEUE_KEY, timeout=10)
            if item:
                _, job_id = item
                handle(job_id)
            else:
                cleanup_old_files()
        except Exception:
            log.exception("worker loop error")
            time.sleep(2)


if __name__ == "__main__":
    main()
