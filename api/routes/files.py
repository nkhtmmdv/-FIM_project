"""File routes."""
from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from auth import current_user
from database import audit, execute, fetch_all, fetch_one
from models.file_record import FileAdd

router = APIRouter(prefix='/files', tags=['files'])
MONITOR_ROOT = os.getenv('MONITOR_ROOT', '/monitored')

def _to_scan(p: str) -> str:
    """Add MONITOR_ROOT prefix for scanner container."""
    p = os.path.normpath(p)
    return p if p.startswith(MONITOR_ROOT) else MONITOR_ROOT + p

def _to_display(p: str) -> str:
    """Strip MONITOR_ROOT prefix for display."""
    return p[len(MONITOR_ROOT):] if p and p.startswith(MONITOR_ROOT + '/') else p

def _strip(row: dict) -> dict:
    """Return row with file_path stripped of MONITOR_ROOT."""
    if row and 'file_path' in row:
        row = dict(row)
        row['file_path'] = _to_display(row['file_path'])
    return row

@router.get('')
def list_files(
    user=Depends(current_user),
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """List monitored files with latest event."""
    params = []
    where = ['TRUE']
    if severity:
        where.append('m.severity=%s')
        params.append(severity)

    clause = ' AND '.join(where)
    sql = (
        'SELECT m.*,e.event_type,e.detected_at,e.hash_after '
        'FROM monitored_files m '
        'LEFT JOIN LATERAL ('
        '  SELECT * FROM file_events e2 WHERE e2.file_path=m.file_path ORDER BY detected_at DESC LIMIT 1'
        ') e ON TRUE '
        'WHERE ' + clause + ' ORDER BY m.file_path LIMIT %s OFFSET %s'
    )
    params.extend([limit, offset])
    return [_strip(r) for r in fetch_all(sql, params)]


@router.get('/{path:path}')
def file_detail(path: str, user=Depends(current_user)):
    """Return a single file and history."""
    scan_path = _to_scan('/' + path)
    f = fetch_one(
        'SELECT * FROM monitored_files WHERE file_path=%s',
        (scan_path,),
    )
    hist = fetch_all(
        'SELECT * FROM file_events WHERE file_path=%s ORDER BY detected_at DESC LIMIT 200',
        (scan_path,),
    )
    return {
        'file': _strip(f),
        'history': [_strip(h) for h in hist],
    }


@router.post('/add')
def add_file(body: FileAdd, request: Request, user=Depends(current_user)):
    """Add a monitored file path."""
    norm = os.path.normpath(body.file_path)
    if '..' in norm.split(os.sep) or not norm.startswith('/'):
        raise HTTPException(status_code=400, detail='invalid file path')

    scan_path = _to_scan(norm)
    execute(
        'INSERT INTO monitored_files(file_path,severity,added_by) VALUES(%s,%s,%s) '
        'ON CONFLICT(file_path) DO UPDATE SET is_active=TRUE,severity=EXCLUDED.severity',
        (scan_path, body.severity, user['username']),
    )
    execute('DELETE FROM baseline_hashes WHERE file_path=%s', (scan_path,))
    execute('UPDATE file_events SET acknowledged=TRUE WHERE file_path=%s AND acknowledged=FALSE', (scan_path,))
    audit(
        user['username'],
        'file.add',
        scan_path,
        request.client.host if request.client else None,
    )
    return {'ok': True}


@router.delete('/{path:path}')
def remove_file(path: str, request: Request, user=Depends(current_user)):
    """Deactivate a monitored file path and clean up its baseline + events."""
    target = _to_scan('/' + path)
    execute('UPDATE monitored_files SET is_active=FALSE WHERE file_path=%s', (target,))
    execute('DELETE FROM baseline_hashes WHERE file_path=%s', (target,))
    execute('UPDATE file_events SET acknowledged=TRUE WHERE file_path=%s AND acknowledged=FALSE', (target,))
    audit(
        user['username'],
        'file.remove',
        target,
        request.client.host if request.client else None,
    )
    return {'ok': True}


@router.post('/enable/{path:path}')
def enable_file(path: str, request: Request, user=Depends(current_user)):
    """Re-activate a disabled monitored file path."""
    target = _to_scan('/' + path)
    execute('UPDATE monitored_files SET is_active=TRUE WHERE file_path=%s', (target,))
    audit(
        user['username'],
        'file.enable',
        target,
        request.client.host if request.client else None,
    )
    return {'ok': True}
