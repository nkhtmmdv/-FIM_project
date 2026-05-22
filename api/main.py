"""FastAPI application for FIM."""
import os, signal, time
from typing import Set
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from auth import create_token, current_user, validate_secrets, verify_password
from jose import JWTError, jwt
from database import fetch_one, execute, init_pool
from models.alert import LoginRequest, TokenRefresh
from routes import files, alerts, baseline, stats, settings, profile
APP_VERSION='1.0.0'; sockets:Set[WebSocket]=set(); limiter=Limiter(key_func=get_remote_address)
app=FastAPI(title='FIM API',version=APP_VERSION); app.state.limiter=limiter; app.add_middleware(SlowAPIMiddleware); app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','*').split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.middleware('http')
async def security_and_logging(request:Request, call_next):
    """Add security headers and request timing."""
    start=time.time(); response=await call_next(request); response.headers['Content-Security-Policy']="default-src 'self'"; response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'; response.headers['X-Frame-Options']='DENY'; response.headers['X-Content-Type-Options']='nosniff'; response.headers['X-Process-Time-ms']=str(int((time.time()-start)*1000)); return response
@app.on_event('startup')
def startup()->None:
    """Initialise app dependencies."""
    validate_secrets(); init_pool()
@app.post('/api/v1/auth/login')
@limiter.limit('20/minute')
async def login(request:Request, body:LoginRequest):
    """Authenticate and return access plus refresh tokens."""
    row=fetch_one('SELECT * FROM users WHERE username=%s',(body.username,))
    if not row or not verify_password(body.password,row['password_hash']): raise HTTPException(status_code=401,detail='bad credentials')
    execute('UPDATE users SET last_login=NOW() WHERE username=%s',(body.username,)); return {'access_token':create_token(body.username,'access',int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES','60'))),'refresh_token':create_token(body.username,'refresh',int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS','7'))*1440),'token_type':'bearer'}
@app.post('/api/v1/auth/refresh')
def refresh(body:TokenRefresh):
    """Refresh an access token."""
    from jose import jwt, JWTError
    try: payload=jwt.decode(body.refresh_token,os.getenv('JWT_SECRET',''),algorithms=['HS256'])
    except JWTError as exc: raise HTTPException(status_code=401,detail='bad refresh token') from exc
    if payload.get('type')!='refresh': raise HTTPException(status_code=401,detail='bad refresh token')
    return {'access_token':create_token(payload['sub'],'access',int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES','60')))}
@app.websocket('/ws/live')
async def live(ws:WebSocket):
    """Accept authenticated live WebSocket clients."""
    token=ws.query_params.get('token','')
    try:
        payload=jwt.decode(token,os.getenv('JWT_SECRET',''),algorithms=['HS256'])
        if payload.get('type')!='access': await ws.close(code=4001); return
    except JWTError: await ws.close(code=4001); return
    await ws.accept(); sockets.add(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: sockets.discard(ws)
app.include_router(files.router,prefix='/api/v1'); app.include_router(alerts.router,prefix='/api/v1'); app.include_router(baseline.router,prefix='/api/v1'); app.include_router(stats.router,prefix='/api/v1'); app.include_router(settings.router,prefix='/api/v1'); app.include_router(profile.router)
def _term(signum:int, frame:object)->None:
    """Handle termination signal."""
    raise SystemExit(0)
signal.signal(signal.SIGTERM,_term)
