#!/usr/bin/env bash
# Start FIM Sentinel and wait until the API responds.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

HTTP_PORT=8080
if [ -f .env ]; then
    # shellcheck disable=SC1091
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
    HTTP_PORT="${HTTP_PORT:-8080}"
fi

echo "[fim-start] Starting containers..."
for attempt in 1 2 3 4 5; do
    if docker compose up -d; then
        break
    fi
    echo "[fim-start] docker compose failed (attempt ${attempt}/5), retrying..."
    sleep 5
done

echo "[fim-start] Waiting for API on port ${HTTP_PORT}..."
for _ in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:${HTTP_PORT}/api/v1/health/status" >/dev/null 2>&1; then
        echo "[fim-start] API is ready"
        exit 0
    fi
    sleep 2
done

echo "[fim-start] Warning: API did not respond in time (containers may still be starting)"
exit 0
