"""Settings routes for user-configurable options."""
from __future__ import annotations
from typing import Dict
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from auth import current_user
from database import audit, execute, fetch_all, fetch_one

router = APIRouter(prefix='/settings', tags=['settings'])

ALLOWED_KEYS = {
    'telegram_bot_token',
    'telegram_chat_id',
    'smtp_host',
    'smtp_port',
    'smtp_user',
    'smtp_password',
    'smtp_from',
    'alert_email_to',
    'scan_interval_seconds',
    'alert_on_permission_change',
    'alert_on_owner_change',
    'alert_on_new_files',
    'alert_on_deleted_files',
}


class SettingUpdate(BaseModel):
    """A key-value setting update."""
    key: str
    value: str


class SettingsBatch(BaseModel):
    """Multiple settings at once."""
    settings: list[SettingUpdate]


@router.get('')
def get_settings(user=Depends(current_user)):
    """Return all settings as key-value pairs."""
    rows = fetch_all('SELECT key, value FROM settings ORDER BY key')
    return {r['key']: r['value'] for r in rows}


@router.put('')
def update_settings(body: SettingsBatch, request: Request, user=Depends(current_user)):
    """Update one or more settings."""
    for item in body.settings:
        if item.key not in ALLOWED_KEYS:
            continue
        execute(
            'INSERT INTO settings(key, value, updated_at) VALUES(%s, %s, NOW()) '
            'ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()',
            (item.key, item.value)
        )
    audit(
        user['username'], 'settings.update',
        ','.join(s.key for s in body.settings),
        request.client.host if request.client else None
    )
    return {'ok': True}


@router.post('/test-telegram')
def test_telegram(user=Depends(current_user)):
    """Send a test Telegram message using stored credentials."""
    import requests as req
    token = _get('telegram_bot_token')
    chat = _get('telegram_chat_id')
    if not token or not chat:
        return {'ok': False, 'error': 'Telegram not configured. Set token and chat ID in Settings.'}
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    text = '\U0001f6a8 FIM Sentinel \u2014 Test alert\n\nIf you see this, Telegram integration is working!'
    try:
        r = req.post(url, json={'chat_id': chat, 'text': text}, timeout=10)
        r.raise_for_status()
        return {'ok': True}
    except req.RequestException as exc:
        return {'ok': False, 'error': str(exc)}


def _get(key: str) -> str:
    """Get a setting value from DB."""
    row = fetch_one('SELECT value FROM settings WHERE key=%s', (key,))
    return row['value'] if row else ''
