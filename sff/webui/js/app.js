/**
 * SteaMidra — Main App Router & Sidebar Navigation
 * Handles page switching, platform detection, and global initialization.
 */

window.App = (function() {
    'use strict';

    var _currentPage = 'home';
    var _platform = 'win32';
    var _platformReady = false;
    var _outsideMode = false;
    var _letUpdatesHelper = null;
    var _lcHomeNoticeBusy = false;
    var _liveLogMaxLines = 100;
    var _versionHistoryHandler = null;
    var _versionHistorySession = 0;
    var _versionImportedGroups = [];

    function _pathToFileUrl(path) {
        if (!path) return '';
        if (/^file:/i.test(path)) return path;
        return 'file:///' + String(path).replace(/\\/g, '/').replace(/^\/+/, '');
    }

    function applyCustomAppearance(backgroundPath, accentColor) {
        if (backgroundPath) {
            var url = _pathToFileUrl(backgroundPath) + '?t=' + Date.now();
            document.body.style.backgroundImage = 'url("' + url + '")';
            document.body.style.backgroundSize = 'cover';
            document.body.style.backgroundPosition = 'center';
        } else {
            clearCustomAppearance(true);
        }
        if (accentColor && /^#[0-9a-fA-F]{6}$/.test(accentColor)) {
            document.documentElement.style.setProperty('--accent', accentColor);
            document.documentElement.style.setProperty('--sidebar-active', accentColor);
        }
    }

    function clearCustomAppearance(backgroundOnly) {
        document.body.style.backgroundImage = '';
        document.body.style.backgroundSize = '';
        document.body.style.backgroundPosition = '';
        if (!backgroundOnly) {
            document.documentElement.style.removeProperty('--accent');
            document.documentElement.style.removeProperty('--sidebar-active');
        }
    }

    function _loadCustomAppearance(py) {
        py.get_setting('custom_background_image', function(bgPath) {
            py.get_setting('custom_accent_color', function(accent) {
                applyCustomAppearance(bgPath || '', accent || '');
            });
        });
    }

    function init() {
        Components.initModals();
        new Components.CustomSelect('home-game-select', 'home-game-select-ui');
        new Components.CustomSelect('fixgame-game-select', 'fixgame-game-select-ui');
        new Components.CustomSelect('store-sort', 'store-sort-ui');
        new Components.CustomSelect('setting-language', 'setting-language-ui');
        new Components.CustomSelect('dl-target-os', 'dl-target-os-ui');
        new Components.CustomSelect('ddmod-home-target-os', 'ddmod-home-target-os-ui');
        new Components.CustomSelect('library-drive-select', 'library-drive-select-ui');
        Tooltips.init();
        _initSidebar();
        _initLogPanel();
        _initEacGuideButton();
        _initHintToggle();
        _initGlobalListeners();
        _initDepotEdit();
        if (window.DlcCheck) DlcCheck.init();
        window.addEventListener('live-log-limit-changed', function(ev) {
            _setLiveLogMaxLines(ev.detail);
        });

        Bridge.onReady(function(py) {
            if (py && py.signal_ready) {
                try { py.signal_ready(); } catch (e) {}
            }
            // Detect platform
            py.get_platform(function(platform) {
                _platform = platform || 'win32';
                _platformReady = true;
                document.body.classList.add('platform-' + _platform);
                // Hide Windows-only elements on Linux
                if (_platform !== 'win32') {
                    document.querySelectorAll('.platform-win').forEach(function(el) {
                        el.style.display = 'none';
                    });
                }
                if (_currentPage === 'home') _refreshHomeLumacoreNotice();
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
                _loadCustomAppearance(py);
            });

            // Apply saved language for live i18n
            py.get_setting('language', function(lang) {
                if (window.I18n) I18n.applyLanguage(lang || 'en');
            });

            py.get_setting('live_log_max_lines', function(limit) {
                _setLiveLogMaxLines(limit || '100');
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
            document.getElementById('home-toggle-ui').addEventListener('click', function() {
                Bridge.call('toggle_ui');
            });

            var homeRefreshBtn = document.getElementById('home-game-refresh');
            if (homeRefreshBtn) homeRefreshBtn.addEventListener('click', _populateGameDropdown);
            _initHomeProviderControls();

            // Listen to global signals
            Bridge.on('task_finished', function(json) {
                try {
                    var result = JSON.parse(json);
                    // Steamless / Remove SteamStub DRM: show a proper alert because the
                    // explanation is too long for a 4s toast and users need
                    // to read it (e.g. "wrapper variant Steamless cannot
                    // unpack yet — try SteamAutoCrack").
                    if (result.task === 'steamstub' && result.message) {
                        var prefix = result.success ? '' : '[Steamless] ';
                        window.alert(prefix + result.message);
                        Components.showToast(
                            result.success ? 'success' : 'error',
                            result.success ? 'DRM removed' : 'DRM removal failed (see log)'
                        );
                        return;
                    }
                    if (result.task === 'provider_update' && result.background) {
                        _updateHomeProviderStatus(result);
                        return;
                    }
                    if (result.message) {
                        Components.showToast(
                            result.success ? 'success' : 'error',
                            result.message
                        );
                    }
                    if (result.task === 'download_fastest' && result.success) {
                        var addedKey = 'Added to library. Open Steam to download.';
                        var addedMsg = (window.I18n && I18n.t) ? I18n.t(addedKey) : addedKey;
                        Components.showToast('success', addedMsg);
                        _populateGameDropdown();
                        if (result.is_windows && result.app_id) {
                            var fastAutoUpdateMsg = 'Game downloaded successfully.\n\nWould you like to enable auto-updates for this game?\n(Keeps the Steam Update button visible for this game.)';
                            if (window.confirm(fastAutoUpdateMsg)) {
                                Bridge.call('let_updates_add_game', String(result.app_id));
                            }
                        }
                    }
                    if (result.task === 'download_ddmod' && result.success) {
                        _populateGameDropdown();
                        if (result.is_windows && result.app_id) {
                            var autoUpdateMsg = 'Game downloaded successfully.\n\nWould you like to enable auto-updates for this game?\n(Keeps the Steam Update button visible for this game.)';
                            if (window.confirm(autoUpdateMsg)) {
                                Bridge.call('let_updates_add_game', String(result.app_id));
                            }
                        }
                    }
                    if (result.task === 'auto_lc_setup') {
                        var runBtn = document.getElementById('lc-install-run');
                        if (runBtn) runBtn.disabled = false;
                        var statusEl = document.getElementById('lc-setup-status');
                        if (statusEl) statusEl.textContent = result.success ? 'LumaCore installed.' : (result.message || 'Setup failed.');
                        if (result.success) _refreshLcVersionInfo();
                        if (_currentPage === 'home') _refreshHomeLumacoreNotice(true);
                    }
                    if (result.task === 'auto_lc_deactivate') {
                        var deactBtn = document.getElementById('lc-deactivate-run');
                        if (deactBtn) deactBtn.disabled = false;
                        var statusElDeact = document.getElementById('lc-setup-status');
                        if (statusElDeact) statusElDeact.textContent = result.message || (result.success ? 'LumaCore deactivated.' : 'Deactivate failed.');
                        if (result.success) _refreshLcVersionInfo();
                        if (_currentPage === 'home') _refreshHomeLumacoreNotice(true);
                        Components.showToast(
                            result.success ? 'success' : 'error',
                            result.message || (result.success ? 'LumaCore deactivated.' : 'Deactivate failed.')
                        );
                    }
                    if (result.task === 'lc_online_fix') {
                        var ofStatus = document.getElementById('lc-onlinefix-status');
                        if (ofStatus) ofStatus.textContent = result.success ? (result.message || 'Done.') : (result.message || 'Failed.');
                    }
                    if (result.task === 'ryuu_request_branch') {
                        Components.showToast(
                            result.success ? 'success' : 'error',
                            result.success ? ('Branch requested: ' + (result.message || 'OK')) : (result.message || result.error || 'Request failed')
                        );
                    }
                    if (result.task === 'api_key_connected') {
                        Store.onApiKeyAvailable('');
                    }
                    if (result.task === 'provider_contribute' || result.task === 'provider_update') {
                        _updateHomeProviderStatus(result);
                    }
                    if (result.task === 'store_metadata' && result.success && _currentPage === 'store' && window.Store && Store.refresh) {
                        Store.refresh();
                    }
                    if (result.task === 'store_metadata_refresh') {
                        var btn = document.getElementById('store-update-list-btn');
                        if (btn) { btn.disabled = false; btn.textContent = 'Update List'; }
                        if (result.success) {
                            Components.showToast('success', result.message || 'Store lists updated.');
                            if (_currentPage === 'store' && window.Store && Store.refresh) {
                                Store.refresh();
                            }
                        } else {
                            Components.showToast('error', result.message || 'Failed to update store lists.');
                        }
                    }
                    if (result.task === 'check_updates') {
                        // A5: restore the Settings Update button.
                        var updBtn = document.getElementById('about-update');
                        if (updBtn) {
                            updBtn.disabled = false;
                            if (updBtn.dataset.originalHtml) {
                                updBtn.innerHTML = updBtn.dataset.originalHtml;
                                delete updBtn.dataset.originalHtml;
                            }
                        }
                    }
                } catch(e) {}
            });

            Bridge.on('log_message', function(msg) {
                // Python side batches log lines and joins them with
                // newlines so one emit can carry up to 200 lines.
                // Split here so each line still becomes its own DOM node
                // with the right level styling, but only one DOM append
                // batch per emit (10/sec under load) instead of per
                // producer line (thousands/sec under load).
                if (typeof msg !== 'string' || msg.length === 0) return;
                var lines = msg.split('\n');
                // Only update the home log panel when the home page is
                // active. The home log was getting hit on every line
                // even when the user was on Library / Downloads, which
                // doubled DOM work and forced two scrollTop reflows
                // per line. That is what locked up DDMod downloads in
                // the modern UI on Linux/XFCE and stuttered Windows.
                var updateHomeLog = (_currentPage === 'home');
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line.length === 0) continue;
                    _appendLog(line);
                    if (updateHomeLog) {
                        _appendHomeLog(line);
                    }
                }
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

    function _getPageModule(pageId) {
        switch(pageId) {
            case 'store': return window.Store;
            case 'library': return window.Library;
            case 'downloads': return window.Downloads;
            case 'fixgame': return window.FixGame;
            case 'tools': return window.Tools;
            case 'cloudsaves': return window.CloudSaves;
            case 'settings': return window.Settings;
            default: return null;
        }
    }

    function navigateTo(pageId) {
        if (_currentPage && _currentPage !== pageId) {
            var oldModule = _getPageModule(_currentPage);
            if (oldModule && typeof oldModule.onPageLeave === 'function') {
                try { oldModule.onPageLeave(); } catch(e) {}
            }
        }

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
            case 'home':
                _populateGameDropdown();
                _refreshHomeLumacoreNotice();
                break;
            case 'store': Store.onPageEnter(); break;
            case 'library': Library.onPageEnter(); break;
            case 'downloads': Downloads.onPageEnter(); break;
            case 'fixgame': FixGame.onPageEnter(); break;
            case 'cloudsaves': CloudSaves.onPageEnter(); break;
            case 'settings': Settings.onPageEnter(); break;
        }
    }

    var _logMinLevel = 20; // INFO by default

    function _initEacGuideButton() {
        var btn = document.getElementById('btn-eac-guide');
        if (!btn) return;
        btn.addEventListener('click', function(ev) {
            ev.preventDefault();
            ev.stopPropagation();
            Components.showModal('eac-guide-modal');
            _resetEacPages();
        });
        _wireEacTabs();
    }

    function _initHintToggle() {
        var banner = document.getElementById('home-hint-banner');
        var btn = document.getElementById('home-hint-toggle');
        if (!banner || !btn) return;
        btn.addEventListener('click', function() {
            banner.classList.toggle('collapsed');
        });
    }

    function _resetEacPages() {
        var tabs = document.querySelectorAll('#eac-guide-modal .eac-tab');
        var pages = document.querySelectorAll('#eac-guide-modal .eac-page');
        tabs.forEach(function(t) { t.classList.toggle('eac-tab-active', t.getAttribute('data-page') === '1'); });
        pages.forEach(function(p) { p.classList.toggle('hidden', p.getAttribute('data-page') !== '1'); });
    }

    function _wireEacTabs() {
        var tabs = document.querySelectorAll('#eac-guide-modal .eac-tab');
        if (!tabs || tabs.length === 0) return;
        tabs.forEach(function(tab) {
            tab.addEventListener('click', function(ev) {
                ev.preventDefault();
                var target = tab.getAttribute('data-page');
                document.querySelectorAll('#eac-guide-modal .eac-tab').forEach(function(t) {
                    t.classList.toggle('eac-tab-active', t === tab);
                });
                document.querySelectorAll('#eac-guide-modal .eac-page').forEach(function(p) {
                    p.classList.toggle('hidden', p.getAttribute('data-page') !== target);
                });
            });
        });
    }

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

    // Pending scroll requests for the two log containers. Multiple
    // appendLog calls in the same tick coalesce to ONE scroll-to-bottom
    // via rAF, so a 200-line burst from DDMod no longer forces 200
    // synchronous reflows of a 1000-row scroll container.
    var _scrollLogPanelRAF = false;
    var _scrollHomeLogRAF = false;

    function _parseLiveLogMaxLines(value) {
        var parsed = parseInt(value, 10);
        if (!isFinite(parsed)) parsed = 100;
        if (parsed < 50) parsed = 50;
        if (parsed > 5000) parsed = 5000;
        return parsed;
    }

    function _trimLogContainer(content) {
        if (!content) return;
        while (content.children.length > _liveLogMaxLines) {
            content.removeChild(content.firstChild);
        }
    }

    function _setLiveLogMaxLines(value) {
        _liveLogMaxLines = _parseLiveLogMaxLines(value);
        _trimLogContainer(document.getElementById('log-panel-content'));
        _trimLogContainer(document.getElementById('home-log-content'));
    }

    function _scheduleScrollLogPanel(content) {
        if (_scrollLogPanelRAF) return;
        _scrollLogPanelRAF = true;
        requestAnimationFrame(function() {
            _scrollLogPanelRAF = false;
            content.scrollTop = content.scrollHeight;
        });
    }

    function _scheduleScrollHomeLog(content) {
        if (_scrollHomeLogRAF) return;
        _scrollHomeLogRAF = true;
        requestAnimationFrame(function() {
            _scrollHomeLogRAF = false;
            content.scrollTop = content.scrollHeight;
        });
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
        _trimLogContainer(content);
        _scheduleScrollLogPanel(content);
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
        _trimLogContainer(content);
        _scheduleScrollHomeLog(content);
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

    function _nameFromOutsidePath(path) {
        var cleaned = (path || '').toString().replace(/[\\\/]+$/, '');
        if (!cleaned) return '';
        var parts = cleaned.split(/[\\\/]+/);
        return (parts[parts.length - 1] || '').trim();
    }

    function _getOutsideGameName(path) {
        var inp = document.getElementById('outside-game-name');
        var value = inp ? (inp.value || '').trim() : '';
        return value || _nameFromOutsidePath(path);
    }

    function _initGlobalListeners() {
        // Game source toggle (Steam vs outside)
        var srcSteam   = document.getElementById('game-source-steam');
        var srcOutside = document.getElementById('game-source-outside');
        if (srcSteam) srcSteam.addEventListener('change', function() {
            _outsideMode = false;
            document.getElementById('steam-mode-row').style.display   = 'flex';
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
                if (path) {
                    document.getElementById('outside-path-display').value = path;
                    var nameInp = document.getElementById('outside-game-name');
                    if (nameInp && !nameInp.value.trim()) {
                        nameInp.value = _nameFromOutsidePath(path);
                    }
                }
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

        var lcAlertAction = document.getElementById('home-lumacore-alert-action');
        if (lcAlertAction) {
            lcAlertAction.addEventListener('click', function(ev) {
                ev.preventDefault();
                _handleHomeAction('auto_lc_setup');
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

        // Radio change — show/hide Ryuu update option, local file row, and manifest folder row
        document.querySelectorAll('input[name="dl-source"]').forEach(function(r) {
            r.addEventListener('change', function() {
                var opt = document.getElementById('ryuu-update-option');
                var localRow = document.getElementById('dl-local-row');
                var mfRow = document.getElementById('dl-manifest-folder-row');
                if (opt) opt.style.display = this.value === 'ryuu' ? 'block' : 'none';
                if (localRow) localRow.style.display = this.value === 'local' ? 'block' : 'none';
                if (mfRow && this.value !== 'local') mfRow.style.display = 'none';
            });
        });

        // Ryuu branch refresh button
        var ryuuRefreshBtn = document.getElementById('ryuu-refresh-branches');
        if (ryuuRefreshBtn) {
            ryuuRefreshBtn.addEventListener('click', function(e) {
                e.preventDefault();
                if (ryuuRefreshBtn.disabled) return;
                ryuuRefreshBtn.disabled = true;
                var appId = (document.getElementById('dl-fastest') || {}).dataset.appid || '';
                if (!appId) { ryuuRefreshBtn.disabled = false; return; }
                var sel = document.getElementById('ryuu-branch-select');
                if (sel) sel.innerHTML = '<option value="public">public (fetching...)</option>';
                Bridge.callWithCallback('refresh_game_branches', appId, function(json) {
                    Components._populateRyuuBranches(json);
                    ryuuRefreshBtn.disabled = false;
                });
            });
        }

        // Ryuu request branch button
        var ryuuReqBranchBtn = document.getElementById('ryuu-request-branch-btn');
        if (ryuuReqBranchBtn) {
            ryuuReqBranchBtn.addEventListener('click', function(e) {
                e.preventDefault();
                var appId = (document.getElementById('dl-fastest') || {}).dataset.appid || '';
                var sel = document.getElementById('ryuu-branch-select');
                var branch = sel ? sel.value : 'public';
                if (!appId || branch === 'public') {
                    Components.showToast('warning', 'Select a non-public branch first.');
                    return;
                }
                Components.showToast('info', 'Requesting branch ' + branch + ' for App ' + appId + '...');
                Bridge.call('ryuu_request_branch', appId, branch);
            });
        }

        // Download modal — browse local lua/zip file
        var dlLocalBrowse = document.getElementById('dl-local-lua-browse');
        if (dlLocalBrowse) {
            dlLocalBrowse.addEventListener('click', function() {
                Bridge.callSync('open_lua_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('dl-local-lua-path');
                        if (inp) inp.value = path;
                        var mfRow = document.getElementById('dl-manifest-folder-row');
                        if (mfRow) {
                            var ext = path.split('.').pop().toLowerCase();
                            mfRow.style.display = (ext === 'lua') ? 'block' : 'none';
                        }
                    }
                });
            });
        }

        // Download modal — browse manifest folder
        var dlMfBrowse = document.getElementById('dl-manifest-folder-browse');
        if (dlMfBrowse) {
            dlMfBrowse.addEventListener('click', function() {
                Bridge.callSync('open_manifest_folder_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('dl-manifest-folder-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        // Download modal — choose DDMod destination
        var dlDdmodDestBrowse = document.getElementById('dl-ddmod-dest-browse');
        if (dlDdmodDestBrowse) {
            dlDdmodDestBrowse.addEventListener('click', function() {
                Bridge.callSync('browse_ddmod_download_folder', function(path) {
                    if (path) {
                        var inp = document.getElementById('dl-ddmod-dest-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }
        var dlDdmodDestClear = document.getElementById('dl-ddmod-dest-clear');
        if (dlDdmodDestClear) {
            dlDdmodDestClear.addEventListener('click', function() {
                var inp = document.getElementById('dl-ddmod-dest-path');
                if (inp) inp.value = '';
            });
        }

        // Download modal — fastest
        var dlFastest = document.getElementById('dl-fastest');
        if (dlFastest) {
            dlFastest.addEventListener('click', function() {
                var appId = this.dataset.appid;
                var sourceEl = document.querySelector('input[name="dl-source"]:checked');
                var source = sourceEl ? sourceEl.value : 'oureveryday';
                var updateEl = document.getElementById('ryuu-request-update');
                var requestUpdate = (source === 'ryuu' && updateEl && updateEl.checked) ? '1' : '0';
                var branch = '';
                var fileType = '';
                if (source === 'ryuu') {
                    var branchSel = document.getElementById('ryuu-branch-select');
                    if (branchSel) branch = branchSel.value || 'public';
                    var ftSel = document.getElementById('ryuu-file-type');
                    if (ftSel) fileType = ftSel.value || 'zip';
                }
                Components.hideModal('download-modal');
                if (source === 'local') {
                    var luaPath = (document.getElementById('dl-local-lua-path') || {}).value || '';
                    if (!luaPath) {
                        Components.showToast('warning', 'Please select a local .lua or archive file first.');
                        return;
                    }
                    var manifestFolder = (document.getElementById('dl-manifest-folder-path') || {}).value || '';
                    Bridge.call('download_game_with_source', appId, source, requestUpdate, luaPath, manifestFolder);
                } else {
                    _startDownload(appId, 'fastest', source, requestUpdate);
                }
            });
        }

        // Download modal — older version
        var dlOlder = document.getElementById('dl-older');
        if (dlOlder) {
            dlOlder.addEventListener('click', function() {
                var appId = this.dataset.appid;
                Components.hideModal('download-modal');
                var sourceEl = document.querySelector('input[name="dl-source"]:checked');
                window._olderVersionSource = sourceEl ? sourceEl.value : 'oureveryday';
                var saved = localStorage.getItem('older_version_method') || '';
                if (saved) {
                    window._olderVersionMethod = saved;
                    _showVersionPicker(appId);
                    return;
                }
                Bridge.callSync('get_platform', function(platform) {
                    if (platform === 'win32') {
                        var methodModal = document.getElementById('older-method-modal');
                        if (methodModal) {
                            methodModal.querySelectorAll('.download-option').forEach(function(b) {
                                b.dataset.appid = appId;
                            });
                            Components.showModal('older-method-modal');
                        }
                    } else {
                        window._olderVersionMethod = 'ddmod';
                        _showVersionPicker(appId);
                    }
                });
            });
        }

        // Older method choice — DDMod
        document.getElementById('older-method-ddmod')?.addEventListener('click', function() {
            var appId = this.dataset.appid;
            window._olderVersionMethod = 'ddmod';
            Components.hideModal('older-method-modal');
            _showVersionPicker(appId);
        });

        // Older method choice — Steam Native
        document.getElementById('older-method-steam')?.addEventListener('click', function() {
            var appId = this.dataset.appid;
            window._olderVersionMethod = 'steam_native';
            Components.hideModal('older-method-modal');
            _showVersionPicker(appId);
        });

        // Download modal — direct DDMod
        var dlDdmod = document.getElementById('dl-ddmod');
        if (dlDdmod) {
            dlDdmod.addEventListener('click', function() {
                var appId = this.dataset.appid;
                if (!appId) {
                    Components.showToast('error', 'No App ID. Select a game and try again.');
                    return;
                }
                var sourceEl = document.querySelector('input[name="dl-source"]:checked');
                var source = sourceEl ? sourceEl.value : 'oureveryday';
                var luaPath = '';
                var manifestFolder = '';
                if (source === 'local') {
                    luaPath = (document.getElementById('dl-local-lua-path') || {}).value || '';
                    if (!luaPath) {
                        Components.showToast('warning', 'Please select a local .lua or archive file first.');
                        return;
                    }
                    manifestFolder = (document.getElementById('dl-manifest-folder-path') || {}).value || '';
                }
                var destPath = (document.getElementById('dl-ddmod-dest-path') || {}).value || '';
                var targetOs = (document.getElementById('dl-target-os') || {}).value || '';

                function doDownload(dest) {
                    Components.hideModal('download-modal');
                    _startDdmodDownload(appId, source, luaPath, manifestFolder, targetOs, dest);
                }

                if (!destPath && _platform === 'linux') {
                    // Linux: show Steam library picker before download
                    Bridge.callSync('get_steam_libraries', function(json) {
                        var libs;
                        try { libs = JSON.parse(json || '[]'); } catch(e) { libs = []; }
                        var container = document.getElementById('library-options');
                        if (!container) { doDownload(destPath); return; }
                        container.innerHTML = '';

                        // Custom folder option first
                        var customBtn = document.createElement('button');
                        customBtn.className = 'library-option';
                        customBtn.textContent = 'Custom folder (outside Steam, no ACF written)';
                        customBtn.style.color = 'var(--accent, #e94560)';
                        customBtn.addEventListener('click', function() {
                            Components.hideModal('library-modal');
                            Bridge.callSync('browse_ddmod_download_folder', function(customPath) {
                                if (customPath) doDownload(customPath);
                            });
                        });
                        container.appendChild(customBtn);

                        // Steam library options
                        libs.forEach(function(libPath) {
                            var btn = document.createElement('button');
                            btn.className = 'library-option';
                            btn.textContent = libPath + ' (Steam Library)';
                            btn.addEventListener('click', function() {
                                Components.hideModal('library-modal');
                                doDownload(libPath);
                            });
                            container.appendChild(btn);
                        });

                        if (libs.length === 0) {
                            var noLib = document.createElement('span');
                            noLib.style.opacity = '0.6';
                            noLib.style.fontSize = '13px';
                            noLib.textContent = 'No Steam libraries found. Use Custom folder.';
                            container.appendChild(noLib);
                        }

                        Components.showModal('library-modal');
                    });
                    return;
                }

                if (!destPath) {
                    Components.showToast('warning', 'Choose a DDMod download location first.');
                    return;
                }

                doDownload(destPath);
            });
        }

        // DDMod choose modal (home tab) — Through Steam button
        var ddmodChooseSteam = document.getElementById('ddmod-choose-steam');
        if (ddmodChooseSteam) {
            ddmodChooseSteam.addEventListener('click', function() {
                var appId = this.dataset.appid || '';
                Components.hideModal('ddmod-choose-modal');
                _openSteamHomeModal(appId);
            });
        }

        // Steam home modal — source radio change
        document.querySelectorAll('input[name="steam-home-source"]').forEach(function(r) {
            r.addEventListener('change', function() {
                var ryuuOpt = document.getElementById('steam-home-ryuu-option');
                var localRow = document.getElementById('steam-home-local-row');
                var mfRow = document.getElementById('steam-home-manifest-row');
                var recentRow = document.getElementById('steam-home-recent-row');
                if (ryuuOpt) ryuuOpt.style.display = this.value === 'ryuu' ? 'block' : 'none';
                if (localRow) localRow.style.display = this.value === 'local' ? 'block' : 'none';
                if (recentRow) recentRow.style.display = this.value === 'recent' ? 'block' : 'none';
                if (mfRow) mfRow.style.display = this.value === 'local' ? 'block' : 'none';
            });
        });

        // Steam home modal — browse local lua/zip
        var steamHomeBrowseLocal = document.getElementById('steam-home-local-browse');
        if (steamHomeBrowseLocal) {
            steamHomeBrowseLocal.addEventListener('click', function() {
                Bridge.callSync('open_lua_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('steam-home-local-path');
                        if (inp) inp.value = path;
                        var mfRow = document.getElementById('steam-home-manifest-row');
                        if (mfRow) {
                            var ext = path.split('.').pop().toLowerCase();
                            mfRow.style.display = (ext === 'lua') ? 'block' : 'none';
                        }
                    }
                });
            });
        }

        // Steam home modal — browse manifest folder
        var steamHomeBrowseMf = document.getElementById('steam-home-manifest-browse');
        if (steamHomeBrowseMf) {
            steamHomeBrowseMf.addEventListener('click', function() {
                Bridge.callSync('open_manifest_folder_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('steam-home-manifest-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        // Steam home modal — Browse game button
        var steamHomeBrowseGame = document.getElementById('steam-home-browse-game');
        if (steamHomeBrowseGame) {
            steamHomeBrowseGame.addEventListener('click', function() {
                _openSteamGamePicker();
            });
        }

        // Steam game picker — update list button
        var sgpUpdateBtn = document.getElementById('sgp-update-btn');
        if (sgpUpdateBtn) {
            sgpUpdateBtn.addEventListener('click', function() {
                _sgpStartUpdate();
            });
        }

        // Steam game picker — search input (debounced)
        var sgpSearch = document.getElementById('sgp-search');
        if (sgpSearch) {
            var _sgpDebounce = null;
            sgpSearch.addEventListener('input', function() {
                var q = this.value;
                clearTimeout(_sgpDebounce);
                _sgpDebounce = setTimeout(function() { _sgpSearch(q); }, 300);
            });
        }

        // Steam game picker — select button
        var sgpSelectBtn = document.getElementById('sgp-select');
        if (sgpSelectBtn) {
            sgpSelectBtn.addEventListener('click', function() {
                var selected = document.querySelector('#sgp-list .sgp-item.selected');
                if (!selected) return;
                var appId = selected.dataset.appid || '';
                var name = selected.dataset.name || '';
                var display = document.getElementById('steam-home-game-display');
                if (display) {
                    display.dataset.appid = appId;
                    display.textContent = name + ' [ID=' + appId + ']';
                }
                Components.hideModal('steam-game-picker-modal');
                Components.showModal('steam-home-modal');
            });
        }

        // Listen for game list update result
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'update_games_file') {
                    var btn = document.getElementById('sgp-update-btn');
                    if (btn) { btn.disabled = false; btn.textContent = 'Update list'; }
                    if (data.success) {
                        _sgpRefreshInfo();
                        _sgpSearch(document.getElementById('sgp-search') ? document.getElementById('sgp-search').value : '');
                        Components.showToast('info', data.message || 'Game list updated.');
                    } else {
                        Components.showToast('error', data.message || 'Failed to update game list.');
                    }
                }
            } catch(e) {}
        });

        // Steam home modal — Download button
        var steamHomeDownload = document.getElementById('steam-home-download');
        if (steamHomeDownload) {
            steamHomeDownload.addEventListener('click', function() {
                var display = document.getElementById('steam-home-game-display');
                var appId = (display && display.dataset.appid) ? display.dataset.appid.trim() : '';
                if (!appId || !/^\d+$/.test(appId)) {
                    Components.showToast('warning', 'Please select a game first.');
                    return;
                }
                var sourceEl = document.querySelector('input[name="steam-home-source"]:checked');
                var source = sourceEl ? sourceEl.value : 'oureveryday';
                var updateEl = document.getElementById('steam-home-request-update');
                var requestUpdate = (source === 'ryuu' && updateEl && updateEl.checked) ? '1' : '0';
                Components.hideModal('steam-home-modal');
                if (source === 'local') {
                    var luaPath = (document.getElementById('steam-home-local-path') || {}).value || '';
                    if (!luaPath) {
                        Components.showToast('warning', 'Please select a local .lua or archive file first.');
                        Components.showModal('steam-home-modal');
                        return;
                    }
                    var mf = (document.getElementById('steam-home-manifest-path') || {}).value || '';
                    Components.showToast('info', 'Importing local Lua for App ' + appId + '...');
                    Bridge.call('import_local_lua', appId, luaPath, mf);
                } else if (source === 'recent') {
                    var recentPath = (document.getElementById('steam-home-recent-select') || {}).value || '';
                    if (!recentPath) {
                        Components.showToast('warning', 'Please select a recent file.');
                        Components.showModal('steam-home-modal');
                        return;
                    }
                    Components.showToast('info', 'Importing recent Lua for App ' + appId + '...');
                    Bridge.call('import_local_lua', appId, recentPath, '');
                } else {
                    _startDownload(appId, 'fastest', source, requestUpdate);
                }
            });
        }

        // DDMod choose modal (home tab) — Via DDMod button
        var ddmodChooseDdmod = document.getElementById('ddmod-choose-ddmod');
        if (ddmodChooseDdmod) {
            ddmodChooseDdmod.addEventListener('click', function() {
                var appId = this.dataset.appid || '';
                Components.hideModal('ddmod-choose-modal');
                _openDdmodHomeModal(appId);
            });
        }

        // DDMod home modal — source radio change
        document.querySelectorAll('input[name="ddmod-home-source"]').forEach(function(r) {
            r.addEventListener('change', function() {
                var localRow = document.getElementById('ddmod-home-local-row');
                var recentRow = document.getElementById('ddmod-home-recent-row');
                var mfRow = document.getElementById('ddmod-home-manifest-row');
                if (localRow) localRow.style.display = this.value === 'local' ? 'block' : 'none';
                if (recentRow) recentRow.style.display = this.value === 'recent' ? 'block' : 'none';
                if (mfRow && this.value !== 'local') mfRow.style.display = 'none';
            });
        });

        // DDMod home modal — browse local lua/zip file
        var ddmodHomeBrowse = document.getElementById('ddmod-home-local-browse');
        if (ddmodHomeBrowse) {
            ddmodHomeBrowse.addEventListener('click', function() {
                Bridge.callSync('open_lua_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('ddmod-home-local-path');
                        if (inp) inp.value = path;
                        var mfRow = document.getElementById('ddmod-home-manifest-row');
                        if (mfRow) {
                            var ext = path.split('.').pop().toLowerCase();
                            mfRow.style.display = (ext === 'lua') ? 'block' : 'none';
                        }
                    }
                });
            });
        }

        // DDMod home modal — browse manifest folder
        var ddmodHomeMfBrowse = document.getElementById('ddmod-home-manifest-browse');
        if (ddmodHomeMfBrowse) {
            ddmodHomeMfBrowse.addEventListener('click', function() {
                Bridge.callSync('open_manifest_folder_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('ddmod-home-manifest-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        // DDMod home modal — choose download destination
        var ddmodHomeDestBrowse = document.getElementById('ddmod-home-dest-browse');
        if (ddmodHomeDestBrowse) {
            ddmodHomeDestBrowse.addEventListener('click', function() {
                Bridge.callSync('browse_ddmod_download_folder', function(path) {
                    if (path) {
                        var inp = document.getElementById('ddmod-home-dest-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }
        var ddmodHomeDestClear = document.getElementById('ddmod-home-dest-clear');
        if (ddmodHomeDestClear) {
            ddmodHomeDestClear.addEventListener('click', function() {
                var inp = document.getElementById('ddmod-home-dest-path');
                if (inp) inp.value = '';
            });
        }

        // DDMod home modal — Download button
        var ddmodHomeDownload = document.getElementById('ddmod-home-download');
        if (ddmodHomeDownload) {
            ddmodHomeDownload.addEventListener('click', function() {
                var appId = (document.getElementById('ddmod-home-appid') || {}).value || '';
                if (!appId) {
                    Components.showToast('warning', 'Please enter an App ID.');
                    return;
                }
                var sourceEl = document.querySelector('input[name="ddmod-home-source"]:checked');
                var source = sourceEl ? sourceEl.value : 'oureveryday';
                var luaPath = '';
                var manifestFolder = '';
                if (source === 'local') {
                    luaPath = (document.getElementById('ddmod-home-local-path') || {}).value || '';
                    if (!luaPath) {
                        Components.showToast('warning', 'Please select a local .lua or archive file first.');
                        return;
                    }
                    manifestFolder = (document.getElementById('ddmod-home-manifest-path') || {}).value || '';
                } else if (source === 'recent') {
                    luaPath = (document.getElementById('ddmod-home-recent-select') || {}).value || '';
                    if (!luaPath) {
                        Components.showToast('warning', 'Please select a recent file.');
                        return;
                    }
                    source = 'local';
                }
                var destPath = (document.getElementById('ddmod-home-dest-path') || {}).value || '';
                if (!destPath) {
                    Components.showToast('warning', 'Choose a DDMod download location first.');
                    return;
                }
                Components.hideModal('ddmod-home-modal');
                var targetOs = (document.getElementById('ddmod-home-target-os') || {}).value || '';
                _startDdmodDownload(appId, source, luaPath, manifestFolder, targetOs, destPath);
            });
        }

        // Version picker — download selected
        var versionDl = document.getElementById('version-download');
        if (versionDl) {
            versionDl.addEventListener('click', function() {
                _downloadSelectedVersion();
            });
        }
        var versionManualDl = document.getElementById('version-manual-download');
        if (versionManualDl) {
            versionManualDl.addEventListener('click', function() {
                _downloadManualVersion();
            });
        }
        var versionImportHtml = document.getElementById('version-import-html');
        if (versionImportHtml) {
            versionImportHtml.addEventListener('click', function() {
                _importVersionManifestHtml();
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

        var luToggleBtn = document.getElementById('lu-toggle-all');
        if (luToggleBtn) {
            luToggleBtn.addEventListener('click', function() {
                var checkboxes = document.querySelectorAll('#lu-game-list input[type="checkbox"]');
                var allChecked = Array.prototype.every.call(checkboxes, function(cb) { return cb.checked; });
                checkboxes.forEach(function(cb) { cb.checked = !allChecked; });
                luToggleBtn.textContent = allChecked ? 'Select All' : 'Deselect All';
            });
        }

        var luSaveBtn = document.getElementById('let-updates-save');
        if (luSaveBtn) {
            luSaveBtn.addEventListener('click', function() {
                var selected = [];
                document.querySelectorAll('#lu-game-list input[type="checkbox"]:checked').forEach(function(cb) {
                    if (cb.dataset.appid) selected.push(cb.dataset.appid);
                });
                luSaveBtn.disabled = true;
                Bridge.callWithCallback('let_updates_apply', JSON.stringify({ allow_updates: selected }), function(json) {
                    luSaveBtn.disabled = false;
                    var result;
                    try { result = JSON.parse(json || '{}'); } catch(e) { result = { ok: false, error: String(e) }; }
                    if (!result.ok) {
                        Components.showToast('error', result.error || 'Failed to update Lua manifest pins.');
                        return;
                    }
                    Components.hideModal('let-updates-modal');
                    var suffix = result.global_override ? ' Global override updated too.' : '';
                    Components.showToast('success', 'Updated ' + (result.changed_games || 0) + ' game Lua file(s).' + suffix);
                });
            });
        }

        var luAddHelperBtn = document.getElementById('let-updates-add-helper');
        if (luAddHelperBtn) {
            luAddHelperBtn.addEventListener('click', function() {
                _setLetUpdatesHelper(true);
            });
        }

        var luRemoveHelperBtn = document.getElementById('let-updates-remove-helper');
        if (luRemoveHelperBtn) {
            luRemoveHelperBtn.addEventListener('click', function() {
                _setLetUpdatesHelper(false);
            });
        }

        // 6.2.4: restart-after-dl-run handler dropped along with the modal.
        // LumaCore picks up new manifests / keys live, no restart needed.

        // Keyboard navigation for game cards (Enter/Space triggers click on download button)
        document.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            var target = e.target.closest('[role="listitem"]');
            if (!target) return;
            e.preventDefault();
            var dlBtn = target.querySelector('.btn-download');
            if (dlBtn) dlBtn.click();
        });
    }

    function _startDdmodDownload(appId, source, luaPath, manifestFolder, targetOs, destinationPath) {
        var dest = (destinationPath || '').trim();
        if (!dest) {
            Components.showToast('warning', 'Choose a DDMod download location first.');
            return;
        }
        Bridge.call('set_active_library', dest);
        Components.showToast('info', 'Starting DDMod download for App ' + appId + '...');
        Bridge.call('download_game_ddmod', appId, source, luaPath || '', manifestFolder || '', targetOs || '');
    }

    function _openSteamHomeModal(appId, gameName) {
        var display = document.getElementById('steam-home-game-display');
        if (display) {
            if (appId && /^\d+$/.test(appId.trim())) {
                display.dataset.appid = appId.trim();
                display.textContent = (gameName || ('App ' + appId.trim())) + ' [ID=' + appId.trim() + ']';
            } else {
                display.dataset.appid = '';
                display.textContent = 'No game selected';
            }
        }
        var ryuuOpt = document.getElementById('steam-home-ryuu-option');
        if (ryuuOpt) ryuuOpt.style.display = 'none';
        var localRow = document.getElementById('steam-home-local-row');
        if (localRow) localRow.style.display = 'none';
        var mfRow = document.getElementById('steam-home-manifest-row');
        if (mfRow) { mfRow.style.display = 'none'; }
        var mfInp = document.getElementById('steam-home-manifest-path');
        if (mfInp) mfInp.value = '';
        var recentRow = document.getElementById('steam-home-recent-row');
        if (recentRow) recentRow.style.display = 'none';
        var updateChk = document.getElementById('steam-home-request-update');
        if (updateChk) updateChk.checked = false;
        var firstRadio = document.querySelector('input[name="steam-home-source"][value="oureveryday"]');
        if (firstRadio) firstRadio.checked = true;
        Bridge.callSync('get_recent_lua_files', function(json) {
            var files;
            try { files = JSON.parse(json || '[]'); } catch(e) { files = []; }
            var sel = document.getElementById('steam-home-recent-select');
            if (sel) {
                sel.innerHTML = '<option value="">-- select a recent file --</option>';
                files.forEach(function(f) {
                    var opt = document.createElement('option');
                    opt.value = f.path;
                    opt.textContent = f.name;
                    sel.appendChild(opt);
                });
                var recentRadio = document.querySelector('input[name="steam-home-source"][value="recent"]');
                if (recentRadio) recentRadio.disabled = files.length === 0;
            }
        });
        Components.showModal('steam-home-modal');
    }

    function _openSteamGamePicker() {
        Components.hideModal('steam-home-modal');
        var selectBtn = document.getElementById('sgp-select');
        if (selectBtn) selectBtn.disabled = true;
        var srchInp = document.getElementById('sgp-search');
        if (srchInp) srchInp.value = '';
        var list = document.getElementById('sgp-list');
        if (list) list.innerHTML = '';
        _sgpRefreshInfo();
        Components.showModal('steam-game-picker-modal');
        _sgpSearch('');
    }

    function _sgpRefreshInfo() {
        Bridge.callSync('get_games_file_info', function(json) {
            var info;
            try { info = JSON.parse(json || '{}'); } catch(e) { info = {}; }
            var lbl = document.getElementById('sgp-last-updated');
            if (lbl) {
                if (info.exists) {
                    lbl.textContent = 'Last updated: ' + (info.mtime_str || 'unknown') + ' (' + (info.count || 0) + ' games)';
                } else {
                    lbl.textContent = 'No game list found. Click "Update list" to download.';
                }
            }
        });
    }

    function _sgpSearch(query) {
        var list = document.getElementById('sgp-list');
        var empty = document.getElementById('sgp-empty');
        var loading = document.getElementById('sgp-loading');
        if (loading) loading.style.display = 'block';
        if (list) list.style.display = 'none';
        if (empty) empty.style.display = 'none';
        Bridge.callWithCallback('search_games_file', query || '', function(json) {
            var games;
            try { games = JSON.parse(json || '[]'); } catch(e) { games = []; }
            if (loading) loading.style.display = 'none';
            if (!list) return;
            list.style.display = 'block';
            list.innerHTML = '';
            if (games.length === 0) {
                if (empty) empty.style.display = 'block';
                list.style.display = 'none';
                return;
            }
            games.forEach(function(g) {
                var item = document.createElement('div');
                item.className = 'sgp-item';
                item.dataset.appid = g.appid;
                item.dataset.name = g.name;
                item.style.cssText = 'padding:6px 12px; cursor:pointer; font-size:13px; border-bottom:1px solid rgba(255,255,255,0.05);';
                item.textContent = g.name + ' [ID=' + g.appid + ']';
                item.addEventListener('click', function() {
                    list.querySelectorAll('.sgp-item').forEach(function(el) {
                        el.style.background = '';
                        el.classList.remove('selected');
                    });
                    this.style.background = 'rgba(139,92,246,0.25)';
                    this.classList.add('selected');
                    var selectBtn = document.getElementById('sgp-select');
                    if (selectBtn) selectBtn.disabled = false;
                });
                list.appendChild(item);
            });
        });
    }

    function _sgpStartUpdate() {
        var btn = document.getElementById('sgp-update-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Updating...'; }
        Components.showToast('info', 'Downloading game list from Steam...');
        Bridge.call('update_games_file');
    }

    function _openDdmodHomeModal(appId) {
        var appIdInp = document.getElementById('ddmod-home-appid');
        if (appIdInp) appIdInp.value = appId || '';
        var localRow = document.getElementById('ddmod-home-local-row');
        var recentRow = document.getElementById('ddmod-home-recent-row');
        var mfRow = document.getElementById('ddmod-home-manifest-row');
        var mfInp = document.getElementById('ddmod-home-manifest-path');
        var destInp = document.getElementById('ddmod-home-dest-path');
        if (localRow) localRow.style.display = 'none';
        if (recentRow) recentRow.style.display = 'none';
        if (mfRow) mfRow.style.display = 'none';
        if (mfInp) mfInp.value = '';
        if (destInp) destInp.value = '';
        var firstRadio = document.querySelector('input[name="ddmod-home-source"][value="oureveryday"]');
        if (firstRadio) firstRadio.checked = true;

        Bridge.callSync('get_recent_lua_files', function(json) {
            var files;
            try { files = JSON.parse(json || '[]'); } catch(e) { files = []; }
            var sel = document.getElementById('ddmod-home-recent-select');
            if (sel) {
                sel.innerHTML = '<option value="">-- select a recent file --</option>';
                files.forEach(function(f) {
                    var opt = document.createElement('option');
                    opt.value = f.path;
                    opt.textContent = f.name;
                    sel.appendChild(opt);
                });
                var recentRadio = document.querySelector('input[name="ddmod-home-source"][value="recent"]');
                if (recentRadio) recentRadio.disabled = files.length === 0;
            }
        });

        Components.showModal('ddmod-home-modal');
    }

    function _startDownload(appId, mode, source, requestUpdate) {
        // Steam-source path performs no depot pull; the registration helpers
        // run against the resolved steam_path, not a user-picked library.
        // Skip the library picker so the modal stops promising a download.
        _executeDownload(appId, mode, source, requestUpdate);
    }

    function _executeDownload(appId, mode, source, requestUpdate) {
        if (!appId) {
            Components.showToast('error', 'No App ID. Select a game and try again.');
            return;
        }
        Components.showToast('info', 'Starting download for App ' + appId + '...');
        if (mode === 'fastest') {
            var src = source || 'hubcap';
            Bridge.call('download_game_with_source', appId, src, requestUpdate || '0');
        }
    }

    function _renderVersionGroups(groups, options) {
        options = options || {};
        var loading = document.getElementById('version-loading');
        var table = document.getElementById('version-table');
        var tbody = document.getElementById('version-tbody');
        var dlBtn = document.getElementById('version-download');
        if (loading) loading.classList.add('hidden');
        if (table) table.classList.remove('hidden');
        if (dlBtn) dlBtn.disabled = true;
        if (!tbody) return;
        tbody.innerHTML = '';

        var sourceColors = {
            'SteamDB': '#c084fc',
            'Steam CM': '#60a5fa',
            'Imported HTML': '#facc15'
        };

        function _uncheckSameDepotChoices(active) {
            if (!active || !active.checked) return;
            var depot = active.dataset.depot || '';
            if (!depot) return;
            tbody.querySelectorAll('.version-check:checked').forEach(function(cb) {
                if (cb !== active && cb.dataset.depot === depot) {
                    cb.checked = false;
                }
            });
        }

        (groups || []).forEach(function(group, gi) {
            var groupId = 'vg-' + gi;
            var entries = group.entries || [];
            var srcColor = sourceColors[group.source] || '#ccc';
            var expanded = !!options.expanded;
            var depotCounts = {};
            entries.forEach(function(entry) {
                var depot = entry && entry.depot_id ? String(entry.depot_id) : '';
                if (depot) depotCounts[depot] = (depotCounts[depot] || 0) + 1;
            });
            var sameDepotChoices = !!group.single_depot_choices || Object.keys(depotCounts).some(function(depot) {
                return depotCounts[depot] > 1;
            });

            var hdr = document.createElement('tr');
            hdr.className = 'version-group-header';
            hdr.dataset.group = groupId;
            hdr.dataset.collapsed = expanded ? 'false' : 'true';
            hdr.style.cssText = 'background:rgba(255,255,255,0.07);cursor:pointer;user-select:none;';
            hdr.innerHTML =
                '<td colspan="5" style="font-weight:600;padding:6px 8px;">' +
                '<span class="vg-chevron" style="display:inline-block;width:16px;margin-right:4px;transition:transform 0.2s;' +
                (expanded ? 'transform:rotate(90deg);' : '') + '">&#9654;</span>' +
                '<span style="color:' + srcColor + ';">' + Components.escapeHtml(group.label || 'Imported HTML') + '</span>' +
                '</td>' +
                '<td style="text-align:center;" onclick="event.stopPropagation();">' +
                (sameDepotChoices ? '' : '<input type="checkbox" class="version-group-check" data-group="' + groupId + '" title="Select all depots in this version">') +
                '</td>';
            tbody.appendChild(hdr);

            entries.forEach(function(entry) {
                var tr = document.createElement('tr');
                tr.className = 'version-depot-row';
                tr.dataset.group = groupId;
                tr.style.display = expanded ? '' : 'none';
                var rowDate = entry.date || group.date || '';
                var rowBranch = entry.branch || group.branch || '';
                var rowSource = entry.source || group.source || '';
                tr.innerHTML =
                    '<td>' + Components.escapeHtml(entry.depot_id) + '</td>' +
                    '<td style="font-family:monospace;font-size:0.85em;">' + Components.escapeHtml(entry.manifest_id) + '</td>' +
                    '<td>' + Components.escapeHtml(rowDate === '0000-00-00' ? 'Unknown' : rowDate) + '</td>' +
                    '<td>' + Components.escapeHtml(rowBranch) + '</td>' +
                    '<td style="color:' + srcColor + ';">' + Components.escapeHtml(rowSource) + '</td>' +
                    '<td style="text-align:center;">' +
                    '<input type="checkbox" class="version-check" data-group="' + groupId + '" data-depot="' + Components.escapeHtml(entry.depot_id) + '" data-manifest="' + Components.escapeHtml(entry.manifest_id) + '">' +
                    '</td>';
                tbody.appendChild(tr);
            });
        });

        tbody.onclick = function(e) {
            var hdr = e.target.closest('.version-group-header');
            if (!hdr || e.target.tagName === 'INPUT') return;
            var gid = hdr.dataset.group;
            var isCollapsed = hdr.dataset.collapsed === 'true';
            var rows = tbody.querySelectorAll('.version-depot-row[data-group="' + gid + '"]');
            var chevron = hdr.querySelector('.vg-chevron');
            rows.forEach(function(r) { r.style.display = isCollapsed ? '' : 'none'; });
            hdr.dataset.collapsed = isCollapsed ? 'false' : 'true';
            if (chevron) chevron.style.transform = isCollapsed ? 'rotate(90deg)' : '';
        };

        tbody.onchange = function(e) {
            if (e.target.classList.contains('version-group-check')) {
                var gid = e.target.dataset.group;
                tbody.querySelectorAll('.version-check[data-group="' + gid + '"]').forEach(function(cb) {
                    cb.checked = e.target.checked;
                    _uncheckSameDepotChoices(cb);
                });
            } else if (e.target.classList.contains('version-check')) {
                _uncheckSameDepotChoices(e.target);
            }
            var checked = tbody.querySelectorAll('.version-check:checked');
            if (dlBtn) dlBtn.disabled = checked.length === 0;
        };
    }

    function _stopVersionHistoryFetch() {
        _versionHistorySession += 1;
        if (_versionHistoryHandler) {
            Bridge.off('depot_history_results', _versionHistoryHandler);
            _versionHistoryHandler = null;
        }
        var loading = document.getElementById('version-loading');
        if (loading) loading.classList.add('hidden');
    }

    function _showVersionPicker(appId) {
        Components.showModal('version-modal');
        _stopVersionHistoryFetch();
        _versionImportedGroups = [];
        var loading = document.getElementById('version-loading');
        var table = document.getElementById('version-table');
        var manualBtn = document.getElementById('version-manual-download');
        var importBtn = document.getElementById('version-import-html');
        var manualInp = document.getElementById('version-manual-input');
        var dlBtn = document.getElementById('version-download');
        var session = _versionHistorySession;
        window._versionGroupsData = [];

        if (loading) loading.classList.remove('hidden');
        if (table) table.classList.add('hidden');
        if (dlBtn) { dlBtn.disabled = true; dlBtn.dataset.appid = appId; }
        if (manualBtn) manualBtn.dataset.appid = appId;
        if (importBtn) importBtn.dataset.appid = appId;
        if (manualInp) manualInp.value = '';
        var editDiv = document.getElementById('version-depot-edit');
        if (editDiv) editDiv.classList.add('hidden');

        var handler = function(json) {
            if (session !== _versionHistorySession) return;
            Bridge.off('depot_history_results', handler);
            _versionHistoryHandler = null;
            if (loading) loading.classList.add('hidden');
            if (table) table.classList.remove('hidden');

            try {
                var groups = JSON.parse(json);
                window._versionGroupsData = groups;
                _renderVersionGroups(groups, { expanded: false });
            } catch(e) {
                Components.showToast('error', 'Failed to load version history');
            }
        };
        _versionHistoryHandler = handler;
        Bridge.on('depot_history_results', handler);
        Bridge.call('fetch_depot_history', appId, false);
    }

    function _downloadSelectedVersion() {
        var dlBtn = document.getElementById('version-download');
        var appId = dlBtn ? dlBtn.dataset.appid : '';
        var tbody = document.getElementById('version-tbody');
        if (!tbody || !appId) return;

        var editDiv = document.getElementById('version-depot-edit');
        var editActive = editDiv && !editDiv.classList.contains('hidden');

        var manifest_override = {};
        if (editActive) {
            manifest_override = _getDepotEditOverrides();
        } else {
            tbody.querySelectorAll('.version-check:checked').forEach(function(cb) {
                manifest_override[cb.dataset.depot] = cb.dataset.manifest;
            });
        }
        if (!Object.keys(manifest_override).length) {
            Components.showToast('warning', 'Select at least one depot or use Manual IDs.');
            return;
        }
        _downloadVersionWithOverride(appId, manifest_override);
    }

    function _downloadManualVersion() {
        var btn = document.getElementById('version-manual-download');
        var appId = btn ? btn.dataset.appid : '';
        var inp = document.getElementById('version-manual-input');
        var raw = inp ? inp.value : '';
        if (!appId) return;
        var manifest_override = {};
        raw.split(/\r?\n/).forEach(function(line) {
            var clean = (line || '').trim();
            if (!clean || clean.charAt(0) === '#') return;
            var parts = clean.split(/[=,\s:]+/).filter(Boolean);
            if (parts.length < 2) return;
            var depot = parts[0].trim();
            var gid = parts[1].trim();
            if (/^\d+$/.test(depot) && /^\d+$/.test(gid)) {
                manifest_override[depot] = gid;
            }
        });
        if (!Object.keys(manifest_override).length) {
            Components.showToast('warning', 'Enter at least one line like 939851=2233225956230312354.');
            return;
        }
        _downloadVersionWithOverride(appId, manifest_override);
    }

    function _importVersionManifestHtml() {
        Bridge.callWithCallback('import_depot_manifest_html', function(json) {
            var result = {};
            try { result = JSON.parse(json || '{}'); } catch(e) {}
            if (result.cancelled) return;
            if (!result.ok) {
                Components.showToast('error', result.message || 'Could not import depot HTML');
                return;
            }
            var imported = result.entries || [];
            if (!imported.length || !result.line_text) {
                Components.showToast('warning', 'No depot manifest IDs found in that file');
                return;
            }
            _stopVersionHistoryFetch();
            var seen = {};
            var added = 0;
            _versionImportedGroups.forEach(function(group) {
                (group.entries || []).forEach(function(entry) {
                    if (entry && entry.depot_id && entry.manifest_id) {
                        seen[String(entry.depot_id) + ':' + String(entry.manifest_id)] = true;
                    }
                });
            });
            (result.groups || [{
                label: 'Imported HTML',
                date: 'Imported',
                branch: 'manual',
                source: 'Imported HTML',
                entries: imported
            }]).forEach(function(group) {
                var filtered = [];
                (group.entries || []).forEach(function(entry) {
                    var depot = entry && entry.depot_id ? String(entry.depot_id) : '';
                    var manifest = entry && entry.manifest_id ? String(entry.manifest_id) : '';
                    var seenKey = depot + ':' + manifest;
                    if (!depot || !manifest || seen[seenKey]) return;
                    seen[seenKey] = true;
                    filtered.push(entry);
                });
                if (filtered.length) {
                    added += filtered.length;
                    _versionImportedGroups.push({
                        label: group.label || 'Imported HTML',
                        date: group.date || 'Imported',
                        branch: group.branch || 'manual',
                        source: group.source || 'Imported HTML',
                        entries: filtered
                    });
                }
            });
            if (!added) {
                Components.showToast('warning', 'Those depot IDs are already listed.');
                return;
            }
            _renderVersionGroups(_versionImportedGroups, { expanded: true });
            Components.showToast('success', result.message || 'Imported depot manifest IDs');
        });
    }

    function _initDepotEdit() {
        var editBtn = document.getElementById('version-edit-toggle');
        var doneBtn = document.getElementById('version-edit-done');
        var editDiv = document.getElementById('version-depot-edit');
        var addDepot = document.getElementById('version-edit-add-depot');
        var addManifest = document.getElementById('version-edit-add-manifest');
        var addBtn = document.getElementById('version-edit-add-btn');
        var tbody = document.getElementById('version-edit-tbody');
        if (!editBtn || !editDiv) return;

        editBtn.addEventListener('click', function() {
            var groupsData = window._versionGroupsData || [];
            _populateDepotEditTable(groupsData);
            editDiv.classList.toggle('hidden');
            editBtn.textContent = editDiv.classList.contains('hidden') ? 'Edit Depots' : 'Editing...';
        });

        if (doneBtn) {
            doneBtn.addEventListener('click', function() {
                editDiv.classList.add('hidden');
                if (editBtn) editBtn.textContent = 'Edit Depots';
            });
        }

        if (addBtn && addDepot && addManifest) {
            addBtn.addEventListener('click', function() {
                var depot = addDepot.value.trim();
                var manifest = addManifest.value.trim();
                if (!depot || !manifest) return;
                _addDepotEditRow(tbody, depot, manifest);
                addDepot.value = '';
                addManifest.value = '';
            });
        }
    }

    function _populateDepotEditTable(groups) {
        var tbody = document.getElementById('version-edit-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        var seen = {};
        (groups || []).forEach(function(group) {
            (group.entries || []).forEach(function(entry) {
                var depot = entry && entry.depot_id ? String(entry.depot_id) : '';
                var manifest = entry && entry.manifest_id ? String(entry.manifest_id) : '';
                if (!depot || seen[depot]) return;
                seen[depot] = true;
                _addDepotEditRow(tbody, depot, manifest);
            });
        });
    }

    function _addDepotEditRow(tbody, depotId, manifestId) {
        var tr = document.createElement('tr');
        var depotTd = document.createElement('td');
        depotTd.style.cssText = 'font-family:monospace;font-size:0.85em;padding:4px;';
        depotTd.textContent = depotId;
        var manifestTd = document.createElement('td');
        var inp = document.createElement('input');
        inp.type = 'text';
        inp.value = manifestId || '';
        inp.style.cssText = 'width:100%;box-sizing:border-box;font-family:monospace;font-size:12px;padding:4px;border:1px solid var(--border,rgba(255,255,255,0.15));border-radius:3px;background:var(--input-bg,rgba(0,0,0,0.2));color:var(--fg,#e8e8e8);';
        manifestTd.appendChild(inp);
        var removeTd = document.createElement('td');
        removeTd.style.cssText = 'text-align:center;padding:4px;';
        var rmBtn = document.createElement('button');
        rmBtn.textContent = '✕';
        rmBtn.style.cssText = 'background:none;border:none;color:#e81123;cursor:pointer;font-size:14px;padding:2px 6px;';
        rmBtn.addEventListener('click', function() { tr.remove(); });
        removeTd.appendChild(rmBtn);
        tr.appendChild(depotTd);
        tr.appendChild(manifestTd);
        tr.appendChild(removeTd);
        tbody.appendChild(tr);
    }

    function _getDepotEditOverrides() {
        var tbody = document.getElementById('version-edit-tbody');
        if (!tbody) return {};
        var overrides = {};
        tbody.querySelectorAll('tr').forEach(function(tr) {
            var cells = tr.querySelectorAll('td');
            if (cells.length < 2) return;
            var depot = cells[0].textContent.trim();
            var manifest = (cells[1].querySelector('input') || {}).value || '';
            if (depot && manifest) {
                overrides[depot] = manifest;
            }
        });
        return overrides;
    }

    function _downloadVersionWithOverride(appId, manifest_override) {
        Components.hideModal('version-modal');
        var method = window._olderVersionMethod || 'ddmod';
        var source = window._olderVersionSource || 'oureveryday';

        var doDownload = function() {
            if (method === 'steam_native') {
                Bridge.call('download_game_version_native', appId, JSON.stringify(manifest_override), source);
                Components.showToast('info', 'Setting up Steam Native download for App ' + appId + '...');
            } else {
                Bridge.call('download_game_version', appId, JSON.stringify(manifest_override), source);
                Components.showToast('info', 'Downloading specific version of App ' + appId + '...');
            }
        };

        if (method === 'steam_native') {
            doDownload();
            return;
        }

        Bridge.callSync('get_steam_libraries', function(json) {
            var libs;
            try { libs = JSON.parse(json || '[]'); } catch(e) { libs = []; }

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

    function _renderLetUpdatesList(games) {
        var listEl = document.getElementById('lu-game-list');
        var countEl = document.getElementById('lu-count');
        var toggleBtn = document.getElementById('lu-toggle-all');
        if (!listEl) return;
        if (!games || !games.length) {
            listEl.innerHTML = '<span style="opacity:0.5;font-size:13px;">No stplug-in Lua files with manifest pins found.</span>';
            if (countEl) countEl.textContent = '0 games';
            if (toggleBtn) toggleBtn.textContent = 'Select All';
            return;
        }

        var html = '';
        games.forEach(function(g) {
            var appId = Components.escapeHtml(String(g.app_id || ''));
            var name = Components.escapeHtml(String(g.name || ('App ' + appId)));
            var path = Components.escapeHtml(String(g.path || ''));
            var activePins = parseInt(g.active_pins || 0, 10);
            var commentedPins = parseInt(g.commented_pins || 0, 10);
            var checked = g.allow_update ? ' checked' : '';
            html += '<label style="display:flex;align-items:flex-start;gap:9px;padding:7px 2px;cursor:pointer;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.04);">'
                + '<input type="checkbox" data-appid="' + appId + '"' + checked + ' style="margin-top:3px;accent-color:var(--accent,#e94560);">'
                + '<span style="display:flex;flex-direction:column;gap:2px;min-width:0;">'
                + '<span>' + name + ' <span style="opacity:0.45;font-size:11px;">' + appId + '</span></span>'
                + '<span style="opacity:0.55;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                + 'Pinned: ' + activePins + ' | Auto-update lines: ' + commentedPins + ' | ' + path
                + '</span>'
                + '</span>'
                + '</label>';
        });
        listEl.innerHTML = html;
        if (countEl) countEl.textContent = games.length + ' game' + (games.length !== 1 ? 's' : '');
        if (toggleBtn) {
            var allChecked = games.every(function(g) { return !!g.allow_update; });
            toggleBtn.textContent = allChecked ? 'Deselect All' : 'Select All';
        }
    }

    function _renderLetUpdatesHelperStatus(helper) {
        _letUpdatesHelper = helper || {};
        var statusEl = document.getElementById('lu-helper-status');
        var addBtn = document.getElementById('let-updates-add-helper');
        var removeBtn = document.getElementById('let-updates-remove-helper');
        var exists = !!(_letUpdatesHelper && _letUpdatesHelper.exists);
        if (statusEl) {
            var path = _letUpdatesHelper.path ? (' - ' + _letUpdatesHelper.path) : '';
            statusEl.textContent = exists ? ('Helper Lua: installed' + path) : 'Helper Lua: not installed';
        }
        if (addBtn) addBtn.disabled = exists;
        if (removeBtn) removeBtn.disabled = !exists;
    }

    function _setLetUpdatesHelper(enabled) {
        var action = enabled ? 'add' : 'remove';
        var filePath = (_letUpdatesHelper && _letUpdatesHelper.path) ? _letUpdatesHelper.path : 'Steam/config/stplug-in/00_LetUpdate_override.lua';
        var message = enabled
            ? 'Add 00_LetUpdate_override.lua?\n\nThis lets Steam show update prompts for pinned manifest games.\n\n' + filePath
            : 'Remove 00_LetUpdate_override.lua?\n\nThis disables the global helper Lua.\n\n' + filePath;
        if (!window.confirm(message)) return;

        Bridge.callWithCallback('let_updates_set_helper', !!enabled, function(json) {
            var result;
            try { result = JSON.parse(json || '{}'); } catch(e) { result = { ok: false, error: String(e) }; }
            if (!result.ok) {
                Components.showToast('error', result.error || ('Failed to ' + action + ' helper Lua.'));
                return;
            }
            _renderLetUpdatesHelperStatus(result.status || { exists: !!result.enabled });
            Components.showToast('success', enabled ? 'Helper Lua added.' : 'Helper Lua removed.');
        });
    }

    function _openLetUpdatesModal() {
        var listEl = document.getElementById('lu-game-list');
        var countEl = document.getElementById('lu-count');
        var toggleBtn = document.getElementById('lu-toggle-all');
        var statusEl = document.getElementById('lu-helper-status');
        if (listEl) listEl.innerHTML = '<span style="opacity:0.5;font-size:13px;">Loading stplug-in Lua files...</span>';
        if (countEl) countEl.textContent = 'Loading...';
        if (toggleBtn) toggleBtn.textContent = 'Deselect All';
        if (statusEl) statusEl.textContent = 'Helper status: checking...';
        Components.showModal('let-updates-modal');
        Bridge.callWithCallback('let_updates_list_games', function(json) {
            var data;
            try { data = JSON.parse(json || '{}'); } catch(e) { data = { ok: false, error: String(e) }; }
            if (!data.ok) {
                if (listEl) listEl.innerHTML = '<span style="opacity:0.65;font-size:13px;">' + Components.escapeHtml(data.error || 'Failed to scan stplug-in Lua files.') + '</span>';
                if (countEl) countEl.textContent = 'Scan failed';
                _renderLetUpdatesHelperStatus({});
                return;
            }
            _renderLetUpdatesHelperStatus(data.helper || {});
            _renderLetUpdatesList(data.games || []);
        });
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

        if (action === 'auto_lc_setup') {
            _initLcSetupModal();
            Bridge.callWithCallback('get_setting', 'steam_path', function(steamPath) {
                var pathInp = document.getElementById('lc-steam-path');
                if (pathInp && steamPath && !pathInp.value) pathInp.value = steamPath;
            });
            // Always re-probe on open. The initial probe inside _initLcSetupModal
            // only fires once, so users who installed LumaCore later in the
            // session would otherwise see a stale "—". Force the refresh here
            // so the modal always shows the current installed/latest pair.
            _refreshLcVersionInfo();
            _refreshLcSteamUpdateWarning();
            Components.showModal('lc-setup-modal');
            return;
        }
        if (action === 'linux_setup') {
            Components.showToast('info', 'Running Linux setup...');
            Bridge.call('linux_setup_now');
            return;
        }

        if (action === 'fix_slssteam_hash') {
            Components.showToast('info', 'Fixing SLSsteam hash issue...');
            Bridge.call('fix_slssteam_hash');
            return;
        }

        if (action === 'lc_online_fix') {
            _initLcOnlineFixModal();
            var appId = _getSelectedGameId();
            var appIdInp = document.getElementById('lc-onlinefix-appid');
            if (appIdInp && appId) appIdInp.value = appId;
            Components.showModal('lc-online-fix-modal');
            return;
        }

        // Steam updates block/unblock — writes BootStrapperInhibitAll to
        // <steam>\steam.cfg. The toggle is handled by the bridge so the user
        // sees a confirmation toast with the current state after the write.
        if (action === 'steam_updates') {
            Bridge.callSync('steam_updates_get_state', function(state) {
                var current = (state || 'unknown').toString();
                var msg;
                if (current === 'blocked') {
                    msg = 'Steam auto-updates are currently BLOCKED via steam.cfg.\n\n' +
                          'Click OK to UNBLOCK them (sets BootStrapperInhibitAll=False).';
                } else if (current === 'unblocked') {
                    msg = 'Steam auto-updates are currently allowed.\n\n' +
                          'Click OK to BLOCK them (sets BootStrapperInhibitAll=Enable).';
                } else {
                    msg = 'No steam.cfg setting detected.\n\n' +
                          'Click OK to BLOCK Steam auto-updates by writing ' +
                          'BootStrapperInhibitAll=Enable to <steam>\\steam.cfg.';
                }
                if (!window.confirm(msg)) return;
                var nextAction = (current === 'blocked') ? 'unblock' : 'block';
                Bridge.callWithCallback('steam_updates_set_state', nextAction, function(res) {
                    var result = (res || '').toString();
                    if (result === 'blocked') {
                        Components.showToast('success', 'Steam updates BLOCKED. Restart Steam for it to take effect.');
                    } else if (result === 'unblocked') {
                        Components.showToast('success', 'Steam updates UNBLOCKED. Restart Steam for it to take effect.');
                    } else {
                        Components.showToast('error', 'Failed to update steam.cfg: ' + result);
                    }
                });
            });
            return;
        }

        if (action === 'let_updates') {
            _openLetUpdatesModal();
            return;
        }

        if (action === 'provider_preview') {
            _showHomeProviderPreview();
            return;
        }

        if (action === 'provider_submit') {
            _setHomeProviderStatus('Submitting clean provider keys...');
            Bridge.call('provider_contribute_submit', 'manual');
            return;
        }

        if (action === 'provider_update') {
            _setHomeProviderStatus('Updating provider cache...');
            Bridge.call('provider_update_now');
            return;
        }

        if (action === 'download_games') {
            var homeAppId = _getSelectedGameId() || '';
            Bridge.callSync('get_platform', function(platform) {
                var chooseSteamBtn = document.getElementById('ddmod-choose-steam');
                var chooseDdmodBtn = document.getElementById('ddmod-choose-ddmod');
                if (platform === 'linux') {
                    if (chooseSteamBtn) chooseSteamBtn.style.display = 'none';
                    if (chooseDdmodBtn) chooseDdmodBtn.dataset.appid = homeAppId;
                } else {
                    if (chooseSteamBtn) {
                        chooseSteamBtn.style.display = '';
                        chooseSteamBtn.dataset.appid = homeAppId;
                    }
                    if (chooseDdmodBtn) chooseDdmodBtn.dataset.appid = homeAppId;
                }
            });
            Components.showModal('ddmod-choose-modal');
            return;
        }

        // Non-game actions don't need a game selected
        var nonGameActions = [
            'download_games', 'download_manifests', 'recent_lua', 'update_manifests',
            'mute_toggle', 'remove_game', 'context_menu', 'applist_menu',
            'check_updates', 'scan_library', 'analytics', 'auto_lc_setup', 'lc_online_fix',
            'steam_updates', 'let_updates', 'fix_slssteam_hash'
        ];
        // Outside-Steam game action
        if (_outsideMode && nonGameActions.indexOf(action) === -1) {
            var gamePath     = (document.getElementById('outside-path-display') || {}).value || '';
            var outsideName  = _getOutsideGameName(gamePath);
            var outsideAppId = (document.getElementById('outside-appid') || {}).value || '0';
            if (!gamePath) {
                Components.showToast('warning', 'Please select a game folder first.');
                return;
            }
            if (!outsideName) {
                Components.showToast('warning', 'Please enter the game name first.');
                return;
            }
            // Same achievement-breakage gate as the Steam-game path.
            var outsideBreaking = ['crack', 'steamstub_crack', 'steam_auto'];
            if (outsideBreaking.indexOf(action) !== -1) {
                Bridge.callWithCallback('get_setting', 'warn_before_breaking_achievements', function(val) {
                    var skipWarn = (val === 'False' || val === 'false' || val === '0');
                    if (skipWarn) {
                        Bridge.call('run_game_action_outside', gamePath, outsideName, outsideAppId || '0', action);
                        return;
                    }
                    var msg = 'Heads up — this will break Steam achievements.\n\n'
                        + 'Replacing the Steam API with an emulator means achievements you earn after this will only save locally. Cloud saves will also stop syncing.\n\n'
                        + 'Prefer "Remove SteamStub DRM (Steamless)" if the game uses Steam DRM — it keeps achievements working.\n\n'
                        + 'Continue anyway?';
                    if (window.confirm(msg)) {
                        Bridge.call('run_game_action_outside', gamePath, outsideName, outsideAppId || '0', action);
                    }
                });
                return;
            }
            Bridge.call('run_game_action_outside', gamePath, outsideName, outsideAppId || '0', action);
            return;
        }

        // Steam game action
        var appId = _getSelectedGameId();
        if (nonGameActions.indexOf(action) === -1 && !appId) {
            Components.showToast('warning', 'Please select a game from the dropdown first.');
            return;
        }

        // DLC check has its own structured slot that emits a payload
        // the modal handler renders. Skip the generic run_game_action
        // path which fires-and-forgets to a stdout no one reads.
        if (action === 'dlc_check') {
            DlcCheck.show(appId);
            return;
        }

        if (action === 'multiplayer') {
            var mpMsg = 'Multiplayer Fix uses version-specific online fix files.\n\n'
                + 'Check the game support page first and make sure your game version matches the fix. Some games use Epic or Microsoft services and need a different fix than the normal Steam path.\n\n'
                + 'Continue?';
            if (!window.confirm(mpMsg)) return;
            Bridge.call('run_game_action', appId || '', action);
            return;
        }

        // Achievement-breaking actions: warn before dispatch unless the user
        // has explicitly opted out via the setting. Default is to warn so a
        // never-set value still triggers the dialog.
        var achievementBreaking = ['crack', 'steamstub_crack', 'steam_auto'];
        if (achievementBreaking.indexOf(action) !== -1) {
            if (action === 'crack') {
                // Show emulator platform picker
                var platformChoice = window.confirm(
                    'Select emulator platform:\n\n' +
                    'Click OK for Windows (gbe_fork — steam_api.dll / .exe games)\n' +
                    'Click Cancel for Linux (gbe_fork_linux — libsteam_api.so / native games)'
                );
                var linuxNative = !platformChoice;
                Bridge.call('fix_game', JSON.stringify({
                    app_id: String(appId || ''),
                    game_path: '',
                    emu_mode: 'regular',
                    linux_native: linuxNative
                }));
                return;
            }
            Bridge.callWithCallback('get_setting', 'warn_before_breaking_achievements', function(val) {
                // Setting stores the *opt-out* state. Treat unset / non-False as "warn".
                var skipWarn = (val === 'False' || val === 'false' || val === '0');
                if (skipWarn) {
                    Bridge.call('run_game_action', appId || '', action);
                    return;
                }
                var msg = (action === 'crack' || action === 'steam_auto')
                    ? 'Heads up — this will break Steam achievements.\n\n'
                      + 'Replacing the Steam API with an emulator means achievements you earn after this will only save locally and will not appear on your Steam profile. Cloud saves will also stop syncing.\n\n'
                      + 'For Steam-DRM games (Teardown, Doom Eternal, etc.) prefer "Remove SteamStub DRM (Steamless)" instead — it strips the DRM wrapper without touching the Steam API, so achievements keep working.\n\n'
                      + 'Continue anyway?'
                    : 'This action may break Steam achievements. Continue?';
                if (window.confirm(msg)) {
                    Bridge.call('run_game_action', appId || '', action);
                }
            });
            return;
        }

        Bridge.call('run_game_action', appId || '', action);
    }

    function _initHomeProviderControls() {
        var box = document.getElementById('home-provider-contribute');
        var enrichBox = document.getElementById('home-provider-enrich');
        if (box) {
            Bridge.callWithCallback('get_setting', 'provider_contribute_keys', function(val) {
                box.checked = (val === 'True' || val === 'true' || val === '1');
            });
            box.addEventListener('change', function() {
                Bridge.call('set_setting', 'provider_contribute_keys', box.checked ? 'True' : 'False');
                _setHomeProviderStatus(box.checked ? 'Auto contribution enabled.' : 'Auto contribution disabled.');
            });
        }
        if (enrichBox) {
            Bridge.callWithCallback('get_setting', 'provider_enrich_steam_metadata', function(val) {
                enrichBox.checked = (val === 'True' || val === 'true' || val === '1');
            });
            enrichBox.addEventListener('change', function() {
                Bridge.call('set_setting', 'provider_enrich_steam_metadata', enrichBox.checked ? 'True' : 'False');
                _setHomeProviderStatus(enrichBox.checked ? 'Steam metadata enrichment enabled. Submit may take longer.' : 'Steam metadata enrichment disabled.');
            });
        }
    }

    function _setHomeProviderStatus(msg) {
        var status = document.getElementById('home-provider-status');
        if (status) status.textContent = msg || '';
    }

    function _showHomeProviderPreview() {
        Bridge.callSync('provider_contribute_preview', function(json) {
            var data = {};
            try { data = JSON.parse(json || '{}'); } catch(e) {}
            _setHomeProviderStatus(
                'Found ' + (data.valid || 0) + ' valid keys to submit. ' +
                'Invalid skipped: ' + (data.invalid || 0) + '. ' +
                'Duplicate skipped: ' + (data.duplicates || 0) + '. ' +
                'Already submitted skipped: ' + (data.already_submitted || 0) + '.'
            );
        });
    }

    function _updateHomeProviderStatus(data) {
        if (!data || !data.task) return;
        if (data.task === 'provider_contribute') {
            var msg = data.already_submitted ? 'Already submitted' : (data.message || 'Submitted');
            var enrich = data.steam_metadata_enrichment || {};
            var enrichText = enrich.enabled ? (' Steam metadata filled ' + (enrich.items_enriched || 0) + ' item(s).') : '';
            _setHomeProviderStatus(
                msg + '. Found ' + (data.valid || 0) + ' valid, skipped ' +
                (data.invalid || 0) + ' invalid, ' + (data.duplicates || 0) +
                ' duplicates, and ' + (data.already_submitted_count || 0) +
                ' already submitted.' + enrichText
            );
        } else if (data.task === 'provider_update') {
            _setHomeProviderStatus(data.message || '');
        }
    }

    var _lcSetupInitialized = false;
    function _initLcSetupModal() {
        if (_lcSetupInitialized) return;
        _lcSetupInitialized = true;

        Bridge.on('lc_progress', function(msg) {
            var statusEl = document.getElementById('lc-setup-status');
            if (statusEl) statusEl.textContent = msg;
        });

        var runBtn = document.getElementById('lc-install-run');
        if (runBtn) {
            runBtn.addEventListener('click', function() {
                var steamPath = (document.getElementById('lc-steam-path') || {}).value || '';
                var variant = 'release';
                var picked = document.querySelector('input[name="lc-variant"]:checked');
                if (picked && picked.value) variant = picked.value;
                var statusEl = document.getElementById('lc-setup-status');
                if (statusEl) statusEl.textContent = 'Installing LumaCore (' + variant + ')...';
                runBtn.disabled = true;
                Bridge.call('install_lumacore', steamPath, variant);
            });
        }

        var deactivateBtn = document.getElementById('lc-deactivate-run');
        if (deactivateBtn) {
            deactivateBtn.addEventListener('click', function() {
                var ok = window.confirm(
                    'Deactivate LumaCore?\n\n' +
                    'Steam will be closed first. SteaMidra will then remove ' +
                    'LumaCore.dll, dwmapi.dll, and bin/lcoverlay.dll. ' +
                    'Make sure no Steam process is open before continuing.'
                );
                if (!ok) return;
                var statusEl = document.getElementById('lc-setup-status');
                if (statusEl) statusEl.textContent = 'Deactivating LumaCore...';
                deactivateBtn.disabled = true;
                Bridge.call('lumacore_deactivate');
            });
        }

        var refreshBtn = document.getElementById('lc-version-refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function() {
                _refreshLcVersionInfo(true);
            });
        }

        var blockUpdatesBtn = document.getElementById('lc-block-steam-updates');
        if (blockUpdatesBtn) {
            blockUpdatesBtn.addEventListener('click', function() {
                blockUpdatesBtn.disabled = true;
                Bridge.callWithCallback('steam_updates_set_state', 'block', function(res) {
                    blockUpdatesBtn.disabled = false;
                    var result = (res || '').toString();
                    if (result === 'blocked') {
                        Components.showToast('success', 'Steam updates BLOCKED. Restart Steam for it to take effect.');
                        _refreshLcSteamUpdateWarning();
                    } else {
                        Components.showToast('error', 'Failed to update steam.cfg: ' + result);
                    }
                });
            });
        }

        // Browse button: lets the user pin the Steam folder when auto-detect
        // landed on the wrong install (multiple Steams on disk, registry
        // pointing somewhere stale, etc). Persists the choice through the
        // same `steam_path` setting the rest of the app reads.
        var browseBtn = document.getElementById('lc-steam-path-browse');
        if (browseBtn) {
            browseBtn.addEventListener('click', function() {
                Bridge.callWithCallback('browse_steam_path', '', function(picked) {
                    if (!picked) return;
                    var pathInp = document.getElementById('lc-steam-path');
                    if (pathInp) pathInp.value = picked;
                    Bridge.call('set_setting', 'steam_path', picked);
                    var statusEl = document.getElementById('lc-setup-status');
                    if (statusEl) statusEl.textContent = 'Steam path saved.';
                    _refreshLcVersionInfo(true);
                });
            });
        }

        // Initial version probe — uses the cached answer when available so
        // there's no redundant network round-trip when the modal opens.
        _refreshLcVersionInfo();
        _refreshLcSteamUpdateWarning();
    }

    function _refreshLcSteamUpdateWarning() {
        var warning = document.getElementById('lc-steam-updates-warning');
        if (!warning) return;
        Bridge.callSync('steam_updates_get_state', function(state) {
            warning.style.display = ((state || '').toString() === 'blocked') ? 'none' : 'flex';
        });
    }

    function _refreshHomeLumacoreNotice(force) {
        var alertEl = document.getElementById('home-lumacore-alert');
        if (!alertEl) return;
        if (!_platformReady || _platform !== 'win32') {
            alertEl.classList.add('hidden');
            return;
        }
        if (_lcHomeNoticeBusy) return;
        _lcHomeNoticeBusy = true;
        Bridge.callWithCallback('lumacore_check_update', force ? 'force' : '', function(json) {
            _lcHomeNoticeBusy = false;
            var data;
            try { data = JSON.parse(json); } catch (e) { data = null; }
            if (!data) {
                alertEl.classList.add('hidden');
                return;
            }

            var titleEl = document.getElementById('home-lumacore-alert-title');
            var bodyEl = document.getElementById('home-lumacore-alert-body');
            var actionEl = document.getElementById('home-lumacore-alert-action');
            var installed = (data.installed || '').toString();
            var latest = (data.latest || '').toString();

            if (!installed) {
                if (titleEl) titleEl.textContent = 'LumaCore Installation Required';
                if (bodyEl) bodyEl.textContent = 'Install LumaCore so Steam can see games added through SteaMidra.';
                if (actionEl) actionEl.textContent = 'Auto LC Setup';
                alertEl.classList.remove('hidden');
                return;
            }

            if (data.update_available) {
                if (titleEl) titleEl.textContent = 'LumaCore Update Available!';
                if (bodyEl) {
                    bodyEl.textContent = 'Installed ' + installed + ', latest ' + (latest || 'unknown') + '. Update it before adding more games.';
                }
                if (actionEl) actionEl.textContent = 'Update LumaCore';
                alertEl.classList.remove('hidden');
                return;
            }

            alertEl.classList.add('hidden');
        });
    }

    function _refreshLcVersionInfo(force) {
        var installedEl = document.getElementById('lc-version-installed');
        var latestEl    = document.getElementById('lc-version-latest');
        var bannerEl    = document.getElementById('lc-version-update-banner');
        if (installedEl) installedEl.textContent = 'checking...';
        if (latestEl)    latestEl.textContent    = 'checking...';

        // The slot accepts a string flag. "force" bypasses the 6-hour cache
        // for explicit user-initiated checks; empty string follows the
        // cached path for automatic refreshes.
        var arg = force ? 'force' : '';
        Bridge.callWithCallback('lumacore_check_update', arg, function(json) {
            var data;
            try { data = JSON.parse(json); } catch (e) { data = null; }
            if (!data) {
                if (installedEl) installedEl.textContent = '—';
                if (latestEl)    latestEl.textContent    = '—';
                return;
            }
            if (installedEl) installedEl.textContent = data.installed || 'not installed';
            if (latestEl)    latestEl.textContent    = data.latest    || 'unknown';
            if (bannerEl)    bannerEl.style.display  = data.update_available ? 'flex' : 'none';
            if (data.error) {
                Components.showToast('error', 'Update check failed: ' + data.error);
            }
        });
    }

    var _lcOnlineFixInitialized = false;
    function _initLcOnlineFixModal() {
        if (_lcOnlineFixInitialized) return;
        _lcOnlineFixInitialized = true;

        var checkBtn = document.getElementById('lc-onlinefix-check');
        if (checkBtn) {
            checkBtn.addEventListener('click', function() {
                var appId = (document.getElementById('lc-onlinefix-appid') || {}).value || '';
                if (!appId) { Components.showToast('warning', 'Enter an App ID first.'); return; }
                Bridge.callWithCallback('get_launch_option_status', appId, function(status) {
                    var ofStatus = document.getElementById('lc-onlinefix-status');
                    if (ofStatus) ofStatus.textContent = status || 'Unknown';
                });
            });
        }

        var toggleBtn = document.getElementById('lc-onlinefix-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function() {
                var appId = (document.getElementById('lc-onlinefix-appid') || {}).value || '';
                if (!appId) { Components.showToast('warning', 'Enter an App ID first.'); return; }
                Bridge.call('toggle_online_fix', appId);
                Components.showToast('info', 'Toggling LC Online Fix for App ' + appId + '...');
            });
        }
    }

    function getPlatform() {
        return _platform;
    }

    return {
        init: init,
        navigateTo: navigateTo,
        getPlatform: getPlatform,
        applyCustomAppearance: applyCustomAppearance,
        clearCustomAppearance: clearCustomAppearance
    };
})();

// Boot the app when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    App.init();
});
