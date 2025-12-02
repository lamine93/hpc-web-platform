// ============================================================================
// common.js
// Global Socket.IO initialization + lightweight page-scoped helper (SocketPage)
// ============================================================================

(function () {
  // Avoid double initialization (in case base.html loads scripts twice)
  if (window.__socketInitialized) return;
  window.__socketInitialized = true;

  // ------------------------------------------------------------------------
  // 1) Global Socket.IO client
  // ------------------------------------------------------------------------
  const socket = io('http://192.168.64.2:5000', {
    transports: ['websocket'],      // Prefer WebSocket transport
    reconnection: true,             // Auto reconnect on network issues
    reconnectionDelay: 2000,        // Initial reconnect delay (ms)
    reconnectionDelayMax: 15000,    // Maximum backoff delay (ms)
    // withCredentials: true,       // Uncomment if you rely on cookies/sessions
  });

  // Expose globally for other scripts (dashboard.js, resources.js, etc.)
  window.socket = socket;

  // Basic lifecycle logs
  socket.off('connect').on('connect', () => {
    console.log('[common] Connected to the server:', socket.id);
  });

  socket.off('disconnect').on('disconnect', (reason) => {
    console.log('[common] Disconnected from server:', reason);
  });

  socket.off('connect_error').on('connect_error', (err) => {
    console.warn('[common] Connection error:', err?.message || err);
  });

  // ------------------------------------------------------------------------
  // 2) SocketPage helper
  // ------------------------------------------------------------------------
  /**
   * SocketPage(name)
   * Helper for page-level Socket.IO management:
   *  - avoids double listeners or multiple intervals
   *  - waits for connection before emitting
   *  - auto-cleans on page unload
   *  - pauses polling when tab is hidden
   *  - resumes after reconnect
   */
  window.SocketPage = function SocketPage(name) {
    const scope = {
      name,
      timers: [],
      listeners: {},
      started: false,
    };

    // --------------------------------------------------------
    // Register a unique listener for a given event (off + on)
    // --------------------------------------------------------
    scope.on = function (event, handler) {
      if (scope.listeners[event]) {
        socket.off(event, scope.listeners[event]);
      }
      scope.listeners[event] = handler;
      socket.on(event, handler);
      return scope;
    };

    // --------------------------------------------------------
    // Emit when the socket is connected (waits if needed)
    // --------------------------------------------------------
    scope.emitWhenReady = function (emitFn) {
      if (socket.connected) {
        emitFn();
      } else {
        socket.once('connect', emitFn);
      }
      return scope;
    };

    // --------------------------------------------------------
    // Set up a polling timer (e.g. every 3 minutes)
    // Options:
    //  - immediate: run once immediately (default true)
    //  - visibleOnly: skip when tab is hidden (default true)
    // --------------------------------------------------------
    scope.poll = function (ms, fn, { immediate = true, visibleOnly = true } = {}) {
      const tick = () => {
        if (!visibleOnly || !document.hidden) fn();
      };
      if (immediate) scope.emitWhenReady(fn);
      const id = setInterval(tick, ms);
      scope.timers.push(id);
      return scope;
    };

    // --------------------------------------------------------
    // Cleanup timers and listeners (called automatically)
    // --------------------------------------------------------
    scope.cleanup = function () {
      scope.timers.forEach(clearInterval);
      scope.timers = [];
      Object.entries(scope.listeners).forEach(([ev, fn]) => socket.off(ev, fn));
      scope.listeners = {};
    };

    // Auto cleanup on page unload
    window.addEventListener('beforeunload', scope.cleanup);

    // --------------------------------------------------------
    // Optional: auto re-emit or refresh after reconnect
    // --------------------------------------------------------
    scope.onReconnect = function (fn) {
      scope._onReconnect = fn;
      return scope;
    };

    socket.off(`reconnect.${name}`).on('reconnect', () => {
      if (scope.started && scope._onReconnect) {
        console.log(`[${scope.name}] Reconnected → auto-refresh`);
        scope._onReconnect();
      }
    });

    // --------------------------------------------------------
    // Mark this page as "started" (for reconnect tracking)
    // --------------------------------------------------------
    scope.markStarted = function () {
      scope.started = true;
      return scope;
    };

    return scope;
  };
})();

function getCurrentRefreshRateMs() {
    const rateSeconds = localStorage.getItem('refreshRate') || "180"; 
    
    return parseInt(rateSeconds) * 1000; 
}


function getDefaultQos() {
    return localStorage.getItem('defaultQos') || 'normal';
}

function getDefaultPartition() {
    return localStorage.getItem('defaultPartition') || 'standard';
}

