# FIM Sentinel

> **File Integrity Monitor** — real-time protection of your Linux system against unauthorized file changes.

FIM Sentinel watches your critical files and any files you add, instantly detects any modification, and sends alerts to Telegram. Every user runs it **completely locally** — your data never leaves your machine.

---

## How It Works

```
 Your files (/etc/passwd, /home/user/file.txt, /root/.bashrc, ...)
          │
   [ Scanner ] ──── every N seconds ────► compares against baseline
          │                                        │
    change detected?                         everything OK?
          │                                        │
    ► Telegram alert                    ► waits for next scan silently
    ► stored in database
    ► shown in dashboard
```

**Components:**
- **Scanner** — hashes files, compares to baseline, dispatches alerts
- **API** — JWT-secured REST + WebSocket endpoints
- **Dashboard** — dark-mode web UI with live updates, charts, and CSV export
- **PostgreSQL** — stores baseline, events, users, and full audit log

All components run in Docker. The database is isolated on an internal network with no internet access. The scanner mounts the **entire host filesystem** read-only so it can monitor any file you add.

---

## Requirements

- Linux (Debian, Ubuntu, Kali, CentOS, etc.)
- [Docker](https://docs.docker.com/engine/install/) + Docker Compose v2
- `git`, `openssl` (usually pre-installed)
- Root access (sudo)

---

## Installation

### One-Command Install (recommended)

```bash
# 1. Clone the repository
git clone https://github.com/nkhtmmdv/-FIM_project.git
cd -FIM_project

# 2. Run the installer (once)
sudo bash install.sh
```

The installer automatically:
- Generates **unique random passwords and secrets** for your machine (no two installs share credentials)
- Registers **autostart** on system boot via systemd
- Launches all containers
- Creates the `fim` command for control from anywhere in the terminal
- Configures the browser to open the dashboard automatically on desktop login

Once done, open your browser at **`http://localhost:8080`**.

### Manual Install (without installer)

```bash
git clone https://github.com/nkhtmmdv/-FIM_project.git
cd -FIM_project

# Generate secrets
cp .env.example .env
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" .env

# Start
docker compose up -d --build
```

---

## First Run

1. Open **`http://localhost:8080`**
2. Click **Register** and create your account
3. Log in
4. Go to **Settings** → click **Create Baseline**
   - This snapshots the current state of all monitored files as "normal"
   - Must be done before any alerts can fire
5. Add files or directories to monitor in **Settings → Monitored Files**
6. Configure Telegram alerts (see below)

---

## Adding Files to Monitor

You can monitor **any file or directory** on your system — not just system files.

**Examples of paths you can add:**
```
/etc/passwd
/etc/hosts
/home/kali/important.txt
/root/.bashrc
/opt/myapp/config.json
/var/www/html/index.php
```

**How to add:**
1. Go to **Settings → Monitored Files**
2. Type the full absolute path (e.g. `/home/kali/myfile.txt`)
3. Choose severity: `CRITICAL`, `WARNING`, or `INFO`
4. Click **+ Add**
5. After adding, click **Settings → Create Baseline** so the scanner records the current state

> **Note:** Directories are scanned recursively — adding `/home/kali` will monitor all files inside it.

---

## Telegram Alert Setup

1. Open Telegram → find **@BotFather** → send `/newbot`
2. Choose a display name (e.g. `My FIM Bot`) and a username ending in `bot`
3. BotFather replies with a token like `123456789:AAF...` — copy it
4. Start a chat with your new bot (find it in Telegram, press **Start**)
5. Get your Chat ID — open this URL in a browser:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Find `"chat":{"id": 123456789}` — that number is your Chat ID
6. In the dashboard go to **Settings → Telegram** → paste the token and Chat ID → click **Save** → **Test**

Alerts fire after **every scan** for unacknowledged changes.

---

## Managing FIM Sentinel

After installation, use the `fim` command from anywhere in the terminal:

```bash
fim status    # show running container status
fim start     # start all containers
fim stop      # stop all containers
fim restart   # restart all containers
fim logs      # stream live logs
fim update    # pull latest version and rebuild
```

### Updating

```bash
fim update
```

Pulls the latest version from git and rebuilds all containers automatically.

> **After an update:** if `JWT_SECRET` in your `.env` is shorter than 64 characters, the API will not start.
> Fix: `sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env && docker compose up -d --force-recreate api`

---

## Dashboard Guide

### Dashboard (home)
- File count, alert count, last scan time
- Countdown timer to the next scan
- Recent events feed
- 24-hour alert timeline chart

### Alerts
- Full list of all detected changes
- Filter by severity, event type, or file path
- **Acknowledge** button — marks the alert as reviewed; it will no longer appear in the active alerts list
- Export to CSV

### History
- Full scan history with per-scan details: files scanned, changes found, duration

### Settings

| Section | Description |
|---|---|
| Monitored Files | Add / remove files and directories to watch |
| Baseline Management | Create or reset the baseline snapshot |
| Telegram | Your personal bot token and Chat ID for alerts |
| Scan Interval | How often to scan (in seconds, minimum 10) |

---

## Alert Types

| Event | Description |
|---|---|
| `ADDED` | A new file appeared that was not in the baseline |
| `MODIFIED` | File content (hash) changed |
| `DELETED` | A monitored file was removed |
| `PERMISSIONS_CHANGED` | File permissions changed |
| `OWNER_CHANGED` | File ownership changed |
| `MODIFIED_WITH_OWNER_CHANGE` | Content and ownership both changed |

**Alert behaviour:**
- Telegram fires for each new unacknowledged change after every scan
- Pressing **Acknowledge** marks the alert as reviewed — it moves out of the active list
- After acknowledging, press **Create Baseline** to make the new state the new normal

**Severity levels:**

| Level | Colour | Default for |
|---|---|---|
| CRITICAL | Red | `/bin`, `/sbin`, `/etc`, `/root` |
| WARNING | Yellow | `/home`, `/var/log`, `/opt` |
| INFO | Blue | Everything else |

---

## Security

- **Data** — stored locally only; never sent to any external server (except Telegram alerts you configure)
- **Credentials** — each install generates unique random passwords via `openssl rand`
- **JWT** — HS256, minimum 64-character secret, 1-hour access tokens, 7-day refresh tokens
- **User passwords** — bcrypt, cost factor 12, maximum 72 bytes
- **Rate limiting** — login endpoint blocks after 10 failed attempts per IP per minute
- **Filesystem** — scanner mounts host files read-only; cannot modify them
- **SQL** — parameterised queries everywhere; SQL injection is not possible
- **Audit log** — every user action (login, file add/remove, baseline reset, alert acknowledge) is recorded with IP address

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Authenticate, receive JWT tokens |
| POST | `/api/v1/auth/register` | Create a new account |
| GET | `/api/v1/files` | List monitored files |
| POST | `/api/v1/files/add` | Add a file or directory to monitoring |
| DELETE | `/api/v1/files/{path}` | Remove a file from monitoring |
| GET | `/api/v1/alerts` | List alerts (filterable by severity, type, path) |
| PUT | `/api/v1/alerts/{id}/acknowledge` | Acknowledge an alert |
| POST | `/api/v1/baseline/create` | Create a new baseline |
| GET | `/api/v1/baseline/status` | Baseline metadata |
| POST | `/api/v1/scan/trigger` | Trigger an immediate scan |
| GET | `/api/v1/stats/summary` | Dashboard summary counters |
| WS | `/ws/live` | Real-time event stream |

All requests except `login` and `register` require:
```
Authorization: Bearer <your_token>
```

---

## Troubleshooting

**Cannot log in**
→ Check containers are running: `fim status`
→ View API logs: `docker logs fim_project-api-1 --tail 30`
→ If you see `JWT_SECRET must be at least 64 characters`:
```bash
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
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
