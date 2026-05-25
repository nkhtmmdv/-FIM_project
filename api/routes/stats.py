"""Stats and scan routes."""
from __future__ import annotations
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from auth import current_user
from database import audit, cursor, fetch_all, fetch_one
router=APIRouter(tags=['stats'])
@router.get('/stats/summary')
def summary(user=Depends(current_user)):
    """Return dashboard summary."""
    return fetch_one("SELECT (SELECT COUNT(*) FROM monitored_files WHERE is_active) total_files,(SELECT COUNT(*) FROM monitored_files WHERE is_active)-COUNT(*) clean,COUNT(*) alerts,COUNT(*) FILTER (WHERE severity='CRITICAL') critical FROM file_events WHERE detected_at > NOW()-INTERVAL '24 hours'")
@router.get('/stats/timeline')
def timeline(user=Depends(current_user)):
    """Return hourly alert timeline."""
    return fetch_all("SELECT date_trunc('hour',detected_at) hour,COUNT(*) alerts FROM file_events WHERE detected_at>NOW()-INTERVAL '24 hours' GROUP BY 1 ORDER BY 1")
@router.get('/stats/top-changed')
def top_changed(user=Depends(current_user)):
    """Return top changed paths."""
    return fetch_all('SELECT file_path,COUNT(*) changes FROM file_events GROUP BY file_path ORDER BY changes DESC LIMIT 10')
@router.get('/scan/status')
def scan_status(user=Depends(current_user)):
    """Return latest scan."""
    return fetch_one('SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1')
@router.post('/scan/trigger')
def trigger(user=Depends(current_user)):
    """Trigger manual scan."""
    try:
        requests.post('http://scanner:9000/api/scan/trigger', timeout=5)
    except requests.RequestException:
        pass
    return {'ok': True}
@router.get('/scan/history')
def history(user=Depends(current_user)):
    """Return scan history."""
    return fetch_all('SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 100')


@router.delete('/scan/history')
def clear_history(request: Request, user=Depends(current_user)):
    """Permanently clear ALL scan history (and associated events)."""
    with cursor() as cur:
        cur.execute('LOCK TABLE file_events, scan_runs IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('DELETE FROM file_events WHERE scan_run_id IS NOT NULL')
        cur.execute('DELETE FROM scan_runs')
        deleted = cur.rowcount
    audit(
        user['username'],
        'scan.history.clear',
        f'all ({deleted} runs)',
        request.client.host if request.client else None,
    )
    return {'ok': True, 'deleted': deleted}


@router.delete('/scan/history/{scan_id}')
def delete_scan(scan_id: int, request: Request, user=Depends(current_user)):
    """Delete a single scan run and its events."""
    with cursor() as cur:
        cur.execute('LOCK TABLE file_events, scan_runs IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('DELETE FROM file_events WHERE scan_run_id=%s', (scan_id,))
        cur.execute('DELETE FROM scan_runs WHERE id=%s', (scan_id,))
        deleted = cur.rowcount
    if deleted == 0:
        raise HTTPException(status_code=404, detail='scan run not found')
    audit(
        user['username'],
        'scan.history.delete',
        f'scan#{scan_id}',
        request.client.host if request.client else None,
    )
    return {'ok': True, 'deleted': deleted}
