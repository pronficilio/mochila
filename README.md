# Private YouTube Downloader — V0

A small self-hosted download service for videos you own or are authorized to download.

## Architecture

- FastAPI API + tiny web UI
- Redis job queue/state
- Dedicated worker
- yt-dlp + FFmpeg
- Deno JS runtime for current YouTube challenge handling
- Shared ephemeral-ish download volume
- Bearer-token authentication
- One-use 60-second browser download tickets (avoids buffering large files in JS memory)
- YouTube-only URL allowlist
- Playlists disabled in V0

## Start

```bash
cp .env.example .env
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
# Put that value into API_KEY in .env

docker compose up -d --build
docker compose logs -f worker
```

The service binds to `127.0.0.1:8080` on the Hetzner host by default.

From your laptop:

```bash
ssh -L 8080:127.0.0.1:8080 user@your-server
```

Then open:

```text
http://127.0.0.1:8080
```

## API

Create:

```bash
curl -sS http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url":"https://www.youtube.com/watch?v=VIDEO_ID",
    "mode":"video",
    "max_height":1080
  }'
```

Poll:

```bash
curl -sS http://127.0.0.1:8080/v1/jobs/JOB_ID \
  -H "Authorization: Bearer $API_KEY"
```

Download:

```bash
curl -L http://127.0.0.1:8080/v1/jobs/JOB_ID/file \
  -H "Authorization: Bearer $API_KEY" \
  -o video.bin
```

## Current boundaries

V0 intentionally does not:
- download playlists
- accept arbitrary extractor URLs
- mount account cookies
- expose Redis publicly
- cancel a running yt-dlp process
- implement per-user quotas
- expose public Internet ingress

For age-restricted/private content, add cookie support later as an explicit secret-mount feature rather than passing cookie data through the API.

## Production next steps

1. Put the service on Tailscale/WireGuard or a reverse proxy with TLS.
2. Add streaming progress via yt-dlp progress templates/hooks.
3. Add cancellation and worker heartbeats.
4. Add disk quota / file-size enforcement at the filesystem layer.
5. Add PO-token provider support only if YouTube enforcement makes it necessary on the Hetzner IP.
6. Add Prometheus metrics and structured logs.


## Tests

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```
