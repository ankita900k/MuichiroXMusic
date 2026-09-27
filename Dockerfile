FROM python:3.13-slim

# System dependencies:
# - build-essential: required to build tgcrypto when a prebuilt wheel is unavailable
# - stockfish: chess engine
# directly to PyTgCalls, so no local audio conversion/transcoding is used.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        stockfish \
    && rm -rf /var/lib/apt/lists/*

# Make sure Stockfish is available to the application
ENV PATH="/usr/games:${PATH}"

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn webhook:app --host 0.0.0.0 --port $PORT"]