#!/usr/bin/env bash
# Quick diagnostics when FIM services fail to start.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

echo "=== FIM Doctor ==="
echo "Directory: ${DIR}"
echo ""

echo "--- docker compose ps ---"
docker compose ps || true
API_STATE=$(docker compose ps api 2>/dev/null | tail -1 || true)
if echo "${API_STATE}" | grep -qi 'restarting'; then
    echo ""
    echo "!! API is in a restart loop (exit 137 = killed during stop)."
    echo "   Run: fim update && docker compose up -d --build --force-recreate api"
fi
echo ""

echo "--- .env (secrets hidden) ---"
if [ -f .env ]; then
    grep -E '^(POSTGRES_HOST|POSTGRES_USER|POSTGRES_DB|HTTP_PORT|API_PORT|LOCAL_USERNAME)=' .env || true
else
    echo "MISSING .env"
fi
echo ""

echo "--- API logs (last 40 lines) ---"
docker compose logs api --tail=40 2>/dev/null || echo "no api logs"
echo ""

echo "--- Postgres logs (last 20 lines) ---"
docker compose logs postgres --tail=20 2>/dev/null || echo "no postgres logs"
echo ""

HTTP_PORT=8080
API_PORT=8000
if [ -f .env ]; then
    val=$(grep -E '^HTTP_PORT=' .env | head -1 | cut -d= -f2- | tr -d ' "'\''')
    [ -n "$val" ] && HTTP_PORT="$val"
    val=$(grep -E '^API_PORT=' .env | head -1 | cut -d= -f2- | tr -d ' "'\''')
    [ -n "$val" ] && API_PORT="$val"
fi

echo "--- HTTP probes (dashboard :${HTTP_PORT}) ---"
curl -sf "http://127.0.0.1:${HTTP_PORT}/api/v1/health/live" && echo "live: OK" || echo "live: FAIL"
curl -sf "http://127.0.0.1:${HTTP_PORT}/api/v1/health/status" && echo "status: OK" || echo "status: FAIL"
echo ""

echo "--- HTTP probes (API direct :${API_PORT}) ---"
curl -sf "http://127.0.0.1:${API_PORT}/api/v1/health/live" && echo "live: OK" || echo "live: FAIL"
echo ""

echo "If API keeps restarting:"
echo "  cd ${DIR} && git fetch origin main && git reset --hard origin/main"
echo "  docker compose up -d --build --force-recreate api"
echo ""
echo "If DB auth errors appear in API logs:"
echo "  docker compose down -v && bash install.sh"
echo "(WARNING: deletes all FIM data)"
