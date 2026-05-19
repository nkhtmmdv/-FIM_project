# FIM Sentinel

Production-grade Linux **File Integrity Monitor** with a Python scanner engine, FastAPI REST API, PostgreSQL persistence, and a dark-themed analyst dashboard.

## Architecture

```
 Host filesystem (read-only mounts)
          |
   [ Scanner Engine ] ---> [ PostgreSQL 15 ] <--- [ FastAPI API ]
          |                                             |
   Telegram / SMTP                               [ Nginx Dashboard ]
                                                        |
                                                   Analyst browser
```

- **Scanner** — hashes files every N seconds, compares to baseline, writes events, dispatches alerts.
- **API** — JWT-secured REST + WebSocket endpoints for dashboard and automation.
- **Dashboard** — single-page dark-mode UI with live updates, charts, and CSV export.
- **PostgreSQL** — stores baselines, scan results, events, users, and audit log.

All services run in Docker. The scanner and database are on an isolated internal network with no internet access.

---

## 5-Command Quickstart

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Generate secure secrets automatically
python3 -c "
import secrets
p='.env'; s=open(p).read()
s=s.replace('change_me_minimum_32_characters_long', secrets.token_urlsafe(32))
s=s.replace('change_me_minimum_64_characters_long_change_me_minimum_64_characters_long', secrets.token_urlsafe(64))
s=s.replace('change_me_before_first_start', secrets.token_urlsafe(18))
s=s.replace('change_me_reset_token', secrets.token_urlsafe(32))
open(p,'w').write(s)
"

# 3. Build all images
docker compose build

# 4. Start the stack
docker compose up -d

# 5. Watch logs
docker compose logs -f scanner api
```

Open `http://localhost:8080` and log in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` from your `.env`.

---

## First Baseline Scan

On the very first scanner start, if the `baseline_hashes` table is empty, the scanner automatically creates a baseline and does **not** fire any alerts. Every subsequent scan compares against this baseline.

To force a new baseline later:
- **Dashboard** — Settings page > Baseline Management > "Create New Baseline"
- **API** — `POST /api/v1/baseline/create` with a valid JWT Bearer token
- **Per-file** — File detail drawer > "Reset Baseline" (requires password re-confirmation)

---

## Telegram Bot Setup

1. Open Telegram, search for **@BotFather**, and start a chat.
2. Send `/newbot`. Choose a display name and a username (must end in `bot`).
3. BotFather replies with a **bot token** like `123456:ABC-DEF...`. Copy it.
4. Paste the token into `TELEGRAM_BOT_TOKEN` in your `.env`.
5. Start a chat with your new bot (or add it to a group).
6. Send any message to the bot, then open:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
7. Find `"chat":{"id": 123456789}` in the response. Copy that number.
8. Paste it into `TELEGRAM_CHAT_ID` in your `.env`.
9. Restart the scanner: `docker compose restart scanner`.

Alerts are batched (5 per message) and sent with exponential backoff on failure.

---

## Simulate an Attack (Testing)

> **Only run this on a disposable test host. Never modify real system files.**

```bash
# Create a test directory with copies of system files
mkdir -p ./test-files
cp /etc/passwd ./test-files/passwd-copy
cp /etc/hosts  ./test-files/hosts-copy

# Add the test path to docker-compose scanner volumes:
#   - ./test-files:/monitored/test-files:ro

# Restart, create a baseline, then modify a file:
echo "hacker:x:0:0::/root:/bin/bash" >> ./test-files/passwd-copy
chmod 777 ./test-files/hosts-copy

# The next scan cycle will detect MODIFIED and PERMISSIONS_CHANGED events.
```

You can also use the dashboard's "Manual Trigger" button to force an immediate scan.

---

## API Endpoints Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Authenticate, get JWT + refresh token |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/files` | List monitored files (paginated) |
| GET | `/api/v1/files/{path}` | Single file + full history |
| POST | `/api/v1/files/add` | Add a monitored path |
| DELETE | `/api/v1/files/{path}` | Deactivate a monitored path |
| GET | `/api/v1/alerts` | List alerts (filterable) |
| GET | `/api/v1/alerts/recent` | Last 20 alerts |
| PUT | `/api/v1/alerts/{id}/acknowledge` | Acknowledge an alert |
| POST | `/api/v1/baseline/create` | Trigger baseline creation |
| POST | `/api/v1/baseline/reset/{path}` | Reset baseline (password required) |
| GET | `/api/v1/baseline/status` | Baseline metadata |
| GET | `/api/v1/scan/status` | Latest scan status |
| POST | `/api/v1/scan/trigger` | Trigger manual scan |
| GET | `/api/v1/scan/history` | Scan history (last 100) |
| GET | `/api/v1/stats/summary` | Dashboard summary counters |
| GET | `/api/v1/stats/timeline` | Hourly alert timeline (24h) |
| GET | `/api/v1/stats/top-changed` | Top 10 most-changed files |
| WS | `/ws/live` | Live events stream |

---

## Troubleshooting — Top 10

1. **API crashes at startup** — `JWT_SECRET` must be 64+ characters and `POSTGRES_PASSWORD` must be 32+ characters. Run the secret-generation script above.

2. **Login fails with "bad credentials"** — Confirm `ADMIN_PASSWORD` in `.env`. If you changed it after the first boot, delete the Postgres volume and restart: `docker compose down -v && docker compose up -d`.

3. **No baseline created** — Check `docker compose logs scanner` for database connection errors. Ensure Postgres is healthy: `docker compose ps`.

4. **No Telegram alerts** — Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set. Note: the scanner container is on an internal network by default. If you need Telegram alerts, add `fim-external` to the scanner's networks in `docker-compose.yml`.

5. **"Permission denied" in scanner logs** — Expected for files like `/etc/shadow`. They are recorded as `UNREADABLE` status without crashing.

6. **Dashboard shows "Connection lost"** — The WebSocket proxy may not be configured. Verify nginx is running and `/ws/live` location block is present in `nginx.conf`.

7. **Dashboard can't reach API** — Check that the API container is running and that nginx proxies `/api/` correctly. Run `docker compose ps` and `docker compose logs api`.

8. **Scanner can't read host files** — The read-only bind mounts (`/etc:/monitored/etc:ro`) require the host paths to exist. This project is designed for Linux hosts.

9. **Scans are slow** — Reduce directory scope in `config.yaml` or the `monitored_files` table. Large directories like `/usr/bin/` add many files. Increase `SCAN_INTERVAL_SECONDS`.

10. **Baseline reset denied** — The reset endpoint requires the logged-in user to re-enter their password. Ensure the `BASELINE_CONFIRMATION_TOKEN` in `.env` matches between the API and scanner containers.

---

## Security Design

- **Secrets** — All credentials are in `.env` only (git-ignored). Never hardcoded.
- **SQL** — Parameterised queries everywhere. No string interpolation in SQL.
- **Passwords** — bcrypt with cost factor 12.
- **JWT** — HS256, 1-hour access tokens, 7-day refresh tokens. Secret minimum 64 chars.
- **Scanner** — Runs as non-root UID 1001. All filesystem mounts are read-only.
- **Network** — Scanner and Postgres are on an isolated internal Docker network with no internet.
- **Audit** — All user actions (login, file add/remove, baseline reset, alert ack) are logged to `audit_log`.
- **Logs** — JSON structured, daily rotation with 30-day retention, daily SHA-256 checksums.
- **Headers** — CSP, HSTS, X-Frame-Options DENY, X-Content-Type-Options nosniff on all responses.
