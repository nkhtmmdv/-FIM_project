#!/usr/bin/env bash
# FIM Sentinel — one-shot installer & autostart setup
# Usage: sudo bash install.sh
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "[ERR] Run as root: sudo bash install.sh"
    exit 1
fi

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="fim-sentinel"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ENV_FILE="${INSTALL_DIR}/.env"
ENV_EXAMPLE="${INSTALL_DIR}/.env.example"

echo "=== FIM Sentinel Installer ==="
echo "Directory: ${INSTALL_DIR}"

# ── 1. .env — generate unique secrets for every installation ───────────────
if [ ! -f "${ENV_FILE}" ]; then
    # Generate cryptographically random values unique to this machine
    DB_PASS=$(openssl rand -hex 24)
    JWT_SEC=$(openssl rand -hex 40)

    cat > "${ENV_FILE}" << EOF
POSTGRES_USER=fim
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=fim
JWT_SECRET=${JWT_SEC}
API_PORT=8000
HTTP_PORT=8080
SCAN_INTERVAL_SECONDS=60
EOF
    chmod 600 "${ENV_FILE}"
    echo "[OK] .env created with unique random secrets for this machine"
else
    echo "[--] .env already exists, skipping"
fi

# ── 2. Docker check ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[ERR] Docker not found. Install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi

# ── 3. systemd service ─────────────────────────────────────────────────────
DOCKER_BIN="$(command -v docker)"

cat > /tmp/${SERVICE_NAME}.service << EOF
[Unit]
Description=FIM Sentinel — File Integrity Monitor
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=${DOCKER_BIN} compose up -d
ExecStop=${DOCKER_BIN} compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

cp /tmp/${SERVICE_NAME}.service "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
echo "[OK] Autostart registered (${SERVICE_FILE})"

# ── 4. First launch ────────────────────────────────────────────────────────
echo "[..] Starting FIM Sentinel..."
systemctl start "${SERVICE_NAME}"
sleep 3
systemctl status "${SERVICE_NAME}" --no-pager -l

echo ""
echo "=== Done! FIM Sentinel is running and will auto-start on boot ==="
echo "    Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "    To stop:    sudo systemctl stop ${SERVICE_NAME}"
echo "    To disable: sudo systemctl disable ${SERVICE_NAME}"
echo "    To check:   sudo systemctl status ${SERVICE_NAME}"
