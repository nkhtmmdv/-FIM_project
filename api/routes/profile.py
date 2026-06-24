"""User profile routes (local mode — no login)."""
from __future__ import annotations
import requests as req
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from auth import current_user
from database import audit, execute, fetch_one

router = APIRouter(tags=['profile'])


class ProfileUpdate(BaseModel):
    """Update profile fields."""
    telegram_chat_id: str = Field(default='')
    telegram_bot_token: str = Field(default='')


@router.get('/api/v1/auth/profile')
def get_profile(user=Depends(current_user)):
    """Return the local user's profile (without password hash)."""
    row = fetch_one(
        'SELECT username, role, created_at, last_login, telegram_chat_id, telegram_bot_token '
        'FROM users WHERE username=%s',
        (user['username'],)
    )
    if not row:
        raise HTTPException(status_code=404, detail='user not found')
    token = row.get('telegram_bot_token') or ''
    row['telegram_bot_token_set'] = bool(token)
    row['telegram_bot_token'] = ('*' * (len(token) - 6) + token[-6:]) if len(token) > 6 else token
    return row


@router.put('/api/v1/auth/profile')
def update_profile(body: ProfileUpdate, request: Request, user=Depends(current_user)):
    """Update Telegram settings."""
    row = fetch_one('SELECT id FROM users WHERE username=%s', (user['username'],))
    if not row:
        raise HTTPException(status_code=404, detail='user not found')

    if body.telegram_chat_id != '' or body.telegram_bot_token != '':
        if body.telegram_chat_id:
            execute('UPDATE users SET telegram_chat_id=%s WHERE username=%s',
                    (body.telegram_chat_id, user['username']))
        if body.telegram_bot_token and not body.telegram_bot_token.startswith('*'):
            execute('UPDATE users SET telegram_bot_token=%s WHERE username=%s',
                    (body.telegram_bot_token, user['username']))

    audit(user['username'], 'profile.update', None,
          request.client.host if request.client else None)
    return {'ok': True}


@router.post('/api/v1/auth/test-telegram')
def test_telegram_personal(user=Depends(current_user)):
    """Send a test Telegram message to the local user's chat."""
    row = fetch_one(
        'SELECT telegram_bot_token, telegram_chat_id FROM users WHERE username=%s',
        (user['username'],)
    )
    if not row:
        raise HTTPException(status_code=404, detail='user not found')

    token = row.get('telegram_bot_token') or ''
    chat = row.get('telegram_chat_id') or ''

    if not token:
        cfg = fetch_one("SELECT value FROM settings WHERE key='telegram_bot_token'")
        token = cfg['value'] if cfg else ''

    if not token or not chat:
        return {
            'ok': False,
            'error': 'Set your Bot Token and Chat ID in Profile first.'
        }

    url = f'https://api.telegram.org/bot{token}/sendMessage'
    text = (
        f'\U0001f6a8 FIM Sentinel \u2014 Test alert\n\n'
        f'Hello, {user["username"]}!\n'
        f'Your personal Telegram alerts are configured correctly.'
    )
    try:
        r = req.post(url, json={'chat_id': chat, 'text': text}, timeout=10)
        r.raise_for_status()
        return {'ok': True}
    except req.RequestException as exc:
        return {'ok': False, 'error': str(exc)}
