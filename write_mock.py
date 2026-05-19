content = r'''"""Mock server: serves static files + fake API (updated for per-user Telegram)."""
import json, time, os
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

FAKE_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.fake'
SETTINGS_STORE = {}
USER_STORE = {
    'admin': {'username': 'admin', 'role': 'admin', 'telegram_chat_id': '', 'telegram_bot_token': '', 'created_at': '2025-05-19T00:00:00Z', 'last_login': None}
}

MOCK_FILES = [
    {'id': 1, 'file_path': '/monitored/etc/passwd', 'is_active': True, 'severity': 'CRITICAL', 'event_type': 'MODIFIED', 'detected_at': '2025-05-19T12:30:00Z', 'hash_after': 'a3f2c1d8e9b7', 'added_by': 'admin'},
    {'id': 2, 'file_path': '/monitored/etc/shadow', 'is_active': True, 'severity': 'CRITICAL', 'event_type': 'UNCHANGED', 'detected_at': '2025-05-19T12:30:00Z', 'hash_after': 'b7e9d4f1a2c3', 'added_by': 'admin'},
    {'id': 3, 'file_path': '/monitored/etc/sudoers', 'is_active': True, 'severity': 'CRITICAL', 'event_type': 'UNCHANGED', 'detected_at': '2025-05-19T12:30:00Z', 'hash_after': 'c1d8e9b7a3f2', 'added_by': 'admin'},
    {'id': 4, 'file_path': '/monitored/etc/ssh/sshd_config', 'is_active': True, 'severity': 'WARNING', 'event_type': 'PERMISSIONS_CHANGED', 'detected_at': '2025-05-19T12:28:00Z', 'hash_after': 'd4f1a2c3b7e9', 'added_by': 'admin'},
    {'id': 5, 'file_path': '/monitored/etc/hosts', 'is_active': True, 'severity': 'WARNING', 'event_type': 'UNCHANGED', 'detected_at': '2025-05-19T12:30:00Z', 'hash_after': 'e9b7a3f2c1d8', 'added_by': 'admin'},
    {'id': 6, 'file_path': '/monitored/bin/bash', 'is_active': True, 'severity': 'CRITICAL', 'event_type': 'UNCHANGED', 'detected_at': '2025-05-19T12:30:00Z', 'hash_after': 'f1a2c3b7e9d4', 'added_by': 'admin'},
    {'id': 7, 'file_path': '/monitored/usr/bin/sudo', 'is_active': True, 'severity': 'CRITICAL', 'event_type': 'MODIFIED', 'detected_at': '2025-05-19T12:25:00Z', 'hash_after': '1a2c3b7e9d4f', 'added_by': 'admin'},
    {'id': 8, 'file_path': '/monitored/etc/crontab', 'is_active': True, 'severity': 'WARNING', 'event_type': 'ADDED', 'detected_at': '2025-05-19T11:50:00Z', 'hash_after': '2c3b7e9d4f1a', 'added_by': 'admin'},
]

MOCK_ALERTS = [
    {'id': 1, 'scan_run_id': 5, 'file_path': '/monitored/etc/passwd', 'event_type': 'MODIFIED', 'severity': 'CRITICAL', 'hash_before': 'a3f2c1d8e9', 'hash_after': 'b7e9d4f1a2', 'size_before': 2048, 'size_after': 2190, 'permissions_before': '644', 'permissions_after': '644', 'owner_before': 'root', 'owner_after': 'root', 'detected_at': '2025-05-19T12:30:00Z', 'acknowledged': False},
    {'id': 2, 'scan_run_id': 5, 'file_path': '/monitored/usr/bin/sudo', 'event_type': 'MODIFIED', 'severity': 'CRITICAL', 'hash_before': '1a2c3b7e9d', 'hash_after': '9d4f1a2c3b', 'size_before': 166056, 'size_after': 166120, 'permissions_before': '4755', 'permissions_after': '4755', 'owner_before': 'root', 'owner_after': 'root', 'detected_at': '2025-05-19T12:25:00Z', 'acknowledged': False},
    {'id': 3, 'scan_run_id': 4, 'file_path': '/monitored/etc/ssh/sshd_config', 'event_type': 'PERMISSIONS_CHANGED', 'severity': 'WARNING', 'hash_before': 'd4f1a2c3b7', 'hash_after': 'd4f1a2c3b7', 'size_before': 3280, 'size_after': 3280, 'permissions_before': '600', 'permissions_after': '644', 'owner_before': 'root', 'owner_after': 'root', 'detected_at': '2025-05-19T12:28:00Z', 'acknowledged': False},
    {'id': 4, 'scan_run_id': 3, 'file_path': '/monitored/etc/crontab', 'event_type': 'ADDED', 'severity': 'WARNING', 'hash_before': None, 'hash_after': '2c3b7e9d4f1a', 'size_before': None, 'size_after': 1024, 'permissions_before': None, 'permissions_after': '644', 'owner_before': None, 'owner_after': 'root', 'detected_at': '2025-05-19T11:50:00Z', 'acknowledged': True},
]

MOCK_SCANS = [
    {'id': 5, 'started_at': '2025-05-19T12:30:00Z', 'completed_at': '2025-05-19T12:30:05Z', 'duration_ms': 5120, 'files_scanned': 8, 'files_clean': 5, 'files_modified': 2, 'files_deleted': 0, 'files_added': 1, 'status': 'COMPLETE', 'triggered_by': 'scheduler'},
    {'id': 4, 'started_at': '2025-05-19T12:00:00Z', 'completed_at': '2025-05-19T12:00:04Z', 'duration_ms': 4800, 'files_scanned': 8, 'files_clean': 7, 'files_modified': 0, 'files_deleted': 0, 'files_added': 0, 'status': 'COMPLETE', 'triggered_by': 'scheduler'},
    {'id': 3, 'started_at': '2025-05-19T11:30:00Z', 'completed_at': '2025-05-19T11:30:06Z', 'duration_ms': 6100, 'files_scanned': 7, 'files_clean': 6, 'files_modified': 0, 'files_deleted': 0, 'files_added': 1, 'status': 'COMPLETE', 'triggered_by': 'manual'},
]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory='dashboard', **kw)

    def log_message(self, fmt, *args):
        print(f'[mock] {args[0]} {args[1]}')

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        self.end_headers()

    def _body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        if path == '/api/v1/auth/login':
            user = body.get('username', 'admin')
            if user not in USER_STORE:
                USER_STORE[user] = {'username': user, 'role': 'analyst', 'telegram_chat_id': '', 'telegram_bot_token': '', 'created_at': '2025-05-19T00:00:00Z', 'last_login': None}
            return self._json({'access_token': FAKE_TOKEN, 'refresh_token': FAKE_TOKEN, 'token_type': 'bearer'})
        if path == '/api/v1/auth/register':
            u = body.get('username', '')
            if u in USER_STORE:
                return self._json({'detail': 'username already taken'}, 409)
            USER_STORE[u] = {'username': u, 'role': 'analyst', 'telegram_chat_id': body.get('telegram_chat_id', ''), 'telegram_bot_token': body.get('telegram_bot_token', ''), 'created_at': '2025-05-19T00:00:00Z', 'last_login': None}
            return self._json({'ok': True})
        if path == '/api/v1/auth/refresh':
            return self._json({'access_token': FAKE_TOKEN})
        if path == '/api/v1/auth/test-telegram':
            return self._json({'ok': True})
        if path == '/api/v1/settings/test-telegram':
            return self._json({'ok': True})
        if path == '/api/v1/scan/trigger':
            return self._json({'ok': True})
        if path == '/api/v1/baseline/create':
            return self._json({'ok': True})
        if path == '/api/v1/files/add':
            MOCK_FILES.append({'id': len(MOCK_FILES)+1, 'file_path': body.get('file_path',''), 'is_active': True, 'severity': body.get('severity','WARNING'), 'event_type': 'UNCHANGED', 'detected_at': '2025-05-19T12:30:00Z', 'hash_after': 'new', 'added_by': 'admin'})
            return self._json({'ok': True})
        return self._json({'ok': True})

    def do_PUT(self):
        path = urlparse(self.path).path
        body = self._body()
        if path == '/api/v1/auth/profile':
            user = 'admin'
            if body.get('telegram_chat_id'):
                USER_STORE[user]['telegram_chat_id'] = body['telegram_chat_id']
            if body.get('telegram_bot_token') and not body['telegram_bot_token'].startswith('*'):
                USER_STORE[user]['telegram_bot_token'] = body['telegram_bot_token']
            return self._json({'ok': True})
        if path == '/api/v1/settings':
            for item in body.get('settings', []):
                SETTINGS_STORE[item['key']] = item['value']
            return self._json({'ok': True})
        return self._json({'ok': True})

    def do_DELETE(self):
        return self._json({'ok': True})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/v1/files':
            return self._json(MOCK_FILES)
        if path.startswith('/api/v1/files/'):
            fp = '/' + path[len('/api/v1/files/'):]
            f = next((x for x in MOCK_FILES if x['file_path'] == fp), MOCK_FILES[0])
            return self._json({'file': f, 'history': MOCK_ALERTS[:3]})
        if path == '/api/v1/alerts':
            return self._json(MOCK_ALERTS)
        if path == '/api/v1/alerts/recent':
            return self._json(MOCK_ALERTS[:5])
        if path == '/api/v1/stats/summary':
            return self._json({'total_files': 8, 'clean': 5, 'alerts': 3, 'critical': 2})
        if path == '/api/v1/stats/timeline':
            return self._json([{'hour': f'2025-05-19T{h:02d}:00:00Z', 'alerts': [0,0,1,0,2,0,1][h%7]} for h in range(24)])
        if path == '/api/v1/stats/top-changed':
            return self._json([{'file_path': f['file_path'], 'changes': i+1} for i, f in enumerate(MOCK_FILES[:5])])
        if path == '/api/v1/scan/status':
            return self._json(MOCK_SCANS[0])
        if path == '/api/v1/scan/history':
            return self._json(MOCK_SCANS)
        if path == '/api/v1/baseline/status':
            return self._json({'file_count': 8, 'created_at': '2025-05-18T10:00:00Z', 'updated_at': '2025-05-19T12:30:00Z'})
        if path == '/api/v1/auth/profile':
            return self._json({'username': 'admin', 'role': 'admin', 'telegram_chat_id': USER_STORE.get('admin', {}).get('telegram_chat_id', ''), 'telegram_bot_token': USER_STORE.get('admin', {}).get('telegram_bot_token', ''), 'telegram_bot_token_set': False, 'created_at': '2025-05-19T00:00:00Z', 'last_login': None})
        if path == '/api/v1/settings':
            return self._json(SETTINGS_STORE)
        if path == '/ws/live':
            # WebSocket upgrade not supported in mock — return 426 silently
            self.send_response(426)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        return super().do_GET()

if __name__ == '__main__':
    print('Mock server on http://localhost:8080')
    HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
'''

with open('dashboard/mock_server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
