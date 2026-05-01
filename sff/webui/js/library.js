/**
 * SteaMidra — Library Page
 * Shows installed/downloaded games from AppList + Steam libraries.
 */

window.Library = (function() {
    'use strict';

    var _initialized = false;

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
                    } else {
                        Bridge.call('run_game_action', appId, action);
                    }
                }
            });
        }
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
            var actions = card.querySelector('.game-card-actions');
            if (actions) {
                actions.innerHTML =
                    '<button class="btn btn-sm" data-action="fix" data-appid="' + game.app_id + '" data-tooltip="Fix this game">Fix</button>' +
                    '<button class="btn btn-sm" data-action="dlc_check" data-appid="' + game.app_id + '" data-tooltip="Check DLCs">DLC</button>' +
                    '<button class="btn btn-sm" data-action="workshop" data-appid="' + game.app_id + '" data-tooltip="Open Workshop">Workshop</button>';
            }

            if (grid) grid.appendChild(card);
        });


    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
