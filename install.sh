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

    cat > "${ENV_FILE}" << EOF
POSTGRES_HOST=postgres
POSTGRES_USER=fim
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=fim
LOCAL_USERNAME=local
API_PORT=8000
HTTP_PORT=8080
SCAN_INTERVAL_SECONDS=60
EOF
    chmod 600 "${ENV_FILE}"
    echo "[OK] .env created with unique random secrets for this machine"
else
    echo "[--] .env already exists, normalizing"
    awk -F= '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { next }
        NF { env[$1]=$0 }
        END { for (k in env) print env[k] }
    ' "${ENV_FILE}" > "${ENV_FILE}.tmp"
    mv "${ENV_FILE}.tmp" "${ENV_FILE}"
    grep -q '^POSTGRES_HOST=' "${ENV_FILE}" || echo 'POSTGRES_HOST=postgres' >> "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
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
ExecStart=${INSTALL_DIR}/scripts/fim-start.sh
ExecStop=${DOCKER_BIN} compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

cp /tmp/${SERVICE_NAME}.service "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
echo "[OK] Autostart registered (${SERVICE_FILE})"

# ── 4. First launch ────────────────────────────────────────────────────────
echo "[..] Building and starting FIM Sentinel (this may take 5-10 minutes on first run)..."
cd "${INSTALL_DIR}"
if ! docker compose up -d --build; then
    echo "[ERR] docker compose failed — API logs:"
    docker compose logs api --tail=40 || true
    exit 1
fi
echo "[OK] FIM Sentinel started"
systemctl start "${SERVICE_NAME}" 2>/dev/null || true

# ── 5. Global 'fim' command ────────────────────────────────────────────────
cat > /usr/local/bin/fim << EOF
#!/usr/bin/env bash
# FIM Sentinel control command
cd "${INSTALL_DIR}"
case "\${1:-status}" in
    start)   systemctl start ${SERVICE_NAME} ;;
    stop)    systemctl stop ${SERVICE_NAME} ;;
    restart) systemctl restart ${SERVICE_NAME} ;;
    logs)    docker compose logs -f --tail=50 ;;
    status)  systemctl status ${SERVICE_NAME} --no-pager -l ;;
    update)  bash "${INSTALL_DIR}/fim-update.sh" ;;
    open)    bash "${INSTALL_DIR}/scripts/fim-open-dashboard.sh" ;;
    doctor)  bash "${INSTALL_DIR}/scripts/fim-doctor.sh" ;;
    setup)   echo "Run: sudo bash ${INSTALL_DIR}/install.sh" ;;
    *)       echo "Usage: fim {start|stop|restart|status|logs|update|open|doctor|setup}" ;;
esac
EOF
chmod +x /usr/local/bin/fim
chmod +x "${INSTALL_DIR}/scripts/fim-start.sh" "${INSTALL_DIR}/scripts/fim-open-dashboard.sh" "${INSTALL_DIR}/scripts/fim-git-sync.sh" "${INSTALL_DIR}/scripts/fim-doctor.sh"
echo "[OK] Global command 'fim' installed — use from anywhere"

# ── 6. Auto-open browser on desktop login ─────────────────────────────────
AUTOSTART_DIR="/etc/xdg/autostart"
mkdir -p "${AUTOSTART_DIR}"
DESKTOP_FILE="${AUTOSTART_DIR}/fim-sentinel-browser.desktop"
cat > "${DESKTOP_FILE}" << EOF
[Desktop Entry]
Type=Application
Name=FIM Sentinel Dashboard
Comment=Open FIM Sentinel dashboard on login
Exec=bash ${INSTALL_DIR}/scripts/fim-open-dashboard.sh
Icon=security-high
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
OnlyShowIn=GNOME;XFCE;KDE;LXQt;Unity;MATE;Cinnamon;
EOF
chmod 644 "${DESKTOP_FILE}"

_install_user_autostart() {
    local u="$1"
    local home
    home="$(getent passwd "${u}" 2>/dev/null | cut -d: -f6 || true)"
    [ -z "${home}" ] && return 0
    local ua="${home}/.config/autostart"
    mkdir -p "${ua}"
    cp "${DESKTOP_FILE}" "${ua}/fim-sentinel-browser.desktop"
    chown -R "${u}:${u}" "${ua}"
    echo "[OK] Browser autostart installed for user ${u}"
}

# User who ran sudo (e.g. kali), and kali when installer runs as root
REAL_USER="${SUDO_USER:-}"
if [ -n "${REAL_USER}" ] && [ "${REAL_USER}" != "root" ]; then
    _install_user_autostart "${REAL_USER}"
fi
if getent passwd kali >/dev/null 2>&1; then
    _install_user_autostart kali
fi
echo "[OK] Browser will open automatically on desktop login"

echo ""
echo "=== Done! FIM Sentinel is running and will auto-start on boot ==="
echo "    Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "    fim status   — check status"
echo "    fim logs     — view live logs"
echo "    fim stop     — stop"
echo "    fim start    — start"
echo "    fim update   — pull latest and rebuild"
