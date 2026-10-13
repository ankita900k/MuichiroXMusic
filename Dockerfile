FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        stockfish \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp uses Deno + yt-dlp-ejs for YouTube JavaScript challenges.
ENV DENO_INSTALL=/opt/deno
ENV PATH="/opt/deno/bin:/usr/games:${PATH}"
RUN curl -fsSL https://deno.land/install.sh | sh

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn webhook:app --host 0.0.0.0 --port $PORT"]
