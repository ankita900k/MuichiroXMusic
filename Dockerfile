FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        stockfish \
        ffmpeg \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV DENO_INSTALL=/opt/deno
ENV PATH="/opt/deno/bin:/usr/games:${PATH}"

RUN curl -fsSL https://deno.land/install.sh | sh \
    && deno --version

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn webhook:app --host 0.0.0.0 --port $PORT"]