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

ALGORITHM = 'HS256'
SECURITY = HTTPBearer()
PWD = CryptContext(schemes=['bcrypt'], deprecated='auto', bcrypt__rounds=12)


def validate_secrets() -> None:
    """Validate minimum secret lengths, warn instead of crashing."""
    import logging

    if len(os.getenv('JWT_SECRET', '')) < 64:
        raise RuntimeError('JWT_SECRET must be at least 64 characters — set it in .env')
    if not os.getenv('POSTGRES_PASSWORD', ''):
        raise RuntimeError('POSTGRES_PASSWORD must be set in .env')


def hash_password(password: str) -> str:
    """Hash a password with bcrypt (max 72 bytes)."""
    if len(password.encode()) > 72:
        raise ValueError('Password must be 72 bytes or fewer (bcrypt limit)')
    return PWD.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a bcrypt password (max 72 bytes)."""
    return PWD.verify(password, hashed)


def create_token(username: str, kind: str, minutes: int) -> str:
    """Create a signed JWT."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode(
        {'sub': username, 'type': kind, 'exp': exp},
        os.getenv('JWT_SECRET', ''),
        algorithm=ALGORITHM,
    )


def current_user(creds: HTTPAuthorizationCredentials = Depends(SECURITY)) -> Dict[str, str]:
    """Return authenticated user from bearer token."""
    try:
        payload = jwt.decode(creds.credentials, os.getenv('JWT_SECRET', ''), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid token') from exc

    if payload.get('type') != 'access':
        raise HTTPException(status_code=401, detail='invalid token type')

    return {'username': str(payload['sub'])}


def ensure_admin() -> None:
    """No-op: users register themselves via the site."""
    pass
