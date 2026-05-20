"""Alert delivery for Telegram and SMTP.

Reads credentials from the PostgreSQL settings table first,
falling back to environment variables if not found in the DB.
This allows each deployment to configure alerts through the dashboard.
"""
from __future__ import annotations
import os, smtplib, time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, List, Optional
import requests

TELEGRAM_URL = 'https://api.telegram.org/bot{token}/sendMessage'

def _load_settings() -> Dict[str, str]:
    """Load fresh settings directly from DB on every call."""
    try:
        import db as scanner_db
        with scanner_db.conn_cursor() as cur:
            cur.execute('SELECT key, value FROM settings')
            return {r['key']: r['value'] for r in cur.fetchall()}
    except Exception:
        pass
    return {}


def _cfg(key: str, env_key: str, default: str = '') -> str:
    """Get config: DB settings first, then env, then default."""
    settings = _load_settings()
    # Always prioritize non-empty DB value over environment variable
    val = settings.get(key)
    if val and val.strip():
        return val.strip()
    return os.getenv(env_key, default).strip()


def format_alert(event: Dict[str, object], host: str) -> str:
    """Build the Telegram alert body."""
    lines = [
        f"\U0001f6a8 FIM ALERT \u2014 {event['event_type']}",
        f"\U0001f4c1 File: {event['file_path']}",
        f"\U0001f504 Change: {event['event_type']}",
        f"\u23f1 Detected: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"\U0001f4ca Before: {event.get('hash_before')} \u2192 After: {event.get('hash_after')}",
        f"\U0001f464 Owner: {event.get('owner_after') or event.get('owner_before')}",
        f"\U0001f512 Permissions: {event.get('permissions_before')} \u2192 {event.get('permissions_after')}",
        f"\U0001f4e6 Size: {event.get('size_before')} \u2192 {event.get('size_after')}",
        f"\U0001f5a5 Host: {host}",
    ]
    return "\n".join(lines)


def send_telegram(events: List[Dict[str, object]]) -> None:
    """Send batched Telegram alerts with exponential backoff."""
    token = _cfg('telegram_bot_token', 'TELEGRAM_BOT_TOKEN')
    chat = _cfg('telegram_chat_id', 'TELEGRAM_CHAT_ID')
    if not token or not chat or not events:
        return
    host = socket.gethostname()
    chunks = [
        '\n\n'.join(format_alert(e, host) for e in events[i:i + 5])
        for i in range(0, len(events), 5)
    ]
    for text in chunks:
        for attempt in range(4):
            try:
                r = requests.post(
                    TELEGRAM_URL.format(token=token),
                    json={'chat_id': chat, 'text': text},
                    timeout=10
                )
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)


def send_email(events: List[Dict[str, object]]) -> None:
    """Send optional SMTP email alert."""
    smtp_host = _cfg('smtp_host', 'SMTP_HOST')
    target = _cfg('alert_email_to', 'ALERT_EMAIL_TO')
    if not smtp_host or not target or not events:
        return
    import socket
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = 'unknown'
    msg = EmailMessage()
    msg['Subject'] = f'FIM alerts: {len(events)} change(s)'
    msg['From'] = _cfg('smtp_from', 'SMTP_FROM', 'fim@example.com')
    msg['To'] = target
    msg.set_content('\n\n'.join(format_alert(e, hostname) for e in events))
    with smtplib.SMTP(smtp_host, int(_cfg('smtp_port', 'SMTP_PORT', '587')), timeout=15) as smtp:
        smtp.starttls()
        user = _cfg('smtp_user', 'SMTP_USER')
        if user:
            smtp.login(user, _cfg('smtp_password', 'SMTP_PASSWORD'))
        smtp.send_message(msg)


def dispatch(events: List[Dict[str, object]]) -> None:
    """Dispatch alerts per-user (personal Telegram) with global fallback."""
    if not events:
        return

    import logging
    try:
        import db as scanner_db
        owner_map = scanner_db.file_owner_telegram()   # file_path -> {token, chat_id}
        glob = scanner_db.global_telegram()            # global fallback
    except Exception as e:
        logging.error(f'[alerter] DB error loading creds: {e}')
        owner_map = {}
        glob = {}

    global_token = glob.get('telegram_bot_token') or _cfg('telegram_bot_token', 'TELEGRAM_BOT_TOKEN')
    global_chat  = glob.get('telegram_chat_id')   or _cfg('telegram_chat_id',   'TELEGRAM_CHAT_ID')

    # Group events by (token, chat_id) destination
    buckets: Dict[tuple, List[Dict[str, object]]] = {}
    no_personal: List[Dict[str, object]] = []

    for ev in events:
        path = ev['file_path']
        # Normalize container path to DB path style (remove /monitored prefix if exists)
        if path.startswith('/monitored'):
            normalized_path = path[10:] # len('/monitored') = 10
        else:
            normalized_path = path

        creds = owner_map.get(normalized_path) or owner_map.get(path)
        if creds and creds.get('chat_id'):
            tok = creds['token'] or global_token
            key = (tok, creds['chat_id'])
            buckets.setdefault(key, []).append(ev)
        else:
            no_personal.append(ev)

    # Send to each personal destination
    for (tok, chat), evs in buckets.items():
        _send_to(tok, chat, evs)

    # Remaining events: try any user with Telegram first, then global fallback
    if no_personal:
        sent = False
        # 1) Try any user that has Telegram credentials configured
        try:
            import db as scanner_db
            with scanner_db.conn_cursor() as cur:
                cur.execute(
                    "SELECT telegram_bot_token, telegram_chat_id FROM users "
                    "WHERE telegram_chat_id IS NOT NULL AND telegram_chat_id != '' "
                    "LIMIT 1"
                )
                row = cur.fetchone()
                if row and row['telegram_bot_token'] and row['telegram_chat_id']:
                    _send_to(row['telegram_bot_token'], row['telegram_chat_id'], no_personal)
                    sent = True
        except Exception:
            pass
        # 2) Fallback to global if user send didn't happen
        if not sent and global_token and global_chat:
            _send_to(global_token, global_chat, no_personal)

    send_email(events)


def _send_to(token: str, chat: str, events: List[Dict[str, object]]) -> None:
    """Send batched alerts to a single Telegram destination."""
    import logging, socket
    if not token or not chat:
        logging.warning(f'[alerter] _send_to skipped: token={bool(token)} chat={bool(chat)}')
        return
    logging.info(f'[alerter] sending to chat={chat} token_prefix={token[:12]}...')
    try:
        host = socket.gethostname()
    except Exception:
        host = 'unknown'
    chunks = [
        '\n\n'.join(format_alert(e, host) for e in events[i:i + 5])
        for i in range(0, len(events), 5)
    ]
    for text in chunks:
        for attempt in range(4):
            try:
                r = requests.post(
                    TELEGRAM_URL.format(token=token),
                    json={'chat_id': chat, 'text': text},
                    timeout=10
                )
                r.raise_for_status()
                logging.info(f'[alerter] Telegram sent OK to chat={chat}')
                break
            except requests.RequestException as e:
                logging.error(f'[alerter] Telegram error attempt {attempt}: {e}')
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
