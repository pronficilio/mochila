FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DENO_INSTALL=/usr/local

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp currently recommends Deno for YouTube's JS challenge runtime.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && deno --version \
    && ffmpeg -version | head -n 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -c "import socks" \
    && yt-dlp --version

COPY app ./app

# Fail the image build if the pinned external PO provider cannot register with
# the installed yt-dlp version. This makes provider discovery reproducible.
RUN python -c "from app.ytdlp_runner import configure_bgutil_pot_provider; configure_bgutil_pot_provider(); from yt_dlp.extractor.youtube.pot.provider import _pot_providers; assert _pot_providers.value['BgUtilHTTP'].PROVIDER_VERSION == '2.0.0'"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
