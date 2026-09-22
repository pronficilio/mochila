import glob
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .settings import settings


class DownloadError(RuntimeError):
    pass


def classify_youtube_failure(output: str) -> str:
    """Return a stable, non-secret failure category for worker logs and jobs."""
    normalized = output.lower()
    if (
        "http error 429" in normalized
        or "too many requests" in normalized
        or "sign in to confirm you're not a bot" in normalized
    ):
        return "YOUTUBE_RATE_LIMITED"
    if "po token" in normalized or "pot provider" in normalized:
        return "YOUTUBE_PO_TOKEN_UNAVAILABLE"
    return "YOUTUBE_EXTRACTOR_FAILURE"


def residential_proxy_reachable(timeout_seconds: float = 3.0) -> bool:
    """Check the SOCKS listener without sending any traffic to YouTube."""
    if settings.download_egress != "residential":
        return False

    proxy = urlsplit(settings.residential_proxy_url())
    try:
        with socket.create_connection(
            (proxy.hostname, proxy.port), timeout=timeout_seconds
        ):
            return True
    except OSError:
        return False


def _redact_proxy_secrets(value: str) -> str:
    """Keep a proxy URL with userinfo out of worker errors and logs."""
    if settings.residential_proxy is None:
        return value

    proxy_url = settings.residential_proxy_url()
    proxy = urlsplit(proxy_url)
    if proxy.username is None and proxy.password is None:
        return value

    host = proxy.hostname or "proxy"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{proxy.port}" if proxy.port is not None else ""
    return value.replace(proxy_url, f"{proxy.scheme}://{host}{port}")


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

    if settings.download_egress == "residential":
        # yt-dlp's legacy SOCKS5 compatibility maps socks5:// to socks5h://.
        # The wrapper preserves local IPv4 DNS before traffic enters Dante.
        cmd[0:1] = ["python", "-m", "app.ytdlp_runner"]
        cmd += [
            "--force-ipv4",
            "--proxy", settings.residential_proxy_url(),
            "--extractor-args", "youtube:player_client=mweb;fetch_pot=auto",
            "--extractor-args",
            f"youtubepot-bgutilhttp:base_url={settings.youtube_pot_provider_url}",
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
    if (
        settings.download_egress == "residential"
        and not residential_proxy_reachable()
    ):
        raise DownloadError("Residential egress is unavailable")
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
        failure = classify_youtube_failure(tail)
        raise DownloadError(
            f"{failure}: yt-dlp failed with exit code {result.returncode}:\n"
            f"{_redact_proxy_secrets(tail)}"
        )

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
