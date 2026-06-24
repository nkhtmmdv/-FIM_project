#!/usr/bin/env bash
# Open the FIM dashboard when the user logs in.
# The web UI waits for API itself — browser opens quickly like before.

DIR="${FIM_INSTALL_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HTTP_PORT=8080

if [ -f "${DIR}/.env" ]; then
    val=$(grep -E '^HTTP_PORT=' "${DIR}/.env" | head -1 | cut -d= -f2- | tr -d ' "'\''')
    [ -n "$val" ] && HTTP_PORT="$val"
fi

URL="http://127.0.0.1:${HTTP_PORT}/#dashboard"

# Let the desktop session finish starting (same behaviour as before).
sleep 5

xdg-open "${URL}" 2>/dev/null \
    || sensible-browser "${URL}" 2>/dev/null \
    || firefox "${URL}" 2>/dev/null \
    || true
