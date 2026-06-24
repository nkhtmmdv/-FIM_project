#!/usr/bin/env bash
# Wait for FIM API, then open the dashboard in the default browser.
set -euo pipefail

DIR="${FIM_INSTALL_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HTTP_PORT=8080

if [ -f "${DIR}/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    # shellcheck source=/dev/null
    source "${DIR}/.env" 2>/dev/null || true
    set +a
    HTTP_PORT="${HTTP_PORT:-8080}"
fi

URL="http://127.0.0.1:${HTTP_PORT}/#dashboard"

echo "[fim-open] Waiting for API on port ${HTTP_PORT}..."
for _ in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:${HTTP_PORT}/api/v1/health/status" >/dev/null 2>&1; then
        echo "[fim-open] API ready — opening dashboard"
        xdg-open "${URL}" 2>/dev/null || sensible-browser "${URL}" 2>/dev/null || true
        exit 0
    fi
    sleep 2
done

echo "[fim-open] API not ready yet — opening dashboard anyway"
xdg-open "${URL}" 2>/dev/null || sensible-browser "${URL}" 2>/dev/null || true
