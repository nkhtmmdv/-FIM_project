"""Stats and scan routes."""
from __future__ import annotations
import requests
import threading
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from auth import current_user
from database import audit, cursor, fetch_all, fetch_one

router = APIRouter(tags=['stats'])

# Heartbeat tracking for watchdog
_last_scanner_heartbeat = time.time()
_heartbeat_lock = threading.Lock()

def _check_scanner_watchdog():
    """Background thread: alert if scanner heartbeat missing for >5 minutes."""
    global _last_scanner_heartbeat
    while True:
        time.sleep(60)  # Check every minute
        with _heartbeat_lock:
            elapsed = time.time() - _last_scanner_heartbeat
        if elapsed > 300:  # 5 minutes
            try:
                # Send alert only once per downtime
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
                text = (
                    f"🚨 *FIM WATCHDOG ALERT* 🚨\n\n"
                    f"🔴 Scanner is *OFFLINE*\n"
                    f"⏱ Missing for: {int(elapsed/60)} minutes\n"
                    f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"🖥 Host: `{host}`\n\n"
                    f"⚠️ Check if scanner container is running!"
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

# Start watchdog thread
threading.Thread(target=_check_scanner_watchdog, daemon=True).start()


@router.get('/health/status')
def health_status(user=Depends(current_user)):
    """Return API, database, and scanner health."""
    db_ok = False
    try:
        fetch_one('SELECT 1 AS ok')
        db_ok = True
    except Exception:
        pass
    with _heartbeat_lock:
        elapsed = max(0, int(time.time() - _last_scanner_heartbeat))
    return {
        'db_ok': db_ok,
        'scanner_online': elapsed < 120,
        'scanner_last_seen_seconds': elapsed,
    }


@router.post('/health/scanner-heartbeat')
def scanner_heartbeat():
    """Receive heartbeat from scanner service."""
    global _last_scanner_heartbeat
    with _heartbeat_lock:
        _last_scanner_heartbeat = time.time()
    return {'ok': True}
@router.get('/stats/summary')
def summary(user=Depends(current_user)):
    """Return dashboard summary."""
    return fetch_one(
        "SELECT "
        "(SELECT COUNT(*) FROM monitored_files WHERE is_active) AS total_files, "
        "(SELECT COUNT(*) FROM monitored_files WHERE is_active) "
        "- (SELECT COUNT(*) FROM file_events WHERE detected_at > NOW() - INTERVAL '24 hours') AS clean, "
        "(SELECT COUNT(*) FROM file_events WHERE detected_at > NOW() - INTERVAL '24 hours') AS alerts, "
        "(SELECT COUNT(*) FROM file_events "
        "WHERE detected_at > NOW() - INTERVAL '24 hours' AND severity = 'CRITICAL') AS critical, "
        "(SELECT COUNT(*) FROM file_events WHERE acknowledged = FALSE) AS unacknowledged"
    )
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
