 # FIM Sentinel

> File Integrity Monitor for Linux hosts, packaged as a local Docker application.

FIM Sentinel watches critical files and directories, compares them against a baseline, stores change history, and shows the results in a web dashboard with optional Telegram alerts.

The default installation is **single-user local mode**:
- no account creation on first run;
- no login screen in the normal setup;
- open `http://localhost:8080` and go straight to the dashboard.

---

## What You Get

- Real-time dashboard with scan status, recent alerts, and history
- Recursive monitoring of files and directories
- Baseline creation and reset from the UI
- Manual scan trigger
- Telegram alert delivery
- Docker-based deployment with PostgreSQL, API, scanner, and dashboard

---

## Architecture

```text
Host filesystem (read-only mount)
        |
        v
   Scanner container  --->  PostgreSQL
        |                       |
        v                       v
     FastAPI  <------------  Dashboard (nginx + JS SPA)
        |
        v
   Optional Telegram alerts
```

Components:
- `scanner` scans mounted host paths and records changes
- `api` exposes REST and WebSocket endpoints
- `dashboard` serves the SPA and proxies `/api` and `/ws/live`
- `postgres` stores baseline, events, settings, and audit records

---

## Requirements

- Linux host
- Docker Engine + Docker Compose v2
- `git`
- `sudo` access

This project is intended to run on Linux because the scanner mounts the host filesystem directly into the container.

---

## Quick Start

```bash
git clone https://github.com/nkhtmmdv/-FIM_project.git
cd -FIM_project
cp .env.example .env
docker compose up -d --build
```

Then open:

```text
http://localhost:8080
```

In the default configuration, the dashboard should open immediately without a login step.

---

## First Run Checklist

1. Open `http://localhost:8080`
2. Go to `Settings`
3. Click `Create New Baseline`
4. Add any extra files or directories you want to monitor
5. If you add new paths, create the baseline again
6. Optionally configure Telegram alerts

Important:
- Alerts are meaningful only after a baseline exists.
- Directories are monitored recursively.

---

## Default Mode

The repository ships with:

```env
LOCAL_MODE=true
LOCAL_USERNAME=local-user
```

That means:
- the app behaves like a local desktop-style tool;
- all API routes work for one local user automatically;
- the login/register flow is not required for normal use.

If you want to experiment with multi-user auth later, you can switch to:

```env
LOCAL_MODE=false
```

In auth mode, JWT-based login becomes active again and the frontend will show the login page.

---

## Environment Setup

Minimal variables for local mode are already present in `.env.example`.

Typical setup:

```env
POSTGRES_HOST=postgres
POSTGRES_DB=fim
POSTGRES_USER=fim_app
POSTGRES_PASSWORD=ReplaceThisWithAStrongPassword123!
CORS_ORIGINS=*
LOCAL_MODE=true
LOCAL_USERNAME=local-user
API_PORT=8000
HTTP_PORT=8080
SCAN_INTERVAL_SECONDS=120
```

Notes:
- `POSTGRES_PASSWORD` must be set
- `JWT_SECRET` matters only when `LOCAL_MODE=false`
- `HTTP_PORT` controls the dashboard port exposed on the host

---

## Docker Compose Services

`docker-compose.yml` starts four services:

- `postgres` for persistent storage
- `scanner` for filesystem monitoring
- `api` for REST/WebSocket endpoints
- `dashboard` for the browser UI

Start:

