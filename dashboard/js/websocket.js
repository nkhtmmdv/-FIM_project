/**
 * WebSocket client for FIM live updates.
 * Handles reconnection with exponential backoff and dispatches
 * custom events for the dashboard to consume.
 */

let socket = null;
let wsRetryDelay = 1000;
let wsFailCount = 0;
const WS_MAX_RETRY = 30000;
const WS_BANNER_AFTER = 3; // show banner only after this many consecutive failures

/**
 * Open a WebSocket connection to /ws/live and wire up event handling.
 */
function connectWS() {
    const banner = document.getElementById('reconnect');
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    const url = proto + location.host + '/ws/live';

    try {
        socket = new WebSocket(url);
    } catch (err) {
        wsFailCount++;
        scheduleReconnect();
        return;
    }

    socket.onopen = function () {
        wsRetryDelay = 1000;
        wsFailCount = 0;
        if (banner) banner.classList.remove('show');
        document.getElementById('statusDot').classList.remove('offline');
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

    socket.onclose = function () {
        wsFailCount++;
        if (wsFailCount >= WS_BANNER_AFTER) {
            if (banner) banner.classList.add('show');
            document.getElementById('statusDot').classList.add('offline');
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
