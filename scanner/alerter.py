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
    """Dispatch Telegram alerts using credentials from user profiles only."""
    if not events:
        return

    import logging
    sent = False
    try:
        import db as scanner_db
        with scanner_db.conn_cursor() as cur:
            cur.execute(
                "SELECT telegram_bot_token, telegram_chat_id FROM users "
                "WHERE telegram_bot_token IS NOT NULL AND telegram_bot_token != '' "
                "  AND telegram_chat_id  IS NOT NULL AND telegram_chat_id  != ''"
            )
            rows = cur.fetchall()
    except Exception as e:
        logging.error(f'[alerter] DB error loading user creds: {e}')
        rows = []

    for row in rows:
        tok  = (row['telegram_bot_token'] or '').strip()
        chat = (row['telegram_chat_id']   or '').strip()
        if tok and chat:
            logging.info(f'[alerter] dispatch to chat={chat} token_prefix={tok[:12]}...')
            _send_to(tok, chat, events)
            sent = True

    if not sent:
        logging.warning('[alerter] No Telegram credentials in user profiles — alert not sent via Telegram.')

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
                    logging.error(f'[alerter] All retries failed for chat={chat}, giving up.')
                    return
                time.sleep(2 ** attempt)
