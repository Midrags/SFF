/**
 * SteaMidra — QWebChannel Python↔JS Bridge
 * Connects to the Python WebBridge QObject via QWebChannel.
 * All slot calls are async in Qt6 — use callbacks or signals.
 */

window.Bridge = (function() {
    'use strict';

    let _py = null;
    let _ready = false;
    const _readyCallbacks = [];
    const _signalListeners = {};

    function init() {
        if (typeof QWebChannel === 'undefined') {
            console.error('[Bridge] QWebChannel not available — running outside QtWebEngine?');
            _simulateBridge();
            return;
        }
        new QWebChannel(qt.webChannelTransport, function(channel) {
            _py = channel.objects.bridge;
            if (!_py) {
                console.error('[Bridge] No "bridge" object registered in QWebChannel');
                return;
            }
            _ready = true;
            _connectSignals();
            _readyCallbacks.forEach(function(cb) { cb(_py); });
            _readyCallbacks.length = 0;
            console.log('[Bridge] Connected to Python backend');
        });
    }

    function _connectSignals() {
        var signalNames = [
            'search_results',
            'depot_history_results',
            'download_progress',
            'task_finished',
            'log_message',
            'lc_progress'
        ];
        signalNames.forEach(function(name) {
            if (_py[name] && typeof _py[name].connect === 'function') {
                _py[name].connect(function(data) {
                    _emit(name, data);
                });
            }
        });
    }

    function onReady(callback) {
        if (_ready && _py) {
            callback(_py);
        } else {
            _readyCallbacks.push(callback);
        }
    }

    function isReady() {
        return _ready && _py !== null;
    }

    // Signal listener system
    function on(signalName, callback) {
        if (!_signalListeners[signalName]) {
            _signalListeners[signalName] = [];
        }
        _signalListeners[signalName].push(callback);
    }

    function off(signalName, callback) {
        if (!_signalListeners[signalName]) return;
        var idx = _signalListeners[signalName].indexOf(callback);
        if (idx !== -1) _signalListeners[signalName].splice(idx, 1);
    }

    function _emit(signalName, data) {
        var listeners = _signalListeners[signalName];
        if (!listeners) return;
        listeners.forEach(function(cb) {
            try { cb(data); } catch(e) { console.error('[Bridge] Signal handler error:', signalName, e); }
        });
    }

    // Call a bridge method (async slot — no return value, results via signals)
    function call(method /*, ...args */) {
        if (!_py) {
            console.warn('[Bridge] Not connected, queuing call:', method);
            onReady(function() { call.apply(null, arguments); });
            return;
        }
        var args = Array.prototype.slice.call(arguments, 1);
        if (typeof _py[method] === 'function') {
            _py[method].apply(_py, args);
        } else {
            console.error('[Bridge] Unknown method:', method);
        }
    }

    // Call a sync bridge method (with callback — because Qt6 QWebChannel is always async)
    function callSync(method, callback) {
        if (!_py) {
            onReady(function() { callSync(method, callback); });
            return;
        }
        if (typeof _py[method] === 'function') {
            _py[method](callback);
        } else {
            console.error('[Bridge] Unknown method:', method);
        }
    }

    // Call with args + trailing callback (for sync slots with parameters)
    function callWithCallback(method /*, arg1, arg2, ..., callback */) {
        if (!_py) {
            onReady(function() { callWithCallback.apply(null, arguments); });
            return;
        }
        var args = Array.prototype.slice.call(arguments, 1);
        if (typeof _py[method] === 'function') {
            _py[method].apply(_py, args);
        } else {
            console.error('[Bridge] Unknown method:', method);
        }
    }

    // Simulation mode for development outside QtWebEngine
    function _simulateBridge() {
        console.warn('[Bridge] Running in SIMULATION mode — no Python backend');
        _py = {
            search_games: function() {},
            fetch_depot_history: function() {},
            download_game_fastest: function() {},
            download_game_version: function() {},
            run_game_action: function() {},
            get_platform: function(cb) { if (cb) cb('win32'); },
            connect_store: function() {},
            get_stored_api_key: function(cb) { if (cb) cb(''); },
            list_profiles: function(cb) { if (cb) cb('[]'); },
            switch_profile: function() {},
            save_profile: function() {},
            delete_profile: function() {},
            rename_profile: function() {},
            set_setting: function() {},
            get_setting: function(key, cb) { if (cb) cb(''); },
            get_steam_libraries: function(cb) { if (cb) cb('[]'); },
            set_active_library: function() {},
            open_file_dialog: function(cb) { if (cb) cb(''); },
            open_log_window: function() {},
            restart_steam: function() {},
            refresh_library: function(cb) { if (cb) cb('[]'); },
            get_installed_games: function(cb) { if (cb) cb('[]'); },
            scan_cloud_games: function() {},
            backup_cloud_save: function() {},
            restore_cloud_save: function() {},
            generate_gbe_token: function() {},
            extract_vdf_keys: function(cb) { if (cb) cb('[]'); },
            open_workshop: function() {},
            fix_game: function() {},
            revert_game: function() {},
            get_fix_game_list: function(cb) { if (cb) cb('[]'); },
            get_applist_games: function(cb) { if (cb) cb('[]'); },
            browse_game_folder: function(cb) { if (cb) cb(''); },
            run_game_action_outside: function() {},
            open_url: function() {},
        };
        _ready = true;
        _readyCallbacks.forEach(function(cb) { cb(_py); });
        _readyCallbacks.length = 0;
    }

    return {
        init: init,
        onReady: onReady,
        isReady: isReady,
        on: on,
        off: off,
        call: call,
        callSync: callSync,
        callWithCallback: callWithCallback,
        getPy: function() { return _py; }
    };
})();

// Initialize the bridge immediately
Bridge.init();
