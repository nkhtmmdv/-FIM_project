"""User profile and registration routes."""
from __future__ import annotations
import os
import requests as req
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from auth import current_user, hash_password, verify_password
from database import audit, execute, fetch_one
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(tags=['profile'])


class RegisterRequest(BaseModel):
    """New user registration body."""
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    telegram_chat_id: str = Field(default='')
    telegram_bot_token: str = Field(default='')


class ProfileUpdate(BaseModel):
    """Update profile fields."""
    telegram_chat_id: str = Field(default='')
    telegram_bot_token: str = Field(default='')
    current_password: str = Field(default='')
    new_password: str = Field(default='')


@router.post('/api/v1/auth/register')
@limiter.limit('3/minute')
def register(body: RegisterRequest, request: Request):
    """Register a new user account."""
    existing = fetch_one('SELECT id FROM users WHERE username=%s', (body.username,))
    if existing:
        raise HTTPException(status_code=409, detail='username already taken')
    execute(
        'INSERT INTO users(username, password_hash, role, telegram_chat_id, telegram_bot_token) '
        'VALUES(%s, %s, %s, %s, %s)',
        (body.username, hash_password(body.password), 'analyst',
         body.telegram_chat_id, body.telegram_bot_token)
    )
    audit(body.username, 'user.register', None,
          request.client.host if request.client else None)
    return {'ok': True}


@router.get('/api/v1/auth/profile')
def get_profile(user=Depends(current_user)):
    """Return the current user's profile (without password hash)."""
    row = fetch_one(
        'SELECT username, role, created_at, last_login, telegram_chat_id, telegram_bot_token '
        'FROM users WHERE username=%s',
        (user['username'],)
    )
    if not row:
        raise HTTPException(status_code=404, detail='user not found')
    # Mask token: show only last 6 chars for display
    token = row.get('telegram_bot_token') or ''
    row['telegram_bot_token_set'] = bool(token)
    row['telegram_bot_token'] = ('*' * (len(token) - 6) + token[-6:]) if len(token) > 6 else token
    return row


@router.put('/api/v1/auth/profile')
def update_profile(body: ProfileUpdate, request: Request, user=Depends(current_user)):
    """Update Telegram settings and optionally change password."""
    row = fetch_one('SELECT password_hash FROM users WHERE username=%s', (user['username'],))
    if not row:
        raise HTTPException(status_code=404, detail='user not found')

    # Password change requested
    if body.new_password:
        if not body.current_password:
            raise HTTPException(status_code=400, detail='current_password required to set new password')
        if not verify_password(body.current_password, row['password_hash']):
            raise HTTPException(status_code=403, detail='current password is wrong')
        if len(body.new_password) < 8:
            raise HTTPException(status_code=400, detail='new password must be at least 8 characters')
        execute('UPDATE users SET password_hash=%s WHERE username=%s',
                (hash_password(body.new_password), user['username']))

    # Update Telegram credentials (only overwrite if non-empty provided)
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
    """Send a test Telegram message to the current user's chat."""
    row = fetch_one(
        'SELECT telegram_bot_token, telegram_chat_id FROM users WHERE username=%s',
        (user['username'],)
    )
    if not row:
        raise HTTPException(status_code=404, detail='user not found')

    token = row.get('telegram_bot_token') or ''
    chat = row.get('telegram_chat_id') or ''

    # Fallback to global bot token from settings table if user has none
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
