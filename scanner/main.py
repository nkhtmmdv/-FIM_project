"""Scanner scheduler entrypoint."""
from __future__ import annotations
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import urlparse
import alerter
import db as _db
import requests
import scanner
from logger import write_daily_checksum
STOP = Event()
LAST_SCAN_ID = 0

def _heartbeat_sender():
    """Send periodic heartbeat to API to prove we're alive."""
    while not STOP.is_set():
        try:
            requests.post('http://api:8000/api/v1/health/scanner-heartbeat', timeout=5)
        except Exception:
            pass  # API might be down, keep trying
        STOP.wait(60)  # Heartbeat every 60 seconds

class Handler(BaseHTTPRequestHandler):
    """Minimal internal control API for scanner."""
    def do_GET(self) -> None:
        """Return scanner health."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(f'{{"last_scan_id":{LAST_SCAN_ID}}}'.encode())
    def do_POST(self) -> None:
        """Trigger manual scan or baseline reset."""
        global LAST_SCAN_ID
        path = urlparse(self.path).path
        if path.endswith('/api/scan/trigger'):
            try:
                LAST_SCAN_ID = scanner.run_scan('manual')
            except Exception:
                pass
            self.send_response(202)
            self.end_headers()
            return
        if (
            path.endswith('/api/baseline/reset')
            and self.headers.get('X-Confirmation-Token') == os.getenv('BASELINE_CONFIRMATION_TOKEN', '')
        ):
            try:
                LAST_SCAN_ID = scanner.run_scan('baseline-reset', True)
            except Exception:
                pass
            self.send_response(202)
            self.end_headers()
            return
        self.send_response(403)
        self.end_headers()
def _signal(signum: int, frame: object) -> None:
    """Handle graceful shutdown signals."""
    STOP.set()
    # Send emergency alert before shutting down
    try:
        alerter.send_shutdown_alert('stopped')
    except Exception:
        pass
    write_daily_checksum()
def serve() -> None:
    """Run internal HTTP server."""
    ThreadingHTTPServer(('0.0.0.0', 9000), Handler).serve_forever()
_TICK = 5  # seconds between interval-change checks

def main() -> None:
    """Run scanner forever until SIGTERM."""
    global LAST_SCAN_ID
    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)
    _db.ensure_root_monitored_path('/monitored')
    Thread(target=serve, daemon=True).start()
    Thread(target=_heartbeat_sender, daemon=True).start()
    while not STOP.is_set():
        interval = _db.get_scan_interval()
        try:
            LAST_SCAN_ID = scanner.run_scan('scheduler')
        except Exception:
            pass
        # Wait for the interval but re-check DB every _TICK seconds.
        # If the configured interval changes, break early so the next
        # iteration starts with the new value immediately.
        waited = 0
        while not STOP.is_set() and waited < interval:
            STOP.wait(_TICK)
            waited += _TICK
            new_interval = _db.get_scan_interval()
            if new_interval != interval:
                break
if __name__ == '__main__':
    main()
