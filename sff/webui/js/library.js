/**
 * SteaMidra — Library Page
 * Shows installed/downloaded games from AppList + Steam libraries.
 */

window.Library = (function() {
    'use strict';

    var _initialized = false;
    var _pendingDelete = null; // { appId, gamePath }
    var _libraryGames = [];
    var _managedOnly = false;
    var _renderToken = 0;
    var _renderChunkSize = 48;

    function init() {
        if (_initialized) return;
        _initialized = true;

        var refreshBtn = document.getElementById('library-refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function() { _refreshLibrary(true); });
        }

        var searchInp = document.getElementById('library-search');
        if (searchInp) {
            searchInp.addEventListener('input', function() {
                _applyLibraryFilter(this.value.trim().toLowerCase());
            });
        }

        var managedBtn = document.getElementById('library-filter-managed');
        if (managedBtn) {
            managedBtn.addEventListener('click', function() {
                _managedOnly = !_managedOnly;
                managedBtn.classList.toggle('active', _managedOnly);
                _applyLibraryFilter(searchInp ? searchInp.value.trim().toLowerCase() : '');
            });
        }

        var driveSelect = document.getElementById('library-drive-select');
        if (driveSelect) {
            driveSelect.addEventListener('change', function() {
                _updateDiskInfo(this.value);
            });
        }
        // library-drive-select CustomSelect is initialized globally in app.js

        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'library_loaded' && Array.isArray(data.games)) {
                    _renderLibrary(data.games);
                }
                if (data.task === 'delete_game') {
                    if (data.success) {
                        var removedId = data.app_id || (window._lastDeletedAppId || '');
                        var card = removedId
                            ? document.querySelector('[data-appid="' + removedId + '"].game-card')
                            : null;
                        if (card) {
                            card.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
                            card.style.opacity = '0';
                            card.style.transform = 'scale(0.92)';
                            setTimeout(function() { _refreshLibrary(); }, 200);
                        } else {
                            _refreshLibrary();
                        }
                    }
                }
                if (data.task === 'update_check') {
                    _onUpdateCheckResult(data);
                }
                if (data.task === 'lure_fix') {
                    _onLureFixResult(data);
                }
            } catch(e) {}
        });

        var grid = document.getElementById('library-grid');
        if (grid) {
            grid.addEventListener('click', function(e) {
                var btn = e.target.closest('[data-action]');
                if (btn) {
                    var action = btn.dataset.action;
                    var appId = btn.dataset.appid;
                    if (action === 'play') {
                        Bridge.call('launch_game', appId);
                    } else if (action === 'fix') {
                        FixGame.preSelect(appId);
                        App.navigateTo('fixgame');
                    } else if (action === 'delete') {
                        window._lastDeletedAppId = appId;
                        _pendingDelete = {
                            appId: appId,
                            gamePath: btn.dataset.gamepath || ''
                        };
                        var nameEl = document.getElementById('library-delete-game-name');
                        if (nameEl) nameEl.textContent = btn.dataset.gamename || ('App ' + appId);
                        Components.showModal('library-delete-modal');
                    } else if (action === 'check_update') {
                        btn.disabled = true;
                        btn.textContent = 'Checking...';
                        btn.dataset.checking = appId;
                        Bridge.call('check_game_update', appId);
                    } else if (action === 'lure_fix') {
                        btn.disabled = true;
                        btn.textContent = 'Patching...';
                        btn.dataset.lurefixing = appId;
                        Bridge.call('lure_fix_acf', appId);
                    } else if (action === 'dlc_check') {
                        DlcCheck.show(appId);
                    } else {
                        Bridge.call('run_game_action', appId, action);
                    }
                }
            });
        }

        // Delete modal buttons
        var btnApplist = document.getElementById('library-delete-applist');
        if (btnApplist) {
            btnApplist.addEventListener('click', function() {
                if (_pendingDelete) {
                    Bridge.call('delete_game', _pendingDelete.appId, _pendingDelete.gamePath, 'applist');
                    _pendingDelete = null;
                    Components.hideModal('library-delete-modal');
                }
            });
        }

        var btnFull = document.getElementById('library-delete-full');
        if (btnFull) {
            btnFull.addEventListener('click', function() {
                if (_pendingDelete) {
                    Bridge.call('delete_game', _pendingDelete.appId, _pendingDelete.gamePath, 'full');
                    _pendingDelete = null;
                    Components.hideModal('library-delete-modal');
                }
            });
        }

        ['library-delete-cancel', 'library-delete-cancel-footer'].forEach(function(id) {
            var btn = document.getElementById(id);
            if (btn) {
                btn.addEventListener('click', function() {
                    _pendingDelete = null;
                });
            }
        });
    }

    function onPageEnter() {
        init();
        _refreshLibrary(false);
        _refreshDiskInfo();
    }

    function _refreshDiskInfo() {
        Bridge.callSync('get_steam_libraries', function(json) {
            var paths = [];
            try { paths = JSON.parse(json || '[]'); } catch(e) {}
            var seen = {};
            var drives = [];
            paths.forEach(function(p) {
                if (!p) return;
                var root = (p.length >= 3 && p[1] === ':') ? p.slice(0, 3) : '/';
                var label = (p.length >= 3 && p[1] === ':') ? p[0].toUpperCase() + ':' : 'System';
                if (!seen[root]) {
                    seen[root] = true;
                    drives.push({ root: root, label: label });
                }
            });
            if (!drives.length) {
                Bridge.callWithCallback('get_setting', 'steam_path', function(steamPath) {
                    if (!steamPath) return;
                    var root = (steamPath.length >= 3 && steamPath[1] === ':') ? steamPath.slice(0, 3) : '/';
                    var label = (steamPath.length >= 3 && steamPath[1] === ':') ? steamPath[0].toUpperCase() + ':' : 'System';
                    _populateDriveSelect([{ root: root, label: label }]);
                    _updateDiskInfo(root);
                });
                return;
            }
            _populateDriveSelect(drives);
            _updateDiskInfo(drives[0].root);
        });
    }

    function _populateDriveSelect(drives) {
        var sel = document.getElementById('library-drive-select');
        if (!sel) return;
        sel.innerHTML = '';
        drives.forEach(function(d) {
            var opt = document.createElement('option');
            opt.value = d.root;
            opt.textContent = d.label;
            sel.appendChild(opt);
        });
        var ui = document.getElementById('library-drive-select-ui');
        if (ui) {
            if (drives.length > 1) {
                ui.classList.remove('hidden');
            } else {
                ui.classList.add('hidden');
            }
        }
    }

    function _updateDiskInfo(drivePath) {
        Bridge.callWithCallback('get_disk_usage', drivePath, function(json) {
            var el = document.getElementById('library-disk-info');
            if (!el) return;
            try {
                var d = JSON.parse(json || '{}');
                if (d.error || !d.total) { el.textContent = ''; return; }
                el.textContent = _fmtBytes(d.free) + ' free of ' + _fmtBytes(d.total);
            } catch(e) {}
        });
    }

    function _fmtBytes(b) {
        if (b >= 1e12) return (b / 1e12).toFixed(1) + ' TB';
        if (b >= 1e9) return (b / 1e9).toFixed(1) + ' GB';
        if (b >= 1e6) return (b / 1e6).toFixed(1) + ' MB';
        return (b / 1e3).toFixed(0) + ' KB';
    }

    function _refreshLibrary(force) {
        Bridge.call(force ? 'refresh_library' : 'load_library');
    }

    function _renderLibrary(games) {
        _libraryGames = games || [];
        var searchInp = document.getElementById('library-search');
        var filter = searchInp ? searchInp.value.trim().toLowerCase() : '';
        _applyLibraryFilter(filter);
    }

    function _applyLibraryFilter(filter) {
        var games = _libraryGames;
        var grid = document.getElementById('library-grid');
        var empty = document.getElementById('library-empty');
        if (!grid) return;
        if (filter) {
            games = games.filter(function(g) {
                return (g.name || '').toLowerCase().indexOf(filter) !== -1;
            });
        }
        if (_managedOnly) {
            games = games.filter(function(g) { return !!g.steamidra_managed; });
        }

        if (grid) grid.innerHTML = '';
        _renderToken++;

        if (games.length === 0) {
            if (grid) grid.classList.add('hidden');
            if (empty) empty.classList.remove('hidden');
            return;
        }

        if (grid) grid.classList.remove('hidden');
        if (empty) empty.classList.add('hidden');

        _renderLibraryBatch(games, 0, _renderToken);
    }

    function _renderLibraryBatch(games, start, token) {
        var grid = document.getElementById('library-grid');
        if (!grid || token !== _renderToken) return;
        var end = Math.min(start + _renderChunkSize, games.length);
        var frag = document.createDocumentFragment();
        for (var i = start; i < end; i++) {
            frag.appendChild(_createLibraryCard(games[i], i));
        }
        grid.appendChild(frag);
        if (end < games.length) {
            setTimeout(function() {
                _renderLibraryBatch(games, end, token);
            }, 16);
        }
    }

    function _createLibraryCard(game, index) {
        game.installed = true;
        var card = Components.createGameCard(game, { index: index, forceShowImage: true });
        var safeName = (game.name || '').replace(/"/g, '&quot;');
        var safePath = (game.path || '').replace(/"/g, '&quot;');
        var actions = card.querySelector('.game-card-actions');
        if (actions) {
            actions.innerHTML =
                '<button class="btn btn-sm btn-primary" data-action="play" data-appid="' + game.app_id + '" data-tooltip="Launch through Steam">Play</button>' +
                '<button class="btn btn-sm" data-action="fix" data-appid="' + game.app_id + '" data-tooltip="Fix this game">Fix</button>' +
                '<button class="btn btn-sm" data-action="dlc_check" data-appid="' + game.app_id + '" data-tooltip="Check DLCs">DLC</button>' +
                '<button class="btn btn-sm" data-action="workshop" data-appid="' + game.app_id + '" data-tooltip="Open Workshop">Workshop</button>' +
                '<button class="btn btn-sm" data-action="lure_fix" data-appid="' + game.app_id + '" data-tooltip="Patch ACF to match Steam CM latest, no download">Lure Fix</button>' +
                '<button class="btn btn-sm" data-action="check_update" data-appid="' + game.app_id + '" data-tooltip="Download latest manifests and patch ACF">Update</button>' +
                '<button class="btn btn-sm btn-danger" data-action="delete" data-appid="' + game.app_id + '" data-gamepath="' + safePath + '" data-gamename="' + safeName + '" data-tooltip="Remove this game">\u2715</button>';
        }
        if (game.steamidra_managed) {
            var badge = document.createElement('div');
            badge.className = 'steamidra-managed-badge';
            badge.textContent = 'SM';
            badge.title = 'Added with SteaMidra';
            card.appendChild(badge);
        }
        _attachUpdateBadge(card, game.app_id);
        return card;
    }

    function onPageLeave() {
        _renderToken++;
        var grid = document.getElementById('library-grid');
        if (!grid) return;
        grid.querySelectorAll('img').forEach(function(img) {
            img.onload = null;
            img.onerror = null;
            img.removeAttribute('src');
        });
        grid.innerHTML = '';
    }

    // 6.2.5: update-available badge + popover.
    // Reads cached state through the bridge, paints a green dot when
    // up-to-date and within the freshness window, an amber dot when an
    // update is available, and nothing otherwise. Click opens a tiny
    // popover with installed buildid, CM-published buildid, and Check
    // now. The interval is read live so toggling the setting flips the
    // freshness gate without a reload.
    function _attachUpdateBadge(card, appId) {
        if (!card || !appId) return;
        var dot = document.createElement('div');
        dot.className = 'update-badge update-badge-hidden';
        dot.dataset.appid = appId;
        dot.title = 'Update status';
        card.appendChild(dot);
        dot.addEventListener('click', function(ev) {
            ev.stopPropagation();
            _openUpdatePopover(dot, appId);
        });
        _refreshUpdateBadge(dot, appId);
    }

    function _refreshUpdateBadge(dot, appId) {
        Bridge.callWithCallback('get_game_update_state', String(appId), function(json) {
            var state = {};
            try { state = JSON.parse(json || '{}') || {}; } catch(e) {}
            Bridge.callWithCallback('get_setting', 'update_check_interval_min', function(rawInterval) {
                var intervalMin = parseInt(rawInterval || '60', 10);
                if (!intervalMin || intervalMin <= 0) intervalMin = 60;
                _paintUpdateBadge(dot, state, intervalMin);
            });
        });
    }

    function _paintUpdateBadge(dot, state, intervalMin) {
        if (!dot) return;
        dot.classList.remove('update-badge-green', 'update-badge-amber', 'update-badge-hidden');
        var now = Math.floor(Date.now() / 1000);
        var fresh = state && state.checked_at && (now - state.checked_at) < (intervalMin * 60);
        var enabled = state && state.enabled !== false;
        var hasError = state && (state.error || state.up_to_date === null);
        if (!enabled || hasError || !state) {
            dot.classList.add('update-badge-hidden');
            return;
        }
        if (state.up_to_date === true && fresh) {
            dot.classList.add('update-badge-green');
            dot.title = 'Up to date (build ' + (state.installed_buildid || '') + ')';
        } else if (state.up_to_date === false) {
            dot.classList.add('update-badge-amber');
            dot.title = 'Update available — installed ' +
                (state.installed_buildid || '?') + ', Steam ' +
                (state.cm_buildid || '?');
        } else {
            dot.classList.add('update-badge-hidden');
        }
    }

    var _openPopover = null;
    function _openUpdatePopover(anchor, appId) {
        _closeUpdatePopover();
        Bridge.callWithCallback('get_game_update_state', String(appId), function(json) {
            var state = {};
            try { state = JSON.parse(json || '{}') || {}; } catch(e) {}
            var pop = document.createElement('div');
            pop.className = 'update-popover';
            pop.innerHTML =
                '<div class="update-popover-row"><span>Installed build:</span><b>' +
                    (state.installed_buildid || '—') + '</b></div>' +
                '<div class="update-popover-row"><span>Steam build:</span><b>' +
                    (state.cm_buildid || '—') + '</b></div>' +
                '<button class="btn btn-sm btn-primary update-popover-check">Check now</button>';
            document.body.appendChild(pop);
            var rect = anchor.getBoundingClientRect();
            pop.style.position = 'fixed';
            pop.style.top = (rect.bottom + 6) + 'px';
            pop.style.left = Math.max(8, rect.right - 220) + 'px';
            var btn = pop.querySelector('.update-popover-check');
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                btn.disabled = true;
                btn.textContent = 'Checking...';
                Bridge.call('check_game_update', String(appId));
                // The task_finished listener in init() refreshes badges
                // through _onUpdateCheckResult; close the popover so the
                // user sees the toast and the dot recolour.
                setTimeout(_closeUpdatePopover, 250);
            });
            _openPopover = pop;
            // Close on outside click.
            setTimeout(function() {
                document.addEventListener('click', _outsidePopoverClick, { once: true });
            }, 0);
        });
    }

    function _outsidePopoverClick(e) {
        if (_openPopover && !_openPopover.contains(e.target)) {
            _closeUpdatePopover();
        }
    }

    function _closeUpdatePopover() {
        if (_openPopover && _openPopover.parentNode) {
            _openPopover.parentNode.removeChild(_openPopover);
        }
        _openPopover = null;
    }

    function _refreshAllBadges() {
        var grid = document.getElementById('library-grid');
        if (!grid) return;
        var dots = grid.querySelectorAll('.update-badge');
        dots.forEach(function(dot) {
            var appId = dot.dataset.appid;
            if (appId) _refreshUpdateBadge(dot, appId);
        });
    }

    function _onUpdateCheckResult(data) {
        var grid = document.getElementById('library-grid');
        if (grid) {
            var btns = grid.querySelectorAll('[data-action="check_update"]');
            btns.forEach(function(b) {
                if (b.dataset.checking) {
                    b.disabled = false;
                    b.textContent = 'Update';
                    delete b.dataset.checking;
                }
            });
        }
        _refreshAllBadges();
        if (data.up_to_date) {
            Components.showToast('success', 'Already up to date (build ' + (data.installed_buildid || '') + ')');
        } else if (data.updated) {
            Components.showToast('success', 'Updated to build ' + (data.cm_buildid || ''));
        } else if (data.error) {
            Components.showToast('error', data.error);
        }
    }

    function _onLureFixResult(data) {
        var grid = document.getElementById('library-grid');
        if (grid) {
            var btns = grid.querySelectorAll('[data-action="lure_fix"]');
            btns.forEach(function(b) {
                if (b.dataset.lurefixing) {
                    b.disabled = false;
                    b.textContent = 'Lure Fix';
                    delete b.dataset.lurefixing;
                }
            });
        }
        if (data.success) {
            Components.showToast('success', data.message || 'ACF patched. Restart Steam.');
        } else {
            Components.showToast('error', data.message || 'Lure fix failed');
        }
    }

    return {
        init: init,
        onPageEnter: onPageEnter,
        onPageLeave: onPageLeave
    };
})();