```bash
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

See status:

```bash
docker compose ps
```

See logs:

```bash
docker compose logs -f
```

---

## Adding Files To Monitor

Examples:

```text
/etc/passwd
/etc/hosts
/home/kali/important.txt
/root/.bashrc
/opt/myapp/config.json
/var/www/html/index.php
```

How to add them:
1. Open `Settings`
2. Enter the absolute path
3. Choose severity
4. Click `+ Add`
5. Recreate the baseline if needed

Default monitored directories are inserted from `db/init.sql` on first database creation.

---

## Telegram Alerts

Telegram alerts are optional.

Setup steps:
1. Create a bot with `@BotFather`
2. Start a chat with the bot
3. Get your Chat ID from `getUpdates`
4. Open `Settings`
5. Enter bot token and chat ID
6. Click `Save Profile`
7. Click `Test Telegram`

In local mode, this configuration is stored for the single local user.

---

## Dashboard Guide

### Dashboard
- summary counters
- recent alerts
- timeline chart
- next scan indicator

### Alerts
- full alert list
- filters by severity, event type, and path
- acknowledge actions
- CSV export

### History
- scan run history
- per-scan change details

### Settings
- monitored paths
- scan interval and alert toggles
- Telegram configuration
- baseline controls

---

## Security Model

Default mode is designed for a local single user on their own machine.

In that mode:
- data stays local;
- no browser login is required;
- scanner mounts the host filesystem read-only;
- database is internal to Docker;
- Telegram is the only optional external integration.

When `LOCAL_MODE=false`, the project also supports:
- JWT access and refresh tokens
- user registration and login
- password hashing with bcrypt

---

## API Notes

Useful endpoints in local mode:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/app/config` | frontend runtime mode |
| GET | `/api/v1/stats/summary` | dashboard counters |
| GET | `/api/v1/files` | monitored files |
| GET | `/api/v1/alerts` | alert history |
| POST | `/api/v1/files/add` | add monitored path |
| POST | `/api/v1/baseline/create` | create baseline |
| POST | `/api/v1/scan/trigger` | trigger manual scan |
| WS | `/ws/live` | live updates |

In local mode these routes work without manual authentication in the browser.

---

## Troubleshooting

### Dashboard does not open

Check that containers are running:

```bash
docker compose ps
```

### Dashboard opens but shows no data

Check API and scanner logs:

```bash
docker compose logs api
docker compose logs scanner
```

### No alerts appear

Most often, the baseline has not been created yet. Open `Settings` and create it first.

### Changes are not detected for a new path

- make sure the path is absolute;
- make sure it exists on the host;
- recreate the baseline after adding it.

### Port 8080 is busy

Change this in `.env`:

```env
HTTP_PORT=8081
```

Then restart:

```bash
docker compose up -d --build
```

### You want the old login-based behavior

Set:

```env
LOCAL_MODE=false
```

Then restart the stack.

---

## Project Goal

This repository is meant to behave like a usable local application, not just a classroom prototype. The default setup is optimized for reviewers and end users who clone the repo, follow the instructions, and expect the program to run predictably on first launch.
docker compose up -d --force-recreate api
```
→ After changing `JWT_SECRET`, clear browser localStorage (F12 → Application → Local Storage → Clear) and log in again

**No Telegram alerts**
→ Check your token and Chat ID in Settings → press **Test**
→ Make sure you pressed **Start** in your bot chat in Telegram
→ Check that a baseline exists (Settings → Baseline Management)

**Dashboard won't open**
→ Confirm the stack is running: `fim status`
→ Use `http://localhost:8080` (not `https`)

**No alerts when a file changes**
→ Make sure you created a baseline (Settings → Create Baseline)
→ Confirm the file path is listed in Settings → Monitored Files
→ Press **Manual Scan** in Settings for an immediate scan
→ Verify the file exists on the host: `ls -la /path/to/file`

**Added a file but no ADDED alert**
→ After adding a new file to monitor, you must click **Create Baseline** first
→ Then modify the file — the next scan will detect it as `MODIFIED`
→ If you want an `ADDED` alert for a brand-new file: add it to monitoring **before** creating the baseline

**OWNER_CHANGED keeps appearing**
→ This happens when the baseline was created before the scanner ran as root
→ Fix: go to Settings → **Create New Baseline** to reset with correct ownership data

**502 Bad Gateway**
→ Restart all containers: `fim restart`

**Scanner not seeing a file I added**
→ Verify the file exists: `ls /path/to/file`
→ Check scanner sees it: `docker exec fim_project-scanner-1 ls /monitored/path/to/file`
→ The path in monitoring must match the actual host path (e.g. add `/home/kali/file.txt`, not `/monitored/home/kali/file.txt`)

---

## License

MIT — free to use for personal and commercial purposes.
