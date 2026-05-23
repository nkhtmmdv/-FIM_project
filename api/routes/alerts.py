"""Alert routes."""
from __future__ import annotations
import os
from fastapi import APIRouter, Depends, Query, Request
from auth import current_user
from database import audit, execute, fetch_all, fetch_one

router = APIRouter(prefix='/alerts', tags=['alerts'])
_ROOT = os.getenv('MONITOR_ROOT', '/monitored')


def _s(row: dict) -> dict:
    if row and 'file_path' in row:
        row = dict(row)
        p = row['file_path']
        row['file_path'] = p[len(_ROOT):] if p and p.startswith(_ROOT + '/') else p
    return row


@router.get('')
def alerts(
    user=Depends(current_user),
    severity: str | None = None,
    event_type: str | None = None,
    path: str | None = None,
    scan_run_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    """List alerts."""
    where = ['TRUE']
    params = []
    if severity:
        where.append('severity=%s')
        params.append(severity)
    if event_type:
        where.append('event_type=%s')
        params.append(event_type)
    if path:
        where.append('file_path ILIKE %s')
        params.append(f'%{path}%')
    if scan_run_id:
        where.append('scan_run_id=%s')
        params.append(scan_run_id)

    params.extend([limit, offset])
    sql = (
        'SELECT * FROM file_events WHERE ' + ' AND '.join(where)
        + ' ORDER BY detected_at DESC LIMIT %s OFFSET %s'
    )
    return [_s(r) for r in fetch_all(sql, params)]


@router.get('/recent')
def recent(user=Depends(current_user)):
    """Return last twenty alerts."""
    return [_s(r) for r in fetch_all('SELECT * FROM file_events ORDER BY detected_at DESC LIMIT 20')]


@router.put('/{alert_id}/acknowledge')
def acknowledge(alert_id: int, request: Request, user=Depends(current_user)):
    """Acknowledge an alert and advance the baseline so the scanner stops re-alerting."""
    ev = fetch_one('SELECT * FROM file_events WHERE id=%s', (alert_id,))
    if not ev:
        return {'ok': False, 'error': 'not found'}

    execute(
        'UPDATE file_events SET acknowledged=TRUE,acknowledged_by=%s,acknowledged_at=NOW() '
        'WHERE file_path=%s AND acknowledged=FALSE',
        (user['username'], ev['file_path']),
    )
    audit(
        user['username'],
        'alert.ack',
        str(alert_id),
        request.client.host if request.client else None,
    )

    if ev['hash_after'] == 'DELETED':
        execute('DELETE FROM baseline_hashes WHERE file_path=%s', (ev['file_path'],))
    elif ev['hash_after'] and ev['hash_after'] not in ('UNREADABLE',):
        execute('DELETE FROM baseline_hashes WHERE file_path=%s', (ev['file_path'],))
        execute(
            'INSERT INTO baseline_hashes(file_path,sha256_hash,file_size,permissions,owner_name,baseline_set_at) '
            'VALUES(%s,%s,%s,%s,%s,NOW())',
            (
                ev['file_path'],
                ev['hash_after'],
                ev.get('size_after'),
                ev.get('permissions_after'),
                ev.get('owner_after'),
            ),
        )
    return _s(fetch_one('SELECT * FROM file_events WHERE id=%s', (alert_id,)))
