from urllib.parse import urlsplit

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
}


def validate_youtube_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are accepted")

    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_HOSTS:
        raise ValueError("Only YouTube URLs are accepted")

    if not parsed.path or parsed.path == "/":
        raise ValueError("URL does not identify a video")

    return value
