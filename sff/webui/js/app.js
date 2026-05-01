/**
 * SteaMidra — Main App Router & Sidebar Navigation
 * Handles page switching, platform detection, and global initialization.
 */

window.App = (function() {
    'use strict';

    var _currentPage = 'home';
    var _platform = 'win32';
    var _outsideMode = false;

    function init() {
        Components.initModals();
        Tooltips.init();
        _initSidebar();
        _initLogPanel();
        _initGlobalListeners();

        Bridge.onReady(function(py) {
            // Detect platform
            py.get_platform(function(platform) {
                _platform = platform || 'win32';
                document.body.classList.add('platform-' + _platform);
                // Hide Windows-only elements on Linux
                if (_platform !== 'win32') {
                    document.querySelectorAll('.platform-win').forEach(function(el) {
                        el.style.display = 'none';
                    });
                }
            });

            // Load theme from backend (overrides localStorage default for fresh installs)
            py.get_setting('theme', function(themeId) {
                if (themeId) {
                    document.documentElement.setAttribute('data-theme', themeId);
                    localStorage.setItem('theme', themeId);
                }
            });

            // Check for stored API key
            py.get_stored_api_key(function(apiKey) {
                if (apiKey) {
                    Store.onApiKeyAvailable(apiKey);
                }
            });

            // Populate game dropdown on Home page
            _populateGameDropdown();
            setInterval(_populateGameDropdown, 10 * 60 * 1000);

            // Refresh button beside game dropdown
            var homeRefreshBtn = document.getElementById('home-game-refresh');
            if (homeRefreshBtn) homeRefreshBtn.addEventListener('click', _populateGameDropdown);

            // Listen to global signals
            Bridge.on('task_finished', function(json) {
                try {
                    var result = JSON.parse(json);
                    if (result.message) {
                        Components.showToast(
                            result.success ? 'success' : 'error',
                            result.message
                        );
                    }
                    if (result.task === 'download_fastest' && result.success) {
                        Components.showModal('restart-after-download-modal');
                        _populateGameDropdown();
                    }
                } catch(e) {}
            });

            Bridge.on('log_message', function(msg) {
                _appendLog(msg);
                _appendHomeLog(msg);
            });
        });

        // Navigate to saved page or home
        var savedPage = localStorage.getItem('currentPage');
        if (savedPage) {
            navigateTo(savedPage);
        }

        // Apply saved theme
        var savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-theme', savedTheme);
        }
    }

    function _initSidebar() {
        document.querySelectorAll('.nav-item[data-page]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                navigateTo(this.dataset.page);
            });
        });
    }

    function navigateTo(pageId) {
        // Hide all pages
        document.querySelectorAll('.page').forEach(function(page) {
            page.classList.remove('active');
        });

        // Show target page
        var target = document.getElementById('page-' + pageId);
        if (target) {
            target.classList.add('active');
        }

        // Update sidebar active state
        document.querySelectorAll('.nav-item[data-page]').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.page === pageId);
        });

        _currentPage = pageId;
        localStorage.setItem('currentPage', pageId);

        // Trigger page-specific init if needed
        switch(pageId) {
            case 'store': Store.onPageEnter(); break;
            case 'library': Library.onPageEnter(); break;
            case 'downloads': Downloads.onPageEnter(); break;
            case 'fixgame': FixGame.onPageEnter(); break;
            case 'tools': Tools.onPageEnter(); break;
            case 'cloudsaves': CloudSaves.onPageEnter(); break;
            case 'settings': Settings.onPageEnter(); break;
        }
    }

    var _logMinLevel = 20; // INFO by default

    function _initLogPanel() {
        // Sidebar Logs button opens the native GlobalLogWindow (independent OS window)
        var logsBtn = document.getElementById('btn-logs');
        if (logsBtn) {
            logsBtn.addEventListener('click', function() {
                Bridge.call('open_log_window');
            });
        }

        // Home page mini-log Clear button
        var homeLogClear = document.getElementById('home-log-clear');
        if (homeLogClear) {
            homeLogClear.addEventListener('click', function() {
                var content = document.getElementById('home-log-content');
                if (content) content.innerHTML = '';
            });
        }

        // Home page mini-log Copy button — uses bridge to avoid clipboard API issues in QWebEngine
        var homeLogCopy = document.getElementById('home-log-copy');
        if (homeLogCopy) {
            homeLogCopy.addEventListener('click', function() {
                var content = document.getElementById('home-log-content');
                if (content) {
                    var text = content.innerText || content.textContent || '';
                    Bridge.call('copy_to_clipboard', text);
                    Components.showToast('success', 'Log copied to clipboard');
                }
            });
        }
    }

    function _appendLog(msg) {
        var content = document.getElementById('log-panel-content');
        if (!content) return;

        // Parse level from message format: "[LEVEL] message" or "name — [LEVEL] message"
        var level = 20; // default INFO
        var levelClass = 'log-info';
        var levelTag = 'INFO';
        if (msg.indexOf('[DEBU') !== -1) { level = 10; levelClass = 'log-debug'; levelTag = 'DEBG'; }
        else if (msg.indexOf('[WARN') !== -1) { level = 30; levelClass = 'log-warning'; levelTag = 'WARN'; }
        else if (msg.indexOf('[ERRO') !== -1 || msg.indexOf('[CRIT') !== -1) { level = 40; levelClass = 'log-error'; levelTag = 'ERR '; }

        var now = new Date();
        var ts = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2) + ':' + ('0' + now.getSeconds()).slice(-2);

        var line = document.createElement('div');
        line.className = 'log-line ' + levelClass;
        line.dataset.level = level;
        line.innerHTML = '<span class="log-ts">' + ts + '</span> <span class="log-tag">[' + levelTag + ']</span> ' + _escapeLogHtml(msg);

        if (level < _logMinLevel) {
            line.style.display = 'none';
        }

        content.appendChild(line);
        content.scrollTop = content.scrollHeight;
    }

    function _appendHomeLog(msg) {
        var content = document.getElementById('home-log-content');
        if (!content) return;

        var levelClass = 'log-info';
        var levelTag = 'INFO';
        if (msg.indexOf('[DEBU') !== -1) { levelClass = 'log-debug'; levelTag = 'DEBG'; }
        else if (msg.indexOf('[WARN') !== -1) { levelClass = 'log-warning'; levelTag = 'WARN'; }
        else if (msg.indexOf('[ERRO') !== -1 || msg.indexOf('[CRIT') !== -1) { levelClass = 'log-error'; levelTag = 'ERR '; }

        var now = new Date();
        var ts = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2) + ':' + ('0' + now.getSeconds()).slice(-2);

        var line = document.createElement('div');
        line.className = 'log-line ' + levelClass;
        line.innerHTML = '<span class="log-ts">' + ts + '</span> ' + _escapeLogHtml(msg);

        content.appendChild(line);
        // Keep last 200 lines to avoid memory growth
        while (content.children.length > 200) {
            content.removeChild(content.firstChild);
        }
        content.scrollTop = content.scrollHeight;
    }

    function _escapeLogHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _applyLogLevelFilter() {
        var content = document.getElementById('log-panel-content');
        if (!content) return;
        var lines = content.querySelectorAll('.log-line');
        for (var i = 0; i < lines.length; i++) {
            var lineLevel = parseInt(lines[i].dataset.level, 10) || 20;
            lines[i].style.display = lineLevel >= _logMinLevel ? '' : 'none';
        }
    }

    function _initGlobalListeners() {
        // Game source toggle (Steam vs outside)
        var srcSteam   = document.getElementById('game-source-steam');
        var srcOutside = document.getElementById('game-source-outside');
        if (srcSteam) srcSteam.addEventListener('change', function() {
            _outsideMode = false;
            document.getElementById('steam-mode-row').style.display   = '';
            document.getElementById('outside-mode-row').style.display  = 'none';
        });
        if (srcOutside) srcOutside.addEventListener('change', function() {
            _outsideMode = true;
            document.getElementById('steam-mode-row').style.display   = 'none';
            document.getElementById('outside-mode-row').style.display  = '';
        });

        // Browse button — opens native folder picker via bridge
        var browseBtn = document.getElementById('outside-path-browse');
        if (browseBtn) browseBtn.addEventListener('click', function() {
            Bridge.callSync('browse_game_folder', function(path) {
                if (path) document.getElementById('outside-path-display').value = path;
            });
        });

        // Restart Steam button
        var restartBtn = document.getElementById('btn-restart-steam');
        if (restartBtn) {
            restartBtn.addEventListener('click', function() {
                if (confirm('Restart Steam?')) {
                    Bridge.call('restart_steam');
                    Components.showToast('info', 'Restarting Steam...');
                }
            });
        }

        // Global download button handler (delegated)
        document.addEventListener('click', function(e) {
            var dlBtn = e.target.closest('.btn-download');
            if (dlBtn) {
                e.preventDefault();
                var appId = dlBtn.dataset.appid;
                var name = dlBtn.dataset.name || ('App ' + appId);
                Components.showDownloadModal(appId, name, _platform);
            }
        });

        // Download modal — fastest
        var dlFastest = document.getElementById('dl-fastest');
        if (dlFastest) {
            dlFastest.addEventListener('click', function() {
                var appId = this.dataset.appid;
                var sourceEl = document.querySelector('input[name="dl-source"]:checked');
                var source = sourceEl ? sourceEl.value : 'hubcap';
                Components.hideModal('download-modal');
                _startDownload(appId, 'fastest', source);
            });
        }

        // Download modal — older version
        var dlOlder = document.getElementById('dl-older');
        if (dlOlder) {
            dlOlder.addEventListener('click', function() {
                var appId = this.dataset.appid;
                Components.hideModal('download-modal');
                _showVersionPicker(appId);
            });
        }

        // Version picker — download selected
        var versionDl = document.getElementById('version-download');
        if (versionDl) {
            versionDl.addEventListener('click', function() {
                _downloadSelectedVersion();
            });
        }

        // Home page action cards
        document.querySelectorAll('.action-card[data-action]').forEach(function(card) {
            card.addEventListener('click', function() {
                var action = this.dataset.action;
                _handleHomeAction(action);
            });
        });

        // Update Manifests modal — wire Run + Select-All + Restart-after-download buttons
        var umRunBtn = document.getElementById('update-manifests-run');
        if (umRunBtn) {
            umRunBtn.addEventListener('click', function() {
                var excludes = [];
                document.querySelectorAll('#um-game-list input[type="checkbox"]:not(:checked)').forEach(function(cb) {
                    if (cb.dataset.appid) excludes.push(cb.dataset.appid);
                });
                Bridge.call('set_setting', 'manifest_update_excludes', excludes.join(','));
                Components.hideModal('update-manifests-modal');
                Components.showToast('info', 'Updating manifests...');
                Bridge.call('run_game_action', '', 'update_manifests');
            });
        }

        var umToggleBtn = document.getElementById('um-toggle-all');
        if (umToggleBtn) {
            umToggleBtn.addEventListener('click', function() {
                var checkboxes = document.querySelectorAll('#um-game-list input[type="checkbox"]');
                var allChecked = Array.prototype.every.call(checkboxes, function(cb) { return cb.checked; });
                checkboxes.forEach(function(cb) { cb.checked = !allChecked; });
                umToggleBtn.textContent = allChecked ? 'Select All' : 'Deselect All';
            });
        }

        var rsDlBtn = document.getElementById('restart-after-dl-run');
        if (rsDlBtn) {
            rsDlBtn.addEventListener('click', function() {
                Components.hideModal('restart-after-download-modal');
                Bridge.call('restart_steam');
            });
        }
    }

    function _startDownload(appId, mode, source) {
        // First, ask for library selection
        Bridge.callSync('get_steam_libraries', function(json) {
            var libs;
            try { libs = JSON.parse(json || '[]'); } catch(e) { libs = []; }

            if (libs.length === 0) {
                Components.showToast('error', 'No Steam libraries found. Check your Steam path in Settings.');
                return;
            }

            if (libs.length === 1) {
                Bridge.call('set_active_library', libs[0]);
                _executeDownload(appId, mode, source);
            } else {
                Components.showLibraryModal(libs, function(selectedLib) {
                    Bridge.call('set_active_library', selectedLib);
                    _executeDownload(appId, mode, source);
                });
            }
        });
    }

    function _executeDownload(appId, mode, source) {
        Components.showToast('info', 'Starting download for App ' + appId + '...');
        if (mode === 'fastest') {
            var src = source || 'hubcap';
            Bridge.call('download_game_with_source', appId, src);
        }
    }

    function _showVersionPicker(appId) {
        Components.showModal('version-modal');
        var loading = document.getElementById('version-loading');
        var table = document.getElementById('version-table');
        var tbody = document.getElementById('version-tbody');
        var dlBtn = document.getElementById('version-download');

        if (loading) loading.classList.remove('hidden');
        if (table) table.classList.add('hidden');
        if (dlBtn) { dlBtn.disabled = true; dlBtn.dataset.appid = appId; }

        // Listen for depot history results
        var handler = function(json) {
            Bridge.off('depot_history_results', handler);
            if (loading) loading.classList.add('hidden');
            if (table) table.classList.remove('hidden');

            try {
                var depots = JSON.parse(json);
                if (tbody) {
                    tbody.innerHTML = '';
                    depots.forEach(function(depot) {
                        (depot.manifests || []).forEach(function(manifest) {
                            var tr = document.createElement('tr');
                            tr.innerHTML =
                                '<td>' + depot.depot_id + '</td>' +
                                '<td>' + manifest.manifest_id + '</td>' +
                                '<td>' + (manifest.date || 'N/A') + '</td>' +
                                '<td><input type="checkbox" class="version-check" data-depot="' + depot.depot_id + '" data-manifest="' + manifest.manifest_id + '"></td>';
                            tbody.appendChild(tr);
                        });
                    });
                }
            } catch(e) {
                Components.showToast('error', 'Failed to load version history');
            }
        };
        Bridge.on('depot_history_results', handler);
        Bridge.call('fetch_depot_history', appId, false);

        // Enable download button when checkboxes are selected
        if (tbody) {
            tbody.addEventListener('change', function() {
                var checked = tbody.querySelectorAll('.version-check:checked');
                if (dlBtn) dlBtn.disabled = checked.length === 0;
            });
        }
    }

    function _downloadSelectedVersion() {
        var dlBtn = document.getElementById('version-download');
        var appId = dlBtn ? dlBtn.dataset.appid : '';
        var tbody = document.getElementById('version-tbody');
        if (!tbody || !appId) return;

        var manifest_override = {};
        tbody.querySelectorAll('.version-check:checked').forEach(function(cb) {
            manifest_override[cb.dataset.depot] = cb.dataset.manifest;
        });

        Components.hideModal('version-modal');

        // Library selection + version download
        Bridge.callSync('get_steam_libraries', function(json) {
            var libs;
            try { libs = JSON.parse(json || '[]'); } catch(e) { libs = []; }

            var doDownload = function() {
                Bridge.call('download_game_version', appId, JSON.stringify(manifest_override));
                Components.showToast('info', 'Downloading specific version of App ' + appId + '...');
            };

            if (libs.length <= 1) {
                if (libs.length === 1) Bridge.call('set_active_library', libs[0]);
                doDownload();
            } else {
                Components.showLibraryModal(libs, function(selectedLib) {
                    Bridge.call('set_active_library', selectedLib);
                    doDownload();
                });
            }
        });
    }

    function _populateGameDropdown() {
        Bridge.callSync('get_game_list', function(json) {
            var games;
            try { games = JSON.parse(json || '[]'); } catch(e) { games = []; }
            var select = document.getElementById('home-game-select');
            if (!select) return;
            // Keep the placeholder option
            select.innerHTML = '<option value="">-- Select a game --</option>';
            games.forEach(function(game) {
                var opt = document.createElement('option');
                opt.value = game.app_id;
                opt.textContent = game.name + ' (' + game.app_id + ')';
                select.appendChild(opt);
            });
        });
    }

    function _getSelectedGameId() {
        var select = document.getElementById('home-game-select');
        return select ? select.value : '';
    }

    function _handleHomeAction(action) {
        // Show game-picker dialog before running update_manifests
        if (action === 'update_manifests') {
            var listEl = document.getElementById('um-game-list');
            var countEl = document.getElementById('um-count');
            var toggleBtn = document.getElementById('um-toggle-all');
            if (listEl) listEl.innerHTML = '<span style="opacity:0.5;font-size:13px;">Loading games...</span>';
            if (countEl) countEl.textContent = 'Loading...';
            if (toggleBtn) toggleBtn.textContent = 'Deselect All';
            Components.showModal('update-manifests-modal');
            Bridge.callSync('get_applist_games', function(json) {
                var games;
                try { games = JSON.parse(json || '[]'); } catch(e) { games = []; }
                if (!listEl) return;
                if (games.length === 0) {
                    listEl.innerHTML = '<span style="opacity:0.5;font-size:13px;">No saved Lua files found.</span>';
                    if (countEl) countEl.textContent = '0 games';
                    return;
                }
                var html = '';
                games.forEach(function(g) {
                    var safe = (g.name || g.app_id).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    html += '<label style="display:flex;align-items:center;gap:8px;padding:5px 2px;cursor:pointer;font-size:13px;">'
                        + '<input type="checkbox" data-appid="' + g.app_id + '" checked style="accent-color:var(--accent,#e94560);">'
                        + '<span>' + safe + ' <span style="opacity:0.45;font-size:11px;">' + g.app_id + '</span></span>'
                        + '</label>';
                });
                listEl.innerHTML = html;
                if (countEl) countEl.textContent = games.length + ' game' + (games.length !== 1 ? 's' : '');
            });
            return;
        }

        // Non-game actions don't need a game selected
        var nonGameActions = [
            'download_games', 'download_manifests', 'recent_lua', 'update_manifests',
            'mute_toggle', 'remove_game', 'context_menu', 'applist_menu', 'offline_fix',
            'check_updates', 'scan_library', 'analytics'
        ];
        // Outside-Steam game action
        if (_outsideMode && nonGameActions.indexOf(action) === -1) {
            var gamePath     = (document.getElementById('outside-path-display') || {}).value || '';
            var outsideAppId = (document.getElementById('outside-appid') || {}).value || '0';
            if (!gamePath) {
                Components.showToast('warning', 'Please select a game folder first.');
                return;
            }
            Bridge.call('run_game_action_outside', gamePath, outsideAppId || '0', action);
            return;
        }

        // Steam game action
        var appId = _getSelectedGameId();
        if (nonGameActions.indexOf(action) === -1 && !appId) {
            Components.showToast('warning', 'Please select a game from the dropdown first.');
            return;
        }
        Bridge.call('run_game_action', appId || '', action);
    }

    function getPlatform() {
        return _platform;
    }

    return {
        init: init,
        navigateTo: navigateTo,
        getPlatform: getPlatform
    };
})();

// Boot the app when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    App.init();
});
