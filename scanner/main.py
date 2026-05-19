"""Scanner scheduler entrypoint."""
from __future__ import annotations
import os, signal, time
from typing import Dict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import urlparse
import scanner
from logger import write_daily_checksum
STOP=Event(); LAST_SCAN_ID=0
class Handler(BaseHTTPRequestHandler):
    """Minimal internal control API for scanner."""
    def do_GET(self)->None:
        """Return scanner health."""
        self.send_response(200); self.end_headers(); self.wfile.write(f'{{"last_scan_id":{LAST_SCAN_ID}}}'.encode())
    def do_POST(self)->None:
        """Trigger manual scan or baseline reset."""
        global LAST_SCAN_ID
        path=urlparse(self.path).path
        if path.endswith('/api/scan/trigger'): LAST_SCAN_ID=scanner.run_scan('manual'); self.send_response(202); self.end_headers(); return
        if path.endswith('/api/baseline/reset') and self.headers.get('X-Confirmation-Token')==os.getenv('BASELINE_CONFIRMATION_TOKEN',''): LAST_SCAN_ID=scanner.run_scan('baseline-reset',True); self.send_response(202); self.end_headers(); return
        self.send_response(403); self.end_headers()
def _signal(signum:int, frame:object)->None:
    """Handle graceful shutdown signals."""
    STOP.set(); write_daily_checksum()
def serve()->None:
    """Run internal HTTP server."""
    ThreadingHTTPServer(('0.0.0.0',9000),Handler).serve_forever()
def main()->None:
    """Run scanner forever until SIGTERM."""
    global LAST_SCAN_ID
    signal.signal(signal.SIGTERM,_signal); signal.signal(signal.SIGINT,_signal); Thread(target=serve,daemon=True).start()
    while not STOP.is_set():
        import db as _db; interval=_db.get_scan_interval()
        LAST_SCAN_ID=scanner.run_scan('scheduler'); STOP.wait(interval)
if __name__=='__main__': main()
