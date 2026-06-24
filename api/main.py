"""FastAPI application for FIM."""
import asyncio
import atexit
import os
import threading
import time
from typing import Set
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from auth import ensure_local_user, validate_secrets
from database import fetch_all, init_pool
from routes import files, alerts, baseline, stats, settings, profile
APP_VERSION = '1.0.0'
sockets: Set[WebSocket] = set()
_sockets_lock: asyncio.Lock = asyncio.Lock()
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
    for attempt in range(15):
        try:
            ensure_local_user()
            return
        except Exception:
            if attempt >= 14:
                raise
            time.sleep(2)


@app.get('/api/v1/health/live')
def health_live():
    """Liveness probe for Docker (no database required)."""
    return {'ok': True}


@app.websocket('/ws/live')
async def live(ws: WebSocket):
    """Accept live WebSocket clients."""
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


def _shutdown_alert_async() -> None:
    """Best-effort shutdown alert without blocking container stop."""
    threading.Thread(target=_send_api_shutdown_alert, daemon=True).start()


atexit.register(_shutdown_alert_async)
