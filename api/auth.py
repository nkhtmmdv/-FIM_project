"""JWT authentication and password security."""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from database import execute, fetch_one
ALGORITHM='HS256'; SECURITY=HTTPBearer(); PWD=CryptContext(schemes=['bcrypt'],deprecated='auto',bcrypt__rounds=12)
def validate_secrets()->None:
    """Validate minimum secret lengths, warn instead of crashing."""
    import logging
    if len(os.getenv('JWT_SECRET',''))<32:
        raise RuntimeError('JWT_SECRET must be at least 32 characters — set it in .env')
    if not os.getenv('POSTGRES_PASSWORD',''):
        raise RuntimeError('POSTGRES_PASSWORD must be set in .env')
def hash_password(password:str)->str:
    """Hash a password with bcrypt."""
    return PWD.hash(password)
def verify_password(password:str, hashed:str)->bool:
    """Verify a bcrypt password."""
    return PWD.verify(password,hashed)
def create_token(username:str, kind:str, minutes:int)->str:
    """Create a signed JWT."""
    exp=datetime.now(timezone.utc)+timedelta(minutes=minutes); return jwt.encode({'sub':username,'type':kind,'exp':exp},os.getenv('JWT_SECRET',''),algorithm=ALGORITHM)
def current_user(creds:HTTPAuthorizationCredentials=Depends(SECURITY))->Dict[str,str]:
    """Return authenticated user from bearer token."""
    try: payload=jwt.decode(creds.credentials,os.getenv('JWT_SECRET',''),algorithms=[ALGORITHM])
    except JWTError as exc: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail='invalid token') from exc
    if payload.get('type')!='access': raise HTTPException(status_code=401,detail='invalid token type')
    return {'username':str(payload['sub'])}
def ensure_admin()->None:
    """Create initial admin user from environment if missing."""
    username=os.getenv('ADMIN_USERNAME','admin'); password=os.getenv('ADMIN_PASSWORD','')
    if not password:
        import logging; logging.warning('ADMIN_PASSWORD not set — skipping auto-admin creation'); return
    if not fetch_one('SELECT id FROM users WHERE username=%s',(username,)): execute('INSERT INTO users(username,password_hash,role,telegram_chat_id,telegram_bot_token) VALUES(%s,%s,%s,%s,%s)',(username,hash_password(password),'admin','',''))
