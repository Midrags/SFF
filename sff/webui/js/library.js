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
                        App.navigateTo('fixgame');
                    } else if (action === 'delete') {
                        _pendingDelete = {
                            appId: appId,
                            gamePath: btn.dataset.gamepath || ''
                        };
                        var nameEl = document.getElementById('library-delete-game-name');
                        if (nameEl) nameEl.textContent = btn.dataset.gamename || ('App ' + appId);
                        Components.showModal('library-delete-modal');
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
            var card = Components.createGameCard(game, { index: index });

            // Add library-specific actions
            var safeName = (game.name || '').replace(/"/g, '&quot;');
            var safePath = (game.path || '').replace(/"/g, '&quot;');
            var actions = card.querySelector('.game-card-actions');
            if (actions) {
                actions.innerHTML =
                    '<button class="btn btn-sm" data-action="fix" data-appid="' + game.app_id + '" data-tooltip="Fix this game">Fix</button>' +
                    '<button class="btn btn-sm" data-action="dlc_check" data-appid="' + game.app_id + '" data-tooltip="Check DLCs">DLC</button>' +
                    '<button class="btn btn-sm" data-action="workshop" data-appid="' + game.app_id + '" data-tooltip="Open Workshop">Workshop</button>' +
                    '<button class="btn btn-sm btn-danger" data-action="delete" data-appid="' + game.app_id + '" data-gamepath="' + safePath + '" data-gamename="' + safeName + '" data-tooltip="Remove this game">\u2715</button>';
            }

            if (grid) grid.appendChild(card);
        });


    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
