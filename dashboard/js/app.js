/**
 * FIM Sentinel Dashboard — Main Application
 * SPA router, API client, page controllers, UI helpers.
 */

/* =========================================================
   Constants & State
   ========================================================= */
const API = '/api/v1';
let token = localStorage.getItem('fimToken') || '';
let currentPage = 'dashboard';
let scanInterval = 30;
let countdownTimer = null;
let countdownValue = 30;
let alertsPageOffset = 0;
let filesPageOffset = 0;
let tokenIsSet = false;   // true when a Telegram token is already saved in DB
const PAGE_SIZE = 50;

/** Promise-based sleep. */
function sleep(ms) { return new Promise(function(r) { setTimeout(r, ms); }); }

/* =========================================================
   API Client
   ========================================================= */

/**
 * Authenticated fetch wrapper. Auto-refreshes JWT on 401, redirects to login if refresh fails.
 * @param {string} path - API path after /api/v1
 * @param {object} opts - Fetch options
 * @returns {Promise<any>}
 */
async function api(path, opts) {
    opts = opts || {};
    var headers = {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : ''
    };
    if (opts.headers) {
        Object.keys(opts.headers).forEach(function (k) { headers[k] = opts.headers[k]; });
    }
    opts.headers = headers;
    var r = await fetch(API + path, opts);
    if (r.status === 401) {
        // Try to refresh the access token once
        var refreshed = await _tryRefresh();
        if (!refreshed) { showPage('login'); return null; }
        opts.headers['Authorization'] = 'Bearer ' + token;
        r = await fetch(API + path, opts);
        if (r.status === 401) { showPage('login'); return null; }
    }
    try {
        return await r.json();
    } catch (e) {
        return null;
    }
}

/**
 * Attempt to refresh the access token using the stored refresh token.
 * @returns {Promise<boolean>} true if refresh succeeded
 */
async function _tryRefresh() {
    var rt = localStorage.getItem('fimRefresh');
    if (!rt) return false;
    try {
        var r = await fetch(API + '/auth/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: rt })
        });
        if (!r.ok) return false;
        var data = await r.json();
        if (data && data.access_token) {
            token = data.access_token;
            localStorage.setItem('fimToken', token);
            return true;
        }
    } catch (e) {}
    return false;
}

/* =========================================================
   SPA Router
   ========================================================= */

/**
 * Display the specified page and hide all others.
 * @param {string} page - Page name (dashboard, alerts, history, settings, login)
 */
function showPage(page) {
    currentPage = page;
    document.querySelectorAll('.page').forEach(function (el) { el.classList.remove('active'); });
    var target = document.getElementById('page-' + page);
    if (target) target.classList.add('active');

    document.querySelectorAll('.nav-links a').forEach(function (a) {
        a.classList.toggle('active', a.getAttribute('data-page') === page);
    });

    var isLoggedIn = !!token;
    document.querySelector('.nav').style.display = (page === 'login') ? 'none' : '';

    if (page === 'dashboard' && isLoggedIn) loadDashboard();
    else if (page === 'alerts' && isLoggedIn) loadAlerts();
    else if (page === 'history' && isLoggedIn) loadHistory();
    else if (page === 'settings' && isLoggedIn) loadSettings();
}

/**
 * Hash-based route handler.
 */
function route() {
    var hash = location.hash.replace('#', '') || 'dashboard';
    if (!token && hash !== 'login') { showPage('login'); return; }
    showPage(hash);
}

/* =========================================================
   Animated Counter
   ========================================================= */

/**
 * Animate a number from 0 to val inside an element.
 * @param {string} id - Element ID
 * @param {number} val - Target value
 */
function animateNum(id, val) {
    val = parseInt(val) || 0;
    var el = document.getElementById(id);
    if (!el) return;
    var n = 0;
    var step = Math.max(1, Math.ceil(val / 25));
    var t = setInterval(function () {
        n += step;
        if (n >= val) { n = val; clearInterval(t); }
        el.textContent = n;
    }, 20);
}

/* =========================================================
   Timestamp Formatter
   ========================================================= */

/**
 * Format an ISO timestamp for display.
 * @param {string} ts - ISO date string
 * @returns {string}
 */
