# FIM Sentinel

> **File Integrity Monitor** — real-time protection of your Linux system against unauthorized file changes.

FIM Sentinel watches your critical files, instantly detects any modification, and sends alerts to Telegram. Every user runs it **completely locally** — your data never leaves your machine.

---

## How It Works

```
 Your files (/etc/passwd, /etc/hosts, ...)
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

All components run in Docker. The database is isolated on an internal network with no internet access.

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
- Generates **unique random passwords** for your machine (no two installs share credentials)
- Registers **autostart** on system boot via systemd
- Launches all containers
- Creates the `fim` command for control from anywhere in the terminal
- Configures the browser to open the dashboard automatically on desktop login

Once done, open your browser at `http://localhost:8080`.

---

## First Run

1. Open `http://localhost:8080`
2. Click **Register** and create your account
3. Log in
4. Go to **Settings** → click **Create Baseline** (snapshots the current state of your files as "normal")
5. Add files to monitor in **Settings** → Monitored Files (e.g. `/etc/passwd`)
6. Configure Telegram alerts (see below)

---

## Telegram Alert Setup

1. Open Telegram → find **@BotFather** → send `/newbot`
2. Choose a display name (e.g. `My FIM Bot`) and a username ending in `bot`
3. BotFather replies with a token like `123456789:AAF...` — copy it
4. Start a chat with your new bot (find it in Telegram, press Start)
5. Get your Chat ID — open this in a browser:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Find `"chat":{"id": 123456789}` — that number is your Chat ID
6. In the dashboard go to **Settings** → paste the token and Chat ID → click **Save** → **Test**

Alerts fire after **every scan** until you press **Acknowledge**.

---

## Managing FIM Sentinel

After installation, use the `fim` command from anywhere in the terminal:

```bash
fim status    # show running status
fim start     # start all containers
fim stop      # stop all containers
fim restart   # restart all containers
fim logs      # stream live logs
fim update    # pull latest version and rebuild
```

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
- **Acknowledge** button — marks the change as reviewed and saves the new state as the new baseline
- Export to CSV

### History
- Full scan history
- Per-scan details: files scanned, changes found, duration

### Settings

| Section | Description |
|---|---|
| Monitored Files | Add / remove files to watch (type the path as `/etc/passwd`) |
| Baseline Management | Create or reset the baseline snapshot |
| Telegram | Your personal bot token and Chat ID |
| SMTP | Email alert configuration |
| Scan Interval | How often to scan (in seconds) |

---

## Alert Behaviour

| Event | Result |
|---|---|
| File modified | Telegram alert fires after **every scan** |
| Acknowledge pressed | New state saved as baseline → alerts stop |
| File modified again | Telegram fires again after every scan |
| File deleted | `DELETED` alert |
| New file appears | `ADDED` alert |
| Permissions changed | `PERMISSIONS_CHANGED` alert |

**Severity levels:**

| Level | Colour | Use for |
|---|---|---|
| CRITICAL | Red | Critical system files |
| WARNING | Yellow | Important config files |
| INFO | Blue | Everything else |

---

## Security

- **Data** — stored locally only; never sent to any external server
- **Credentials** — each install generates unique random passwords via `openssl rand`
- **JWT** — HS256, 1-hour access tokens, 7-day refresh tokens
- **User passwords** — bcrypt, cost factor 12
- **Network** — PostgreSQL and scanner are isolated on an internal Docker network with no internet
- **Filesystem** — scanner mounts host files read-only; cannot write to them
- **SQL** — parameterised queries everywhere; SQL injection is not possible
- **Audit log** — every user action (login, file add/remove, baseline reset, alert acknowledge) is recorded

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Authenticate, receive JWT tokens |
| POST | `/api/v1/auth/register` | Create a new account |
| GET | `/api/v1/files` | List monitored files |
| POST | `/api/v1/files/add` | Add a file to monitoring |
| DELETE | `/api/v1/files/{path}` | Remove a file from monitoring |
| GET | `/api/v1/alerts` | List alerts (filterable) |
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
→ View logs for errors: `fim logs`

**No Telegram alerts**
→ Check your token and Chat ID in Settings → press **Test**
→ Make sure you started a chat with your bot in Telegram first

**Dashboard won't open**
→ Confirm the stack is running: `fim status`
→ Use `http://localhost:8080` (not `https`)

**No alerts when a file changes**
→ Make sure you created a baseline (Settings → Create Baseline)
→ Confirm the file is listed in Monitored Files
→ Press **Manual Trigger** in the dashboard for an immediate scan

**502 Bad Gateway**
→ Restart all containers: `fim restart`

---

## Updating

```bash
fim update
```

Pulls the latest version from git and rebuilds all containers automatically.

---

## License

MIT — free to use for personal and commercial purposes.
