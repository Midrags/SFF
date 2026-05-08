/**
 * SteaMidra — Library Page
 * Shows installed/downloaded games from AppList + Steam libraries.
 */

window.Library = (function() {
    'use strict';

    var _initialized = false;
    var _pendingDelete = null; // { appId, gamePath }

    function init() {
        if (_initialized) return;
        _initialized = true;

        var refreshBtn = document.getElementById('library-refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', _refreshLibrary);
        }

        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'library_loaded' && Array.isArray(data.games)) {
                    _renderLibrary(data.games);
                }
                if (data.task === 'delete_game') {
                    if (data.success) {
                        _refreshLibrary();
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
                    if (action === 'fix') {
                        FixGame.preSelect(appId);
                        App.navigateTo('fixgame');
                    } else if (action === 'delete') {
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
        _refreshLibrary();
    }

    function _refreshLibrary() {
        Bridge.call('load_library');
    }

    function _renderLibrary(games) {
        var grid = document.getElementById('library-grid');
        var empty = document.getElementById('library-empty');

        if (grid) grid.innerHTML = '';

        if (games.length === 0) {
            if (grid) grid.classList.add('hidden');
            if (empty) empty.classList.remove('hidden');
            return;
        }

        if (grid) grid.classList.remove('hidden');
        if (empty) empty.classList.add('hidden');

        games.forEach(function(game, index) {
            game.installed = true;
            var card = Components.createGameCard(game, { index: index, forceShowImage: true });

            // Add library-specific actions
            var safeName = (game.name || '').replace(/"/g, '&quot;');
            var safePath = (game.path || '').replace(/"/g, '&quot;');
            var actions = card.querySelector('.game-card-actions');
            if (actions) {
                actions.innerHTML =
                    '<button class="btn btn-sm" data-action="fix" data-appid="' + game.app_id + '" data-tooltip="Fix this game">Fix</button>' +
                    '<button class="btn btn-sm" data-action="dlc_check" data-appid="' + game.app_id + '" data-tooltip="Check DLCs">DLC</button>' +
                    '<button class="btn btn-sm" data-action="workshop" data-appid="' + game.app_id + '" data-tooltip="Open Workshop">Workshop</button>' +
                    '<button class="btn btn-sm" data-action="lure_fix" data-appid="' + game.app_id + '" data-tooltip="Patch ACF to match Steam CM latest — no download, stops update prompt">Lure Fix</button>' +
                    '<button class="btn btn-sm" data-action="check_update" data-appid="' + game.app_id + '" data-tooltip="Download latest manifests and patch ACF">Update</button>' +
                    '<button class="btn btn-sm btn-danger" data-action="delete" data-appid="' + game.app_id + '" data-gamepath="' + safePath + '" data-gamename="' + safeName + '" data-tooltip="Remove this game">\u2715</button>';
            }

            if (grid) grid.appendChild(card);
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
        onPageEnter: onPageEnter
    };
})();
