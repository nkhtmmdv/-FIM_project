"""Alert delivery for Telegram and SMTP.

Reads credentials from user profiles in PostgreSQL and dispatches
alerts only to users who have configured their own Telegram bot.
"""
from __future__ import annotations
import logging
import os
import smtplib
import socket
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, List

import requests

TELEGRAM_URL = 'https://api.telegram.org/bot{token}/sendMessage'
MONITOR_ROOT = os.getenv('MONITOR_ROOT', '/monitored')

def _display_path(p: str) -> str:
    """Strip internal /monitored prefix so users see real host paths."""
    return p[len(MONITOR_ROOT):] if p and p.startswith(MONITOR_ROOT + '/') else p

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
    path = _display_path(str(event.get('file_path', '')))
    kind = event['event_type']
    icons = {'MODIFIED': '\u270f\ufe0f', 'DELETED': '\U0001f5d1', 'ADDED': '\U0001f195',
             'PERMISSIONS_CHANGED': '\U0001f512', 'OWNER_CHANGED': '\U0001f464'}
    icon = icons.get(kind, '\u26a0\ufe0f')
    sev  = event.get('severity', 'INFO')
    sev_icon = {'CRITICAL': '\U0001f534', 'WARNING': '\U0001f7e1', 'INFO': '\U0001f535'}.get(sev, '\u26aa')
    lines = [
        f"{icon} *FIM ALERT* {sev_icon} {sev}",
        f"\U0001f4c1 `{path}`",
        f"\U0001f504 Event: *{kind}*",
        f"\u23f1 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"\U0001f5a5 Host: {host}",
    ]
    if event.get('hash_before') and event.get('hash_after'):
        lines.append(f"Hash: `{str(event.get('hash_before',''))[:16]}...` \u2192 `{str(event.get('hash_after',''))[:16]}...`")
    return "\n".join(lines)


def send_email(events: List[Dict[str, object]]) -> None:
    """Send optional SMTP email alert."""
    smtp_host = _cfg('smtp_host', 'SMTP_HOST')
    target = _cfg('alert_email_to', 'ALERT_EMAIL_TO')
    if not smtp_host or not target or not events:
        return
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
        password = _cfg('smtp_password', 'SMTP_PASSWORD')
        if user:
            if password:
                smtp.login(user, password)
            else:
                logging.warning('[alerter] SMTP user configured without password; skipping auth')
        smtp.send_message(msg)


def dispatch(events: List[Dict[str, object]]) -> None:
    """Dispatch Telegram alerts using credentials from user profiles only."""
    if not events:
        return

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
                    json={'chat_id': chat, 'text': text, 'parse_mode': 'Markdown'},
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
