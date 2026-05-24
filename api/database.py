"""Database helpers for the API."""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence
from psycopg2 import pool, DatabaseError
from psycopg2.extras import RealDictCursor

DB_POOL: Optional[pool.SimpleConnectionPool] = None


def init_pool() -> None:
    """Initialise API database pool."""
    global DB_POOL
    DB_POOL = pool.SimpleConnectionPool(
        1,
        20,
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        dbname=os.getenv('POSTGRES_DB', 'fim'),
        user=os.getenv('POSTGRES_USER', 'fim_app'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
    )


@contextmanager
def cursor():
    """Yield transactional cursor."""
    if DB_POOL is None:
        init_pool()

    conn = DB_POOL.getconn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        conn.commit()
    except DatabaseError:
        conn.rollback()
        raise
    finally:
        DB_POOL.putconn(conn)


def fetch_all(sql: str, params: Sequence[Any] | None = None) -> List[Dict[str, Any]]:
    """Fetch all rows for parameterised SQL."""
    if params is None:
        params = []
    with cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_one(sql: str, params: Sequence[Any] | None = None) -> Optional[Dict[str, Any]]:
    """Fetch one row for parameterised SQL."""
    if params is None:
        params = []
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(sql: str, params: Sequence[Any] | None = None) -> None:
    """Execute parameterised SQL."""
    if params is None:
        params = []
    with cursor() as cur:
        cur.execute(sql, params)


def execute_count(sql: str, params: Sequence[Any] | None = None) -> int:
    """Execute parameterised SQL and return affected row count."""
    if params is None:
        params = []
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def audit(username: str, action: str, target: str | None, ip: str | None) -> None:
    """Write an audit log entry."""
    execute(
        'INSERT INTO audit_log(username,action,target,ip_address) VALUES(%s,%s,%s,%s)',
        (username, action, target, ip),
    )
