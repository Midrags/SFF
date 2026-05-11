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
        new Components.CustomSelect('home-game-select', 'home-game-select-ui');
        new Components.CustomSelect('fixgame-game-select', 'fixgame-game-select-ui');
        new Components.CustomSelect('store-sort', 'store-sort-ui');
        new Components.CustomSelect('setting-gl-version', 'setting-gl-version-ui');
        new Components.CustomSelect('profile-select', 'profile-select-ui');
        new Components.CustomSelect('setting-language', 'setting-language-ui');
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
                    var _photoMap = {
                        'dawn': 'img/themes/dawn.jpg',
                        'dusk': 'img/themes/dusk.jpg',
                        'flow': 'img/themes/flow.jpg',
                        'lake': 'img/themes/lake.jpg',
                        'midnight-city': 'img/themes/midnightcity.jpg',
                        'snow': 'img/themes/snow.jpg'
                    };
                    var _bgImg = _photoMap[themeId] ? 'url(' + _photoMap[themeId] + ')' : '';
                    document.body.style.backgroundImage = _bgImg;
                    document.body.style.backgroundSize = _bgImg ? 'cover' : '';
                    document.body.style.backgroundPosition = _bgImg ? 'center' : '';
                }
            });

            // Apply saved language for live i18n
            py.get_setting('language', function(lang) {
                if (window.I18n) I18n.applyLanguage(lang || 'en');
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
                    if (result.task === 'auto_gl_setup') {
                        var runBtn = document.getElementById('gl-setup-run');
                        if (runBtn) runBtn.disabled = false;
                        if (result.success && result.applist_path) {
                            var folderInp = document.getElementById('setting-applist-folder');
                            if (folderInp) {
                                folderInp.value = result.applist_path;
                            }
                        }
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

        // Home game search filter
        var homeSearch = document.getElementById('home-game-search');
        if (homeSearch) {
            homeSearch.addEventListener('input', function() {
                _filterGameDropdown(this.value.trim().toLowerCase());
            });
        }

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

        // Radio change — show/hide Ryuu update option
        document.querySelectorAll('input[name="dl-source"]').forEach(function(r) {
            r.addEventListener('change', function() {
                var opt = document.getElementById('ryuu-update-option');
                if (opt) opt.style.display = this.value === 'ryuu' ? 'block' : 'none';
            });
        });

        // Download modal — fastest
        var dlFastest = document.getElementById('dl-fastest');
        if (dlFastest) {
            dlFastest.addEventListener('click', function() {
                var appId = this.dataset.appid;
                var sourceEl = document.querySelector('input[name="dl-source"]:checked');
                var source = sourceEl ? sourceEl.value : 'hubcap';
                var updateEl = document.getElementById('ryuu-request-update');
                var requestUpdate = (source === 'ryuu' && updateEl && updateEl.checked) ? '1' : '0';
                Components.hideModal('download-modal');
                _startDownload(appId, 'fastest', source, requestUpdate);
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

    function _startDownload(appId, mode, source, requestUpdate) {
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
                _executeDownload(appId, mode, source, requestUpdate);
            } else {
                Components.showLibraryModal(libs, function(selectedLib) {
                    Bridge.call('set_active_library', selectedLib);
                    _executeDownload(appId, mode, source, requestUpdate);
                });
            }
        });
    }

    function _executeDownload(appId, mode, source, requestUpdate) {
        Components.showToast('info', 'Starting download for App ' + appId + '...');
        if (mode === 'fastest') {
            var src = source || 'hubcap';
            Bridge.call('download_game_with_source', appId, src, requestUpdate || '0');
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

        var handler = function(json) {
            Bridge.off('depot_history_results', handler);
            if (loading) loading.classList.add('hidden');
            if (table) table.classList.remove('hidden');

            try {
                var groups = JSON.parse(json);
                if (!tbody) return;
                tbody.innerHTML = '';

                // Source color map
                var sourceColors = {
                    'SteamDB': '#c084fc',
                    'Steam CM': '#60a5fa'
                };

                groups.forEach(function(group, gi) {
                    var groupId = 'vg-' + gi;
                    var entries = group.entries || [];
                    var srcColor = sourceColors[group.source] || '#ccc';

                    // Version group header row (collapsible, starts collapsed)
                    var hdr = document.createElement('tr');
                    hdr.className = 'version-group-header';
                    hdr.dataset.group = groupId;
                    hdr.dataset.collapsed = 'true';
                    hdr.style.cssText = 'background:rgba(255,255,255,0.07);cursor:pointer;user-select:none;';
                    hdr.innerHTML =
                        '<td colspan="5" style="font-weight:600;padding:6px 8px;">' +
                        '<span class="vg-chevron" style="display:inline-block;width:16px;margin-right:4px;transition:transform 0.2s;">&#9654;</span>' +
                        '<span style="color:' + srcColor + ';">' + Components.escapeHtml(group.label) + '</span>' +
                        '</td>' +
                        '<td style="text-align:center;" onclick="event.stopPropagation();">' +
                        '<input type="checkbox" class="version-group-check" data-group="' + groupId + '" title="Select all depots in this version">' +
                        '</td>';
                    tbody.appendChild(hdr);

                    // Individual depot rows (hidden by default)
                    entries.forEach(function(entry) {
                        var tr = document.createElement('tr');
                        tr.className = 'version-depot-row';
                        tr.dataset.group = groupId;
                        tr.style.display = 'none';
                        var srcCellColor = sourceColors[group.source] || '';
                        tr.innerHTML =
                            '<td>' + Components.escapeHtml(entry.depot_id) + '</td>' +
                            '<td style="font-family:monospace;font-size:0.85em;">' + Components.escapeHtml(entry.manifest_id) + '</td>' +
                            '<td>' + Components.escapeHtml(group.date === '0000-00-00' ? 'Unknown' : group.date) + '</td>' +
                            '<td>' + Components.escapeHtml(group.branch || '') + '</td>' +
                            '<td style="color:' + srcCellColor + ';">' + Components.escapeHtml(group.source || '') + '</td>' +
                            '<td style="text-align:center;">' +
                            '<input type="checkbox" class="version-check" data-group="' + groupId + '" data-depot="' + Components.escapeHtml(entry.depot_id) + '" data-manifest="' + Components.escapeHtml(entry.manifest_id) + '">' +
                            '</td>';
                        tbody.appendChild(tr);
                    });
                });

                // Click header to expand/collapse depot rows
                tbody.addEventListener('click', function(e) {
                    var hdr = e.target.closest('.version-group-header');
                    if (!hdr) return;
                    // Don't toggle when clicking the checkbox
                    if (e.target.tagName === 'INPUT') return;
                    var gid = hdr.dataset.group;
                    var isCollapsed = hdr.dataset.collapsed === 'true';
                    var rows = tbody.querySelectorAll('.version-depot-row[data-group="' + gid + '"]');
                    var chevron = hdr.querySelector('.vg-chevron');
                    if (isCollapsed) {
                        rows.forEach(function(r) { r.style.display = ''; });
                        hdr.dataset.collapsed = 'false';
                        if (chevron) chevron.style.transform = 'rotate(90deg)';
                    } else {
                        rows.forEach(function(r) { r.style.display = 'none'; });
                        hdr.dataset.collapsed = 'true';
                        if (chevron) chevron.style.transform = '';
                    }
                });

                // Group header checkbox: toggle all depots in that group
                tbody.addEventListener('change', function(e) {
                    if (e.target.classList.contains('version-group-check')) {
                        var gid = e.target.dataset.group;
                        tbody.querySelectorAll('.version-check[data-group="' + gid + '"]').forEach(function(cb) {
                            cb.checked = e.target.checked;
                        });
                    }
                    var checked = tbody.querySelectorAll('.version-check:checked');
                    if (dlBtn) dlBtn.disabled = checked.length === 0;
                });

            } catch(e) {
                Components.showToast('error', 'Failed to load version history');
            }
        };
        Bridge.on('depot_history_results', handler);
        Bridge.call('fetch_depot_history', appId, false);
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

    function _filterGameDropdown(filter) {
        var dropdown = document.querySelector('#home-game-select-ui .custom-select-dropdown');
        if (!dropdown) return;
        var items = dropdown.querySelectorAll('.custom-select-option');
        items.forEach(function(item) {
            var text = (item.textContent || '').toLowerCase();
            item.style.display = (filter && text.indexOf(filter) === -1) ? 'none' : '';
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
            // Re-apply active search filter after dropdown rebuilds
            var searchInp = document.getElementById('home-game-search');
            if (searchInp && searchInp.value.trim()) {
                var filterVal = searchInp.value.trim().toLowerCase();
                setTimeout(function() { _filterGameDropdown(filterVal); }, 60);
            }
        });
    }

    function _getSelectedGameId() {
        var select = document.getElementById('home-game-select');
        return select ? select.value : '';
    }

    var _hvWarningInitialised = false;
    function _initHvWarningModal() {
        if (_hvWarningInitialised) return;
        _hvWarningInitialised = true;

        var cancelBtn = document.getElementById('hv-warning-cancel');
        var okBtn     = document.getElementById('hv-warning-ok');
        var discordA  = document.getElementById('hv-discord-btn');

        if (cancelBtn) {
            cancelBtn.addEventListener('click', function() {
                _hvClearCountdown();
                Components.hideModal('hv-warning-modal');
            });
        }
        if (okBtn) {
            okBtn.addEventListener('click', function() {
                if (this.disabled) return;
                _hvClearCountdown();
                Components.hideModal('hv-warning-modal');
                var appId   = this.dataset.pendingAppId   || '';
                var outside = this.dataset.pendingOutside === '1';
                var path    = this.dataset.pendingPath    || '';
                var oAppId  = this.dataset.pendingOAppId  || '0';
                Bridge.call('set_setting', 'hv_first_use_warned', 'true');
                Bridge.call('open_url', 'https://discord.gg/denuvowo');
                if (outside) {
                    Bridge.call('run_game_action_outside', path, oAppId, 'hv_fix');
                } else {
                    Bridge.call('run_game_action', appId, 'hv_fix');
                }
            });
        }
        if (discordA) {
            discordA.addEventListener('click', function(e) {
                e.preventDefault();
                Bridge.call('open_url', 'https://discord.gg/denuvowo');
            });
        }
    }

    var _hvCountdownTimer = null;
    function _hvClearCountdown() {
        if (_hvCountdownTimer !== null) {
            clearInterval(_hvCountdownTimer);
            _hvCountdownTimer = null;
        }
    }

    function _showHvWarning(onConfirmArgs) {
        _initHvWarningModal();
        var okBtn  = document.getElementById('hv-warning-ok');
        var cdSpan = document.getElementById('hv-countdown');
        if (!okBtn || !cdSpan) return false;

        // Store context for the OK handler
        okBtn.disabled = true;
        okBtn.dataset.pendingAppId   = onConfirmArgs.appId   || '';
        okBtn.dataset.pendingOutside = onConfirmArgs.outside ? '1' : '0';
        okBtn.dataset.pendingPath    = onConfirmArgs.path    || '';
        okBtn.dataset.pendingOAppId  = onConfirmArgs.oAppId  || '0';

        var secs = 20;
        cdSpan.textContent = secs;
        okBtn.innerHTML = 'I Understand \u2014 Continue (<span id="hv-countdown">' + secs + '</span>s)';

        _hvClearCountdown();
        _hvCountdownTimer = setInterval(function() {
            secs--;
            var span = document.getElementById('hv-countdown');
            if (span) span.textContent = secs;
            if (secs <= 0) {
                _hvClearCountdown();
                okBtn.disabled = false;
                okBtn.innerHTML = 'I Understand \u2014 Continue';
            }
        }, 1000);

        Components.showModal('hv-warning-modal');
        return true;
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
                Bridge.callWithCallback('get_setting', 'manifest_update_excludes', function(excludeVal) {
                    var excludedSet = new Set(
                        (excludeVal || '').split(',').map(function(x) { return x.trim(); }).filter(Boolean)
                    );
                    var html = '';
                    games.forEach(function(g) {
                        var safe = (g.name || g.app_id).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        var isExcluded = excludedSet.has(String(g.app_id));
                        html += '<label style="display:flex;align-items:center;gap:8px;padding:5px 2px;cursor:pointer;font-size:13px;">'
                            + '<input type="checkbox" data-appid="' + g.app_id + '"'
                            + (isExcluded ? '' : ' checked')
                            + ' style="accent-color:var(--accent,#e94560);">'
                            + '<span>' + safe + ' <span style="opacity:0.45;font-size:11px;">' + g.app_id + '</span></span>'
                            + '</label>';
                    });
                    listEl.innerHTML = html;
                    if (countEl) countEl.textContent = games.length + ' game' + (games.length !== 1 ? 's' : '');
                });
            });
            return;
        }

        // HyperVisor action — check first-use warning
        if (action === 'hv_fix') {
            // Resolve the game/path context first, then decide whether to show warning
            var hvAppId    = '';
            var hvOutside  = false;
            var hvPath     = '';
            var hvOAppId   = '0';
            if (_outsideMode) {
                hvPath    = (document.getElementById('outside-path-display') || {}).value || '';
                hvOAppId  = (document.getElementById('outside-appid') || {}).value || '0';
                if (!hvPath) {
                    Components.showToast('warning', 'Please select a game folder first.');
                    return;
                }
                hvOutside = true;
            } else {
                hvAppId = _getSelectedGameId();
                if (!hvAppId) {
                    Components.showToast('warning', 'Please select a game from the dropdown first.');
                    return;
                }
            }
            var confirmArgs = { appId: hvAppId, outside: hvOutside, path: hvPath, oAppId: hvOAppId };
            Bridge.callWithCallback('get_setting', 'hv_first_use_warned', function(val) {
                var warned = val === 'True' || val === 'true' || val === '1';
                if (!warned) {
                    _showHvWarning(confirmArgs);
                } else {
                    if (hvOutside) {
                        Bridge.call('run_game_action_outside', hvPath, hvOAppId, 'hv_fix');
                    } else {
                        Bridge.call('run_game_action', hvAppId, 'hv_fix');
                    }
                }
            });
            return;
        }

        if (action === 'auto_gl_setup') {
            _initGlSetupModal();
            Bridge.callWithCallback('get_setting', 'steam_path', function(steamPath) {
                var steamExeInp = document.getElementById('gl-steam-exe');
                if (steamExeInp && steamPath && !steamExeInp.value) {
                    steamExeInp.value = steamPath.replace(/[\\/]$/, '') + '\\steam.exe';
                }
            });
            Components.showModal('gl-setup-modal');
            return;
        }

        // Non-game actions don't need a game selected
        var nonGameActions = [
            'download_games', 'download_manifests', 'recent_lua', 'update_manifests',
            'mute_toggle', 'remove_game', 'context_menu', 'applist_menu', 'offline_fix',
            'check_updates', 'scan_library', 'analytics', 'auto_gl_setup'
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

    var _glSetupInitialized = false;
    function _initGlSetupModal() {
        if (_glSetupInitialized) return;
        _glSetupInitialized = true;

        var archiveBrowse = document.getElementById('gl-archive-browse');
        if (archiveBrowse) {
            archiveBrowse.addEventListener('click', function() {
                Bridge.callSync('open_archive_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('gl-archive-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        var steamBrowse = document.getElementById('gl-steam-browse');
        if (steamBrowse) {
            steamBrowse.addEventListener('click', function() {
                Bridge.callSync('open_exe_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('gl-steam-exe');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        var runBtn = document.getElementById('gl-setup-run');
        if (runBtn) {
            runBtn.addEventListener('click', function() {
                var archivePath = (document.getElementById('gl-archive-path') || {}).value || '';
                var steamExe = (document.getElementById('gl-steam-exe') || {}).value || '';
                var methodEl = document.querySelector('input[name="gl-method"]:checked');
                var method = methodEl ? methodEl.value : 'A';
                if (!archivePath) {
                    Components.showToast('warning', 'Please select the GreenLuma archive first');
                    return;
                }
                runBtn.disabled = true;
                Components.hideModal('gl-setup-modal');
                Bridge.call('auto_gl_setup_action', JSON.stringify({
                    method: method,
                    archive_path: archivePath,
                    steam_exe: steamExe
                }));
            });
        }
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
