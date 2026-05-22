"""PostgreSQL persistence layer for scanner."""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional
from psycopg2 import pool, DatabaseError
from psycopg2.extras import RealDictCursor
DB_POOL:Optional[pool.SimpleConnectionPool]=None
def init_pool()->None:
    """Initialise the database connection pool."""
    global DB_POOL
    DB_POOL=pool.SimpleConnectionPool(1,10,host=os.getenv('POSTGRES_HOST','postgres'),dbname=os.getenv('POSTGRES_DB','fim'),user=os.getenv('POSTGRES_USER','fim_app'),password=os.getenv('POSTGRES_PASSWORD',''))
@contextmanager
def conn_cursor():
    """Yield a transactional cursor and rollback on database errors."""
    if DB_POOL is None: init_pool()
    conn=DB_POOL.getconn()
    try:
        cur=conn.cursor(cursor_factory=RealDictCursor); yield cur; conn.commit()
    except DatabaseError:
        conn.rollback(); raise
    finally:
        DB_POOL.putconn(conn)
def baseline_exists()->bool:
    """Return whether a baseline exists."""
    with conn_cursor() as cur: cur.execute('SELECT EXISTS(SELECT 1 FROM baseline_hashes) AS ok'); return bool(cur.fetchone()['ok'])
def monitored_paths()->List[str]:
    """Return active monitored paths."""
    with conn_cursor() as cur: cur.execute('SELECT file_path FROM monitored_files WHERE is_active=TRUE ORDER BY file_path'); return [r['file_path'] for r in cur.fetchall()]
def severities()->Dict[str,str]:
    """Return configured severities."""
    with conn_cursor() as cur: cur.execute('SELECT file_path,severity FROM monitored_files'); return {r['file_path']:r['severity'] for r in cur.fetchall()}
def start_scan(triggered_by:str)->int:
    """Create a scan run."""
    with conn_cursor() as cur: cur.execute('INSERT INTO scan_runs(triggered_by) VALUES(%s) RETURNING id',(triggered_by,)); return int(cur.fetchone()['id'])
def finish_scan(scan_id:int, stats:Dict[str,int], status:str)->None:
    """Finish a scan run with counters."""
    with conn_cursor() as cur: cur.execute('UPDATE scan_runs SET completed_at=NOW(),duration_ms=%s,files_scanned=%s,files_clean=%s,files_modified=%s,files_deleted=%s,files_added=%s,status=%s WHERE id=%s',(stats.get('duration_ms',0),stats.get('scanned',0),stats.get('clean',0),stats.get('modified',0),stats.get('deleted',0),stats.get('added',0),status,scan_id))
def replace_baseline(scan_id:int, snaps:Iterable[Dict[str,object]])->None:
    """Replace the full baseline atomically."""
    with conn_cursor() as cur:
        cur.execute('DELETE FROM baseline_hashes')
        for s in snaps: cur.execute('INSERT INTO baseline_hashes(file_path,sha256_hash,file_size,permissions,owner_uid,owner_gid,owner_name,inode,baseline_scan_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(s['file_path'],s['sha256_hash'],s['file_size'],s['permissions'],s['owner_uid'],s['owner_gid'],s['owner_name'],s['inode'],scan_id))
def load_baseline()->Dict[str,Dict[str,object]]:
    """Load baseline keyed by path."""
    with conn_cursor() as cur: cur.execute('SELECT * FROM baseline_hashes'); return {r['file_path']:dict(r) for r in cur.fetchall()}
def write_event(scan_id:int, ev:Dict[str,object])->None:
    """Persist a file event."""
    with conn_cursor() as cur: cur.execute('INSERT INTO file_events(scan_run_id,file_path,event_type,severity,hash_before,hash_after,size_before,size_after,permissions_before,permissions_after,owner_before,owner_after) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(scan_id,ev['file_path'],ev['event_type'],ev.get('severity'),ev.get('hash_before'),ev.get('hash_after'),ev.get('size_before'),ev.get('size_after'),ev.get('permissions_before'),ev.get('permissions_after'),ev.get('owner_before'),ev.get('owner_after')))
def has_unacked_duplicate(file_path:str, hash_after:str, current_scan_id:int)->bool:
    """Return True if an unacknowledged event for the same file+state already exists from a prior scan."""
    try:
        with conn_cursor() as cur:
            cur.execute(
                'SELECT 1 FROM file_events WHERE file_path=%s AND hash_after=%s '
                'AND acknowledged=FALSE AND scan_run_id!=%s LIMIT 1',
                (file_path, hash_after, current_scan_id)
            )
            return cur.fetchone() is not None
    except Exception:
        return False

def get_scan_interval()->int:
    """Return scan interval seconds from DB settings, fallback to env."""
    try:
        with conn_cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key='scan_interval_seconds'")
            row=cur.fetchone()
            if row and row['value']: return max(10,int(row['value']))
    except Exception: pass
    return int(os.getenv('SCAN_INTERVAL_SECONDS','120'))
