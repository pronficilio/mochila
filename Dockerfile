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
    && yt-dlp --version

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
