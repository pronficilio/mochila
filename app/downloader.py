import glob
import os
import subprocess
from pathlib import Path

from .settings import settings


class DownloadError(RuntimeError):
    pass


def _existing_outputs(job_id: str) -> set[str]:
    pattern = str(settings.data_dir / f"{job_id}.*")
    return {
        p for p in glob.glob(pattern)
        if not p.endswith((".part", ".ytdl", ".temp"))
    }


def _pick_output(job_id: str, before: set[str]) -> Path:
    after = _existing_outputs(job_id)
    candidates = sorted(
        (Path(p) for p in after - before),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        # A retry can legitimately overwrite/reuse an existing filename.
        candidates = sorted(
            (Path(p) for p in after),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not candidates:
        raise DownloadError("yt-dlp exited successfully but no output file was found")
    return candidates[0]


def build_command(job: dict[str, str]) -> list[str]:
    job_id = job["id"]
    mode = job["mode"]
    max_height = int(job["max_height"])
    url = job["url"]

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-progress",
        "--restrict-filenames",
        "--js-runtimes", "deno",
        "--paths", str(settings.data_dir),
        "--output", f"{job_id}.%(ext)s",
        "--max-filesize", settings.max_filesize,
        "--socket-timeout", "20",
        "--retries", "3",
        "--fragment-retries", "3",
        "--concurrent-fragments", "4",
    ]

    if mode == "video":
        cmd += [
            "--format",
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]",
            "--merge-output-format",
            "mp4",
        ]
    else:
        audio_format = job["audio_format"]
        cmd += [
            "--extract-audio",
            "--audio-format", audio_format,
        ]
        if audio_format == "mp3":
            cmd += ["--audio-quality", "0"]

    cmd += ["--", url]
    return cmd


def run_download(job: dict[str, str]) -> Path:
    before = _existing_outputs(job["id"])
    cmd = build_command(job)

    try:
        result = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=settings.download_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DownloadError(
            f"Download exceeded {settings.download_timeout_seconds}s timeout"
        ) from exc

    if result.returncode != 0:
        tail = (result.stdout or "")[-5000:]
        raise DownloadError(f"yt-dlp failed with exit code {result.returncode}:\n{tail}")

    return _pick_output(job["id"], before)


def delete_job_files(job_id: str) -> None:
    for path in settings.data_dir.glob(f"{job_id}.*"):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def cleanup_old_files() -> None:
    if settings.file_ttl_seconds <= 0:
        return

    import time
    cutoff = time.time() - settings.file_ttl_seconds
    for path in settings.data_dir.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except FileNotFoundError:
            pass