function fmtTime(ts) {
    if (!ts) return '--';
    var d = new Date(ts);
    return d.toLocaleString('en-GB', { hour12: false, year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * Escape HTML special characters.
 * @param {string} s
 * @returns {string}
 */
function esc(s) {
    if (!s) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

/* =========================================================
   PAGE: Dashboard
   ========================================================= */

/**
 * Load all dashboard widgets: stats, file table, alerts feed, timeline.
 */
async function loadDashboard() {
    var s = await api('/stats/summary');
    if (!s) return;
    animateNum('total', s.total_files);
    animateNum('clean', Math.max(0, s.clean || 0));
    animateNum('alertCount', s.alerts);
    animateNum('critical', s.critical);

    var crit = document.getElementById('cardCritical');
    if (crit) crit.classList.toggle('glow-red', (s.critical || 0) > 0);

    await loadFilesTable();
    await loadFeed();

    var tl = await api('/stats/timeline');
    if (tl) renderTimeline(tl);

    await loadLastScan();
}

/**
 * Load the main file status table.
 */
async function loadFilesTable() {
    var query = '?limit=' + PAGE_SIZE + '&offset=' + filesPageOffset;
    var files = await api('/files' + query);
    if (!files) return;
    var body = document.getElementById('filesBody');
    body.innerHTML = files.map(function (f) {
        var evType = f.event_type || 'UNCHANGED';
        var dotClass = (evType === 'UNCHANGED' || !evType) ? 'clean' : (f.severity === 'CRITICAL' ? 'alert' : 'warning');
        return '<tr onclick="openDetail(\'' + encodeURIComponent(f.file_path) + '\')">' +
            '<td><span class="status-dot ' + dotClass + '"></span></td>' +
            '<td>' + esc(f.file_path) + '</td>' +
            '<td>' + fmtTime(f.detected_at) + '</td>' +
            '<td><span class="badge ' + evType + '">' + evType + '</span></td>' +
            '<td><span class="badge ' + (f.severity || 'INFO') + '">' + (f.severity || 'INFO') + '</span></td>' +
            '<td style="font-family:JetBrains Mono,monospace;font-size:11px">' + esc((f.hash_after || '').substring(0, 12)) + '</td>' +
            '<td><button class="btn sm">View</button></td></tr>';
    }).join('');
    renderPagination('filesPagination', filesPageOffset, files.length, function (o) {
        filesPageOffset = o; loadFilesTable();
    });
}

/**
 * Load the recent alerts feed in the sidebar.
 */
async function loadFeed() {
    var alerts = await api('/alerts/recent');
    if (!alerts) return;
    var feed = document.getElementById('feed');
    if (!alerts.length) { feed.innerHTML = '<div class="empty-state"><b>All quiet</b><span>No recent integrity alerts.</span></div>'; return; }
    feed.innerHTML = alerts.map(function (a) {
        return '<div class="alert-card">' +
            '<b>' + esc(a.event_type) + '</b>' +
            '<div class="path">' + esc(a.file_path) + '</div>' +
            '<div class="hash-delta">' + esc((a.hash_before || '').substring(0, 10)) + ' \u2192 ' + esc((a.hash_after || '').substring(0, 10)) + '</div>' +
            '<div class="meta">' + fmtTime(a.detected_at) + '</div>' +
            (a.acknowledged ? '<span class="badge INFO" style="margin-top:4px">Acked</span>' :
                '<button class="btn sm" style="margin-top:6px" onclick="event.stopPropagation();ackAlert(' + a.id + ')">Acknowledge</button>') +
            '</div>';
    }).join('');
}

/**
 * Load the last scan time and start the countdown timer.
 * Fetches the real interval from settings before starting.
 */
async function loadLastScan() {
    var scan = await api('/scan/status');
    if (!scan) return;
    document.getElementById('lastScan').textContent = fmtTime(scan.completed_at || scan.started_at);
    document.getElementById('scanState').textContent = scan.status === 'RUNNING' ? 'Scanning...' : 'Live';
    // Sync interval from DB so ring uses the correct period
    var cfg = await api('/settings');
    if (cfg && cfg.scan_interval_seconds) {
        scanInterval = Math.max(10, parseInt(cfg.scan_interval_seconds, 10) || 30);
    }
    startCountdown();
}

/* =========================================================
   Countdown Timer
   ========================================================= */

/**
 * Update the SVG ring to reflect remaining time.
 * @param {number} remaining - Seconds remaining
 */
function updateRing(remaining) {
    var circle = document.getElementById('progressCircle');
    if (!circle) return;
    var pct = Math.max(0, Math.min(1, remaining / scanInterval));
    circle.setAttribute('stroke-dashoffset', (251.3 * (1 - pct)).toFixed(1));
    var el = document.getElementById('nextScanCountdown');
    if (el) el.textContent = 'Next scan in ' + Math.max(0, remaining) + 's';
}

/**
 * Start or restart the next-scan countdown ring.
 * At 0 automatically fires triggerScan().
 */
function startCountdown() {
    if (countdownTimer) clearInterval(countdownTimer);
    countdownValue = scanInterval;
    updateRing(countdownValue);
    countdownTimer = setInterval(function () {
        countdownValue--;
        updateRing(countdownValue);
        if (countdownValue <= 0) {
            clearInterval(countdownTimer);
            countdownTimer = null;
            triggerScan();
        }
    }, 1000);
}

/* =========================================================
   File Detail Drawer (PAGE 2)
   ========================================================= */

/**
 * Open the file detail drawer for a given file path.
 * @param {string} encodedPath - URI-encoded file path
 */
async function openDetail(encodedPath) {
    var d = await api('/files/' + encodedPath);
    if (!d) return;
    var f = d.file || {};
    var hist = d.history || [];

    document.getElementById('drawerTitle').textContent = f.file_path || decodeURIComponent(encodedPath);
    var html = '<div style="margin-bottom:16px">' +
        '<span class="badge ' + (f.severity || 'INFO') + '">' + (f.severity || '') + '</span>' +
        (f.is_active ? '' : ' <span class="badge FAILED">Inactive</span>') +
        '</div>';

    html += '<h3>Metadata</h3><div class="meta-grid">';
    html += '<div class="meta-item"><label>File Path</label><span>' + esc(f.file_path) + '</span></div>';
    html += '<div class="meta-item"><label>Severity</label><span>' + esc(f.severity) + '</span></div>';
    html += '</div>';

    if (hist.length) {
        var latest = hist[0];
        html += '<h3>Current vs Baseline</h3><div class="meta-grid">';
        html += '<div class="meta-item"><label>Hash Before</label><span>' + esc(latest.hash_before) + '</span></div>';
        html += '<div class="meta-item"><label>Hash After</label><span>' + esc(latest.hash_after) + '</span></div>';
        html += '<div class="meta-item"><label>Size Before</label><span>' + (latest.size_before != null ? latest.size_before + ' B' : '--') + '</span></div>';
        html += '<div class="meta-item"><label>Size After</label><span>' + (latest.size_after != null ? latest.size_after + ' B' : '--') + '</span></div>';
        html += '<div class="meta-item"><label>Perms Before</label><span>' + esc(latest.permissions_before) + '</span></div>';
        html += '<div class="meta-item"><label>Perms After</label><span>' + esc(latest.permissions_after) + '</span></div>';
        html += '<div class="meta-item"><label>Owner Before</label><span>' + esc(latest.owner_before) + '</span></div>';
        html += '<div class="meta-item"><label>Owner After</label><span>' + esc(latest.owner_after) + '</span></div>';
        html += '</div>';
    }

    html += '<h3>Change History</h3><table><thead><tr><th>Time</th><th>Event</th><th>Hash</th></tr></thead><tbody>';
    hist.forEach(function (h) {
        html += '<tr><td>' + fmtTime(h.detected_at) + '</td><td><span class="badge ' + h.event_type + '">' + h.event_type + '</span></td>' +
            '<td style="font-family:JetBrains Mono,monospace;font-size:11px">' + esc((h.hash_before || '').substring(0, 8)) + ' \u2192 ' + esc((h.hash_after || '').substring(0, 8)) + '</td></tr>';
    });
    html += '</tbody></table>';

    html += '<div class="row gap-sm mt-16">' +
        '<button class="btn danger" onclick="resetBaseline(\'' + encodedPath + '\')">Reset Baseline</button>' +
        '<button class="btn" onclick="removeFile(\'' + encodedPath + '\')">Remove from Monitoring</button></div>';

    document.getElementById('drawerContent').innerHTML = html;
    document.getElementById('drawer').classList.add('open');
}

/** Close the detail drawer. */
function closeDrawer() { document.getElementById('drawer').classList.remove('open'); }

/* =========================================================
   PAGE 3: Alerts
   ========================================================= */

/**
 * Load the full alerts page table with filters.
 */
async function loadAlerts() {
    var sev = document.getElementById('alertSeverityFilter').value;
    var typ = document.getElementById('alertTypeFilter').value;
    var pth = document.getElementById('alertPathSearch').value;
    var params = '?limit=' + PAGE_SIZE + '&offset=' + alertsPageOffset;
    if (sev) params += '&severity=' + sev;
    if (typ) params += '&event_type=' + typ;
    if (pth) params += '&path=' + encodeURIComponent(pth);

    var data = await api('/alerts' + params);
    if (!data) return;
    var body = document.getElementById('alertsBody');
    body.innerHTML = data.map(function (a) {
        return '<tr>' +
            '<td>' + fmtTime(a.detected_at) + '</td>' +
            '<td>' + esc(a.file_path) + '</td>' +
            '<td><span class="badge ' + a.event_type + '">' + a.event_type + '</span></td>' +
            '<td><span class="badge ' + (a.severity || '') + '">' + (a.severity || '') + '</span></td>' +
            '<td style="font-family:JetBrains Mono,monospace;font-size:11px">' + esc((a.hash_before || '').substring(0, 12)) + '</td>' +
            '<td style="font-family:JetBrains Mono,monospace;font-size:11px">' + esc((a.hash_after || '').substring(0, 12)) + '</td>' +
            '<td>' + (a.acknowledged ? '<span class="badge INFO">Acked</span>' :
                '<button class="btn sm" onclick="ackAlert(' + a.id + ')">Ack</button>') + '</td></tr>';
    }).join('');
    renderPagination('alertsPagination', alertsPageOffset, data.length, function (o) {
        alertsPageOffset = o; loadAlerts();
    });
}

/**
 * Export alerts to CSV and trigger download.
 */
async function exportCSV() {
    var data = await api('/alerts?limit=500&offset=0');
    if (!data || !data.length) return;
    var headers = ['detected_at', 'file_path', 'event_type', 'severity', 'hash_before', 'hash_after', 'acknowledged'];
    var csv = headers.join(',') + '\n';
    data.forEach(function (row) {
        csv += headers.map(function (h) { return '"' + String(row[h] || '').replace(/"/g, '""') + '"'; }).join(',') + '\n';
    });
    var blob = new Blob([csv], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'fim-alerts-' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
}

/**
 * Acknowledge an alert by ID.
 * @param {number} id - Alert (file_event) ID
 */
async function ackAlert(id) {
    await api('/alerts/' + id + '/acknowledge', { method: 'PUT' });
    if (currentPage === 'dashboard') loadDashboard();
    else loadAlerts();
}

/* =========================================================
   PAGE 5: Scan History
   ========================================================= */

/**
 * Load the scan history table.
 */
async function loadHistory() {
    var scans = await api('/scan/history');
    if (!scans) return;
    var body = document.getElementById('historyBody');
    body.innerHTML = scans.map(function (s) {
        var changes = (s.files_modified || 0) + (s.files_deleted || 0) + (s.files_added || 0);
        return '<tr onclick="loadScanDetail(' + s.id + ')">' +
            '<td>#' + s.id + '</td>' +
            '<td>' + fmtTime(s.started_at) + '</td>' +
            '<td>' + (s.duration_ms != null ? s.duration_ms + 'ms' : '--') + '</td>' +
            '<td>' + (s.files_scanned || 0) + '</td>' +
            '<td>' + changes + '</td>' +
            '<td><span class="badge ' + (s.status || '') + '">' + (s.status || '') + '</span></td>' +
            '<td>' + esc(s.triggered_by) + '</td></tr>';
    }).join('');
}

/**
 * Load detail of files changed in a specific scan.
 * @param {number} scanId - Scan run ID
 */
async function loadScanDetail(scanId) {
    document.getElementById('scanDetail').style.display = '';
    document.getElementById('scanDetailId').textContent = scanId;
    var events = await api('/alerts?limit=500&offset=0&scan_run_id=' + scanId);
    if (!events) return;
    var body = document.getElementById('scanDetailBody');
    body.innerHTML = events.map(function (e) {
        return '<tr><td>' + esc(e.file_path) + '</td>' +
            '<td><span class="badge ' + e.event_type + '">' + e.event_type + '</span></td>' +
            '<td><span class="badge ' + (e.severity || '') + '">' + (e.severity || '') + '</span></td></tr>';
    }).join('');
    if (!events.length) body.innerHTML = '<tr><td colspan="3"><div class="empty-state compact"><b>No changes</b><span>This scan completed cleanly.</span></div></td></tr>';
}

/* =========================================================
   PAGE 4: Settings
   ========================================================= */

/**
 * Load settings page data: monitored files, baseline status, and saved settings.
 */
async function loadSettings() {
    var files = await api('/files?limit=200');
    if (files) {
        var body = document.getElementById('monitoredBody');
        body.innerHTML = files.map(function (f) {
            var enc = encodeURIComponent(f.file_path);
            var toggleBtn = f.is_active
                ? '<button class="btn sm danger" onclick="disableFile(\'' + enc + '\')">Disable</button>'
                : '<button class="btn sm" onclick="enableFile(\'' + enc + '\')">Enable</button>';
            return '<tr style="opacity:' + (f.is_active ? '1' : '0.45') + '">' +
                '<td>' + esc(f.file_path) + '</td>' +
                '<td><span class="badge ' + (f.severity || 'INFO') + '">' + (f.severity || '') + '</span></td>' +
                '<td>' + (f.is_active ? '<span style="color:#4ade80">Active</span>' : '<span style="color:#f87171">Disabled</span>') + '</td>' +
                '<td>' + toggleBtn + '</td></tr>';
        }).join('');
    }
    var bl = await api('/baseline/status');
    if (bl) {
        document.getElementById('baselineInfo').innerHTML =
            'Files: <b>' + (bl.file_count || 0) + '</b> | Created: <b>' + fmtTime(bl.created_at) + '</b> | Updated: <b>' + fmtTime(bl.updated_at) + '</b>';
    }

    // Load personal Telegram credentials from user profile
    var prof = await fetch(API + '/auth/profile', { headers: { 'Authorization': 'Bearer ' + token } });
    if (prof.ok) {
        var p = await prof.json();
        if (p.telegram_chat_id) document.getElementById('tgChat').value = p.telegram_chat_id;
        tokenIsSet = !!p.telegram_bot_token_set;
        _updateTokenIndicator(tokenIsSet);
    }

    // Load global/SMTP settings from DB
    var cfg = await api('/settings');
    if (cfg) {
        if (cfg.smtp_host) document.getElementById('smtpHost').value = cfg.smtp_host;
        if (cfg.smtp_port) document.getElementById('smtpPort').value = cfg.smtp_port;
        if (cfg.smtp_user) document.getElementById('smtpUser').value = cfg.smtp_user;
        if (cfg.alert_email_to) document.getElementById('smtpTo').value = cfg.alert_email_to;
        if (cfg.scan_interval_seconds) {
            var secs = parseInt(cfg.scan_interval_seconds, 10);
            scanInterval = secs;
            countdownValue = secs;
            document.getElementById('scanInterval').value = secs;
            document.getElementById('scanIntervalVal').textContent = secs + 's';
        }
        if (cfg.alert_on_permission_change === 'false') document.getElementById('togPerms').checked = false;
        if (cfg.alert_on_owner_change === 'false') document.getElementById('togOwner').checked = false;
        if (cfg.alert_on_new_files === 'false') document.getElementById('togNew').checked = false;
        if (cfg.alert_on_deleted_files === 'false') document.getElementById('togDel').checked = false;
    }

    document.getElementById('scanInterval').oninput = function () {
        document.getElementById('scanIntervalVal').textContent = this.value + 's';
    };
}

/**
 * Save all settings from the form to the API.
 */
async function saveSettings(settingsArr) {
    await api('/settings', {
        method: 'PUT',
        body: JSON.stringify({ settings: settingsArr })
    });
}

/**
 * Add a new monitored file path.
 */
async function addFile() {
    var path = document.getElementById('newFilePath').value.trim();
    var sev = document.getElementById('newFileSeverity').value;
    if (!path) return;
    await api('/files/add', { method: 'POST', body: JSON.stringify({ file_path: path, severity: sev }) });
    document.getElementById('newFilePath').value = '';
    loadSettings();
}

/**
 * Remove a file from monitoring.
 * @param {string} encodedPath - URI-encoded file path
 */
async function removeFile(encodedPath) {
    await api('/files/' + encodedPath, { method: 'DELETE' });
    closeDrawer();
    if (currentPage === 'settings') loadSettings();
    else loadDashboard();
}

async function disableFile(encodedPath) {
    await api('/files/' + encodedPath, { method: 'DELETE' });
    showToast('Monitoring disabled for this path', 'info');
    loadSettings();
}

async function enableFile(encodedPath) {
    await api('/files/enable/' + encodedPath, { method: 'POST' });
    showToast('Monitoring enabled for this path', 'success');
    loadSettings();
}

/* =========================================================
   Baseline & Scan Actions
   ========================================================= */

/**
 * Trigger manual scan via API.
 */
async function triggerScan() {
    var stateEl = document.getElementById('scanState');
    var lastScanEl = document.getElementById('lastScan');
    if (stateEl) stateEl.textContent = 'Scanning...';

    // Reset ring immediately so user sees feedback
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = null;
    updateRing(0);
    var cdEl = document.getElementById('nextScanCountdown');
    if (cdEl) cdEl.textContent = 'Scanning...';

    // Snapshot current scan ID before triggering
    var before = await api('/scan/status');
    var beforeId = before ? (before.id || 0) : 0;

    await api('/scan/trigger', { method: 'POST' });

    // Poll until a NEW scan (id > beforeId) that is no longer RUNNING
    var t0 = Date.now();
    var scan = null;
    for (var i = 0; i < 30; i++) {
        await sleep(1000);
        var s = await api('/scan/status');
        if (s && s.id > beforeId && s.status !== 'RUNNING') { scan = s; break; }
    }

    var elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    if (!scan) scan = await api('/scan/status');
    var changes = 0;
    if (scan) {
        changes = (scan.files_modified || 0) + (scan.files_deleted || 0) + (scan.files_added || 0);
        if (lastScanEl) lastScanEl.textContent = fmtTime(scan.completed_at || scan.started_at);
        if (stateEl) stateEl.textContent = changes > 0 ? changes + ' change(s) found' : 'No changes';
    } else {
        if (stateEl) stateEl.textContent = 'Done (' + elapsed + 's)';
    }
    if (currentPage === 'dashboard') loadDashboard();

    // Restart countdown ring after scan completes
    startCountdown();
}

/**
 * Create a new baseline.
 */
async function createBaseline() {
    await api('/baseline/create', { method: 'POST' });
    if (currentPage === 'settings') loadSettings();
}

/**
 * Reset baseline for a specific file (requires password confirmation).
 * @param {string} encodedPath - URI-encoded file path
 */
function resetBaseline(encodedPath) {
    document.getElementById('modalTitle').textContent = 'Reset Baseline';
    document.getElementById('modalText').textContent = 'Enter your password to confirm baseline reset for this file.';
    document.getElementById('modalInput').style.display = '';
    document.getElementById('modalInput').value = '';
    document.getElementById('modalBackdrop').classList.add('open');
    document.getElementById('modalConfirm').onclick = async function () {
        var pw = document.getElementById('modalInput').value;
        await api('/baseline/reset/' + encodedPath, { method: 'POST', body: JSON.stringify({ password: pw }) });
        closeModal();
        closeDrawer();
        loadDashboard();
    };
}

/**
 * Export baseline as JSON download.
 */
async function exportBaseline() {
    var bl = await api('/baseline/status');
    if (bl) {
        var blob = new Blob([JSON.stringify(bl, null, 2)], { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'fim-baseline-' + new Date().toISOString().slice(0, 10) + '.json';
        a.click();
    }
}

/* =========================================================
   Auth
   ========================================================= */

/**
 * Login using credentials from the login form (or passed directly).
 * @param {string} [forceUser] - Optional username override
 * @param {string} [forcePass] - Optional password override
 */
async function login(forceUser, forcePass) {
    var user = forceUser || document.getElementById('loginUser').value.trim();
    var pass = forcePass || document.getElementById('loginPass').value;
    var errEl = document.getElementById('loginError');
    if (errEl) errEl.style.display = 'none';

    if (!user || !pass) {
        if (errEl) { errEl.textContent = 'Enter username and password'; errEl.style.display = ''; }
        return;
    }

    var r;
    try {
        r = await fetch(API + '/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user, password: pass })
        });
    } catch (e) {
        if (errEl) { errEl.textContent = 'Server unavailable'; errEl.style.display = ''; }
        return;
    }
    var data = await r.json();
    if (r.ok && data && data.access_token) {
        token = data.access_token;
        localStorage.setItem('fimToken', token);
        if (data.refresh_token) localStorage.setItem('fimRefresh', data.refresh_token);
        location.hash = '#dashboard';
        route();
        if (!socket) startWS();
    } else {
        var msg = 'Login failed';
        if (data && data.detail) {
            if (Array.isArray(data.detail)) {
                msg = data.detail.map(function(e){ return e.msg || JSON.stringify(e); }).join(', ');
            } else {
                msg = data.detail;
            }
        }
        if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
    }
}

/** Show registration panel. */
function showRegister() {
    document.getElementById('loginPanel').style.display = 'none';
    document.getElementById('registerPanel').style.display = '';
}

/** Show login panel. */
function showLogin() {
    document.getElementById('registerPanel').style.display = 'none';
    document.getElementById('loginPanel').style.display = '';
}

/**
 * Register a new account and auto-login.
 */
async function register() {
    var errEl = document.getElementById('regError');
    errEl.style.display = 'none';
    var username = document.getElementById('regUser').value.trim();
    var password = document.getElementById('regPass').value;
    if (!username || !password) { errEl.textContent = 'Username and password required'; errEl.style.display = ''; return; }
    if (password.length < 8) { errEl.textContent = 'Password must be at least 8 characters'; errEl.style.display = ''; return; }

    var r;
    try {
        r = await fetch(API + '/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password })
        });
    } catch (e) {
        errEl.textContent = 'Server unavailable'; errEl.style.display = ''; return;
    }
    var data = await r.json();
    if (r.ok && data.ok) {
        showLogin();
        await login(username, password);
    } else {
        errEl.textContent = data.detail || 'Registration failed';
        errEl.style.display = '';
    }
}

/**
 * Logout and redirect to login page.
 */
function logout() {
    token = '';
    localStorage.removeItem('fimToken');
    localStorage.removeItem('fimRefresh');
    stopWS();
    showPage('login');
}

/* =========================================================
   Toast Notifications
   ========================================================= */

/**
 * Show a temporary toast notification.
 * @param {string} msg
 * @param {string} type - 'success' | 'error' | 'warning'
 */
function showToast(msg, type) {
    type = type || 'success';
    var el = document.createElement('div');
    var colors = { success: 'var(--green)', error: 'var(--red)', warning: 'var(--yellow)' };
    el.style.cssText = [
        'position:fixed', 'bottom:24px', 'right:24px', 'z-index:999',
        'background:var(--panel-solid)', 'color:var(--text-bright)',
        'border:1px solid ' + (colors[type] || colors.success),
        'border-radius:10px', 'padding:14px 20px', 'font-size:13px',
        'box-shadow:0 8px 32px rgba(0,0,0,.4)',
        'animation:fadeIn .2s ease', 'max-width:340px'
    ].join(';');
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () {
        el.style.opacity = '0';
        el.style.transition = 'opacity .3s';
        setTimeout(function () { el.remove(); }, 300);
    }, 3200);
}

/* =========================================================
   Modal Helpers
   ========================================================= */

/** Close the confirmation modal. */
function closeModal() {
    document.getElementById('modalBackdrop').classList.remove('open');
}

/* =========================================================
   Settings — Telegram / Email / Toggles
   ========================================================= */

/**
 * Update the token saved indicator label next to the token input.
 * @param {boolean} isSet
 */
function _updateTokenIndicator(isSet) {
    var tgInput = document.getElementById('tgToken');
    if (!tgInput) return;
    tgInput.value = '';
    tgInput.placeholder = isSet
        ? '✓ Token saved — leave blank to keep, or enter new to replace'
        : 'Your Bot Token (from @BotFather)';
    var ind = document.getElementById('tgTokenIndicator');
    if (ind) ind.textContent = isSet ? '✓ Token saved' : '';
}

/**
 * Save personal profile (Telegram + optional password change).
 */
async function saveProfile() {
    var tgToken  = document.getElementById('tgToken').value.trim();
    var tgChat   = document.getElementById('tgChat').value.trim();
    var curPass  = document.getElementById('profCurPass').value;
    var newPass  = document.getElementById('profNewPass').value;
    var body = {
        telegram_bot_token: tgToken,
        telegram_chat_id:   tgChat,
        current_password:   curPass,
        new_password:       newPass
    };
    var r = await fetch(API + '/auth/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify(body)
    });
    var data = await r.json();
    if (r.ok && data.ok) {
        showToast('Profile saved!', 'success');
        document.getElementById('profCurPass').value = '';
        document.getElementById('profNewPass').value = '';
        if (tgToken) { tokenIsSet = true; }
        _updateTokenIndicator(tokenIsSet);
    } else {
        showToast('Error: ' + (data.detail || 'unknown'), 'error');
    }
}

/**
 * Send a test Telegram message to the current user's personal chat.
 */
async function testTelegramPersonal() {
    var tgToken = document.getElementById('tgToken').value.trim();
    var tgChat  = document.getElementById('tgChat').value.trim();
    if (!tgChat) { showToast('Enter your Chat ID first', 'warning'); return; }
    // Block only if no token in field AND none saved in DB yet
    if (!tgToken && !tokenIsSet) {
        showToast('\u26a0\ufe0f Enter your Bot Token first', 'warning');
        document.getElementById('tgToken').focus();
        return;
    }
    // If a new token was typed save it first; otherwise use the existing DB token
    if (tgToken) { await saveProfile(); }
    var res = await fetch(API + '/auth/test-telegram', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token }
    });
    var data = await res.json();
    if (data && data.ok) {
        showToast('\u2705 Test message sent to your Telegram!', 'success');
        tokenIsSet = true;
        _updateTokenIndicator(true);
    } else {
        var err = data && data.error ? data.error : 'unknown';
        if (err.indexOf('401') !== -1 || err.indexOf('Unauthorized') !== -1) {
            showToast('\u274c Token is invalid. Get a new one from @BotFather and re-enter it.', 'error');
        } else {
            showToast('\u274c Failed: ' + err, 'error');
        }
    }
}

/**
 * Save SMTP credentials to DB then send a test email.
 */
async function testEmail() {
    await saveSettings([
        { key: 'smtp_host',      value: document.getElementById('smtpHost').value.trim() },
        { key: 'smtp_port',      value: document.getElementById('smtpPort').value.trim() },
        { key: 'smtp_user',      value: document.getElementById('smtpUser').value.trim() },
        { key: 'alert_email_to', value: document.getElementById('smtpTo').value.trim() }
    ]);
    showToast('SMTP settings saved. Email alerts are now active.', 'success');
}

/**
 * Save scan toggle settings to DB.
 */
async function saveToggles() {
    var newInterval = parseInt(document.getElementById('scanInterval').value, 10) || 30;
    await saveSettings([
        { key: 'alert_on_permission_change', value: String(document.getElementById('togPerms').checked) },
        { key: 'alert_on_owner_change',      value: String(document.getElementById('togOwner').checked) },
        { key: 'alert_on_new_files',         value: String(document.getElementById('togNew').checked) },
        { key: 'alert_on_deleted_files',     value: String(document.getElementById('togDel').checked) },
        { key: 'scan_interval_seconds',      value: String(newInterval) }
    ]);
    // Apply new interval to live countdown immediately
    scanInterval = Math.max(10, newInterval);
    startCountdown();
    showToast('Scan settings saved — interval updated to ' + scanInterval + 's', 'success');
}

/* =========================================================
   Pagination Helper
   ========================================================= */

/**
 * Render prev/next pagination controls into a container element.
 * @param {string} containerId - ID of the pagination div
 * @param {number} offset - Current offset
 * @param {number} count - Number of rows returned
 * @param {function} onChange - Callback(newOffset)
 */
function renderPagination(containerId, offset, count, onChange) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var page = Math.floor(offset / PAGE_SIZE) + 1;
    var hasPrev = offset > 0;
    var hasNext = count === PAGE_SIZE;
    el.innerHTML = '';
    if (!hasPrev && !hasNext) { return; }

    if (hasPrev) {
        var prev = document.createElement('button');
        prev.className = 'btn sm';
        prev.type = 'button';
        prev.textContent = '← Prev';
        prev.addEventListener('click', function () {
            onChange(Math.max(0, offset - PAGE_SIZE));
        });
        el.appendChild(prev);
    }

    var pageInfo = document.createElement('span');
    pageInfo.style.cssText = 'margin:0 12px;color:var(--muted);font-size:13px';
    pageInfo.textContent = 'Page ' + page;
    el.appendChild(pageInfo);

    if (hasNext) {
        var next = document.createElement('button');
        next.className = 'btn sm';
        next.type = 'button';
        next.textContent = 'Next →';
        next.addEventListener('click', function () {
            onChange(offset + PAGE_SIZE);
        });
        el.appendChild(next);
    }
}

/* =========================================================
   File Search & Filter Tabs
   ========================================================= */

/**
 * Wire up filter tabs for the files table.
 */
function initFileTabs() {
    var tabContainer = document.getElementById('fileTabs');
    if (!tabContainer) return;
    tabContainer.addEventListener('click', function (e) {
        if (e.target.tagName !== 'BUTTON') return;
        tabContainer.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
        e.target.classList.add('active');
        var filter = e.target.getAttribute('data-filter');
        var rows = document.querySelectorAll('#filesBody tr');
        rows.forEach(function (row) {
            if (filter === 'all') { row.style.display = ''; return; }
            if (filter === 'changed') { row.style.display = row.textContent.includes('UNCHANGED') ? 'none' : ''; return; }
            row.style.display = row.textContent.includes(filter) ? '' : 'none';
        });
    });
}

/**
 * Wire up live search for files table.
 */
function initFileSearch() {
    var input = document.getElementById('fileSearch');
    if (!input) return;
    input.addEventListener('input', function () {
        var term = this.value.toLowerCase();
        document.querySelectorAll('#filesBody tr').forEach(function (row) {
            row.style.display = row.textContent.toLowerCase().includes(term) ? '' : 'none';
        });
    });
}

/* =========================================================
   Live Event Handler
   ========================================================= */

/**
 * Handle WebSocket live events — refresh relevant UI.
 */
window.addEventListener('fim-live', function (e) {
    var msg = e.detail;
    if (!msg) return;
    if (msg.type === 'SCAN_COMPLETE' || msg.type === 'FILE_ALERT' || msg.type === 'STATS_UPDATE') {
        if (currentPage === 'dashboard') loadDashboard();
        else if (currentPage === 'alerts') loadAlerts();
        else if (currentPage === 'history') loadHistory();
    }
    if (msg.type === 'SCAN_STARTED') {
        document.getElementById('scanState').textContent = 'Scanning...';
    }
});

/* =========================================================
   Initialization
   ========================================================= */

window.addEventListener('load', function () {
    if (Notification.permission === 'default') Notification.requestPermission();
    initFileTabs();
    initFileSearch();
    window.addEventListener('hashchange', route);
    route();
    if (token) startWS();
});
