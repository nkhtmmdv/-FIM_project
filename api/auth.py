"""Local-only user context (no login required)."""
from __future__ import annotations
import os
from typing import Dict
from database import execute, fetch_one

LOCAL_USERNAME = os.getenv('LOCAL_USERNAME', 'local')


def validate_secrets() -> None:
    """Validate required environment variables."""
    if not os.getenv('POSTGRES_PASSWORD', ''):
        raise RuntimeError('POSTGRES_PASSWORD must be set in .env')


def ensure_local_user() -> None:
    """Create the default local user if it does not exist."""
    if not fetch_one('SELECT id FROM users WHERE username=%s', (LOCAL_USERNAME,)):
        execute(
            'INSERT INTO users(username, password_hash, role) VALUES(%s, %s, %s)',
            (LOCAL_USERNAME, 'local-only', 'admin'),
        )


def current_user() -> Dict[str, str]:
    """Return the local user (no authentication)."""
    return {'username': LOCAL_USERNAME}
