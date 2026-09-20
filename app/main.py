from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse

from .auth import require_api_key
from .db import job_key, r
from .downloader import delete_job_files
from .jobs import create_download_token, create_job, consume_download_token, get_job
from .models import CreateJobRequest, JobResponse
from .settings import settings

app = FastAPI(title="Private YouTube Downloader", version="0.1.0")


def serialize_job(job: dict[str, str]) -> JobResponse:
    done = job.get("status") == "done"
    return JobResponse(
        id=job["id"],
        status=job["status"],
        mode=job["mode"],
        url=job["url"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        error=job.get("error") or None,
        filename=job.get("filename") or None,
        download_url=f"/v1/jobs/{job['id']}/file" if done else None,
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    html = Path(__file__).with_name("static").joinpath("index.html").read_text()
    return HTMLResponse(html)


@app.get("/health")
def health() -> dict[str, str]:
    r.ping()
    return {"status": "ok"}


@app.post(
    "/v1/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
def submit(payload: CreateJobRequest) -> JobResponse:
    height = payload.max_height or settings.default_max_height
    job = create_job(
        url=payload.url,
        mode=payload.mode,
        max_height=height,
        audio_format=payload.audio_format,
    )
    return serialize_job(job)


@app.get(
    "/v1/jobs/{job_id}",
    response_model=JobResponse,
    dependencies=[Depends(require_api_key)],
)
def status_of(job_id: str) -> JobResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)


@app.get(
    "/v1/jobs/{job_id}/file",
    dependencies=[Depends(require_api_key)],
)
def download_file(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "done" or not job.get("filename"):
        raise HTTPException(status_code=409, detail="Job is not complete")

    filename = Path(job["filename"]).name
    path = (settings.data_dir / filename).resolve()
    data_dir = settings.data_dir.resolve()
    if data_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file is missing")

    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.post(
    "/v1/jobs/{job_id}/download-token",
    dependencies=[Depends(require_api_key)],
)
def mint_download_token(job_id: str) -> dict[str, str]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "done" or not job.get("filename"):
        raise HTTPException(status_code=409, detail="Job is not complete")

    token = create_download_token(job_id)
    return {"url": f"/download/{token}", "expires_in": "60"}


@app.get("/download/{token}", include_in_schema=False)
def browser_download(token: str) -> FileResponse:
    job_id = consume_download_token(token)
    if not job_id:
        raise HTTPException(status_code=404, detail="Download token expired or already used")

    job = get_job(job_id)
    if not job or job.get("status") != "done" or not job.get("filename"):
        raise HTTPException(status_code=404, detail="Output is unavailable")

    filename = Path(job["filename"]).name
    path = (settings.data_dir / filename).resolve()
    data_dir = settings.data_dir.resolve()
    if data_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file is missing")

    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.delete(
    "/v1/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
def delete(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running job in V0")

    delete_job_files(job_id)
    r.delete(job_key(job_id))
