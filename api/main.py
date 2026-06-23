"""FastAPI application for FIM."""
import asyncio
import os, signal, time
from collections import defaultdict
from typing import Set
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from auth import create_token, current_user, ensure_local_user, is_local_mode, validate_secrets, verify_password
from jose import JWTError, jwt
from database import fetch_one, execute, init_pool
from models.alert import LoginRequest, TokenRefresh
from routes import files, alerts, baseline, stats, settings, profile
APP_VERSION = '1.0.0'
sockets: Set[WebSocket] = set()
_sockets_lock: asyncio.Lock = asyncio.Lock()
_login_attempts: dict = defaultdict(list)
_LOGIN_MAX = 10
_LOGIN_WINDOW = 60
origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS', '*').split(',') if origin.strip()]
allow_credentials = origins != ['*']
app = FastAPI(title='FIM API', version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def security_and_logging(request: Request, call_next):
    """Add security headers and request timing."""
    start = time.time()
    response = await call_next(request)
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Process-Time-ms'] = str(int((time.time() - start) * 1000))
    return response


@app.on_event('startup')
def startup() -> None:
    """Initialise app dependencies."""
    validate_secrets()
    init_pool()
    ensure_local_user()


@app.get('/api/v1/app/config')
def app_config():
    """Expose runtime mode to the SPA."""
    return {
        'local_mode': is_local_mode(),
        'auth_enabled': not is_local_mode(),
        'version': APP_VERSION,
    }


@app.post('/api/v1/auth/login')
async def login(request: Request, body: LoginRequest):
    """Authenticate and return access plus refresh tokens."""
    if is_local_mode():
        username = current_user()['username']
        return {
            'access_token': create_token(username, 'access', 60),
            'refresh_token': create_token(username, 'refresh', 7 * 1440),
            'token_type': 'bearer',
        }
    ip = request.client.host if request.client else 'unknown'
    now = time.time()
    attempts = _login_attempts[ip]
    _login_attempts[ip] = [t for t in attempts if now - t < _LOGIN_WINDOW]
    if len(_login_attempts[ip]) >= _LOGIN_MAX:
        raise HTTPException(status_code=429, detail='too many login attempts, try again later')
    _login_attempts[ip].append(now)
    row = fetch_one('SELECT * FROM users WHERE username=%s', (body.username,))
    if not row or not verify_password(body.password, row['password_hash']):
        raise HTTPException(status_code=401, detail='bad credentials')

    execute('UPDATE users SET last_login=NOW() WHERE username=%s', (body.username,))
    return {
        'access_token': create_token(
            body.username,
            'access',
            int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60')),
        ),
        'refresh_token': create_token(
            body.username,
            'refresh',
            int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', '7')) * 1440,
        ),
        'token_type': 'bearer',
    }


@app.post('/api/v1/auth/refresh')
def refresh(body: TokenRefresh):
    """Refresh an access token."""
    if is_local_mode():
        username = current_user()['username']
        return {'access_token': create_token(username, 'access', 60)}
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(body.refresh_token, os.getenv('JWT_SECRET', ''), algorithms=['HS256'])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail='bad refresh token') from exc

    if payload.get('type') != 'refresh':
        raise HTTPException(status_code=401, detail='bad refresh token')

    return {
        'access_token': create_token(
            payload['sub'],
            'access',
            int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60')),
        )
    }


@app.websocket('/ws/live')
async def live(ws: WebSocket):
    """Accept authenticated live WebSocket clients."""
    token = ws.query_params.get('token', '')
    if not is_local_mode():
        try:
            payload = jwt.decode(token, os.getenv('JWT_SECRET', ''), algorithms=['HS256'])
            if payload.get('type') != 'access':
                await ws.close(code=4001)
                return
        except JWTError:
            await ws.close(code=4001)
            return

    await ws.accept()
    async with _sockets_lock:
        sockets.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        async with _sockets_lock:
            sockets.discard(ws)


app.include_router(files.router, prefix='/api/v1')
app.include_router(alerts.router, prefix='/api/v1')
app.include_router(baseline.router, prefix='/api/v1')
app.include_router(stats.router, prefix='/api/v1')
app.include_router(settings.router, prefix='/api/v1')
app.include_router(profile.router)


def _send_api_shutdown_alert():
    """Send emergency alert when API shuts down."""
    try:
        import requests
        from database import fetch_all
        rows = fetch_all(
            "SELECT telegram_bot_token, telegram_chat_id FROM users "
            "WHERE telegram_bot_token IS NOT NULL AND telegram_bot_token != '' "
            "  AND telegram_chat_id  IS NOT NULL AND telegram_chat_id  != ''"
        )
        import socket
        try:
            host = socket.gethostname()
        except Exception:
            host = 'unknown'
        from datetime import datetime, timezone
        text = (
            f"🛑 *FIM API SHUTDOWN ALERT* 🛑\n\n"
            f"🔴 API service was *stopped*\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"🖥 Host: `{host}`\n\n"
            f"⚠️ If this was not planned, investigate immediately!"
        )
        for row in rows:
            tok = (row['telegram_bot_token'] or '').strip()
            chat = (row['telegram_chat_id'] or '').strip()
            if tok and chat:
                try:
                    requests.post(
                        f'https://api.telegram.org/bot{tok}/sendMessage',
                        json={'chat_id': chat, 'text': text, 'parse_mode': 'Markdown'},
                        timeout=5
                    )
                except Exception:
                    pass
    except Exception:
        pass


def _term(signum: int, frame: object) -> None:
    """Handle termination signal with alert."""
    _send_api_shutdown_alert()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, _term)
signal.signal(signal.SIGINT, _term)
