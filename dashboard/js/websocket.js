/**
 * WebSocket client for FIM live updates.
 * Handles reconnection with exponential backoff and dispatches
 * custom events for the dashboard to consume.
 */

let socket = null;
let wsRetryDelay = 2000;
let wsFailCount = 0;
let wsEverConnected = false;
const WS_MAX_RETRY = 30000;

/**
 * Open a WebSocket connection to /ws/live and wire up event handling.
 * Banner is only shown after a successful connection is later lost.
 */
function connectWS() {
    const banner = document.getElementById('reconnect');
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    const tok = localStorage.getItem('fimToken') || '';
    const url = tok
        ? proto + location.host + '/ws/live?token=' + encodeURIComponent(tok)
        : proto + location.host + '/ws/live';

    try {
        socket = new WebSocket(url);
    } catch (err) {
        wsFailCount++;
        scheduleReconnect();
        return;
    }

    socket.onopen = function () {
        wsRetryDelay = 2000;
        wsFailCount = 0;
        wsEverConnected = true;
        if (banner) banner.classList.remove('show');
        var dot = document.getElementById('statusDot');
        if (dot) dot.classList.remove('offline');
    };

    socket.onmessage = function (event) {
        var msg;
        try { msg = JSON.parse(event.data); } catch (e) { return; }

        window.dispatchEvent(new CustomEvent('fim-live', { detail: msg }));

        if (msg.type === 'FILE_ALERT' && Notification.permission === 'granted') {
            new Notification('FIM Alert: ' + (msg.event_type || 'Change'), {
                body: msg.file_path || 'File integrity change detected',
                icon: '/favicon.ico',
                tag: 'fim-' + (msg.id || Date.now())
            });
        }
    };

    socket.onclose = function (evt) {
        wsFailCount++;
        // Codes 1002/1003/1006 with no prior connection = server doesn't support WS, stop retrying
        if (!wsEverConnected && wsFailCount >= 2) {
            return; // give up silently — no banner, no retry
        }
        // Only show the red banner if we previously had a working connection
        if (wsEverConnected) {
            if (banner) banner.classList.add('show');
            var dot = document.getElementById('statusDot');
            if (dot) dot.classList.add('offline');
        }
        scheduleReconnect();
    };

    socket.onerror = function () {
        if (socket) socket.close();
    };
}

/**
 * Schedule a reconnection attempt with exponential backoff.
 */
function scheduleReconnect() {
    setTimeout(connectWS, wsRetryDelay);
    wsRetryDelay = Math.min(wsRetryDelay * 1.5, WS_MAX_RETRY);
}

/**
 * Start WebSocket — call after successful login.
 */
function startWS() {
    wsFailCount = 0;
    wsRetryDelay = 2000;
    wsEverConnected = false;
    connectWS();
}

/**
 * Stop WebSocket — call on logout.
 */
function stopWS() {
    wsEverConnected = false;
    if (socket) { socket.onclose = null; socket.close(); socket = null; }
    var banner = document.getElementById('reconnect');
    if (banner) banner.classList.remove('show');
}
