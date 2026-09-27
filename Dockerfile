FROM python:3.13-slim

# Install system dependencies:
# - gcc/build-essential: required to build tgcrypto
# - stockfish: chess engine
# - ffmpeg: audio conversion/playback
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        stockfish \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Make sure Stockfish location is available
ENV PATH="/usr/games:${PATH}"

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn webhook:app --host 0.0.0.0 --port $PORT"]