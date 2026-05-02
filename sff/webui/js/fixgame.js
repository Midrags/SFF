/**
 * SteaMidra — Fix Game Page
 * Emulator mode picker, options, and game fixing workflow.
 */

window.FixGame = (function() {
    'use strict';

    var _initialized = false;

    function init() {
        if (_initialized) return;
        _initialized = true;

        var browseBtn = document.getElementById('fixgame-browse');
        var refreshBtn = document.getElementById('fixgame-refresh');
        var applyBtn = document.getElementById('fixgame-apply');
        var revertBtn = document.getElementById('fixgame-revert');

        if (browseBtn) {
            browseBtn.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var select = document.getElementById('fixgame-game-select');
                        if (select) {
                            var opt = document.createElement('option');
                            opt.value = path;
                            opt.textContent = path;
                            opt.selected = true;
                            select.appendChild(opt);
                        }
                    }
                });
            });
        }

        var avatarBrowseBtn = document.getElementById('fixgame-avatar-browse');
        if (avatarBrowseBtn) {
            avatarBrowseBtn.addEventListener('click', function() {
                Bridge.callSync('browse_image_file', function(path) {
                    if (path) {
                        var avatarInput = document.getElementById('fixgame-avatar');
                        if (avatarInput) avatarInput.value = path;
                    }
                });
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', _loadGameList);
        }

        if (applyBtn) {
            applyBtn.addEventListener('click', _applyFix);
        }

        if (revertBtn) {
            revertBtn.addEventListener('click', _revertFix);
        }

        // Toggle GSE options based on mode selection
        document.querySelectorAll('input[name="emu-mode"]').forEach(function(radio) {
            radio.addEventListener('change', function() {
                var gseOptions = document.getElementById('gse-options');
                if (gseOptions) {
                    gseOptions.style.display =
                        (this.value === 'coldclient_advanced') ? 'block' : 'none';
                }
            });
        });

        // Toggle GSE credentials based on auth mode
        document.querySelectorAll('input[name="gse-auth"]').forEach(function(radio) {
            radio.addEventListener('change', function() {
                var creds = document.getElementById('gse-creds');
                if (creds) {
                    creds.style.display = (this.value === 'login') ? 'block' : 'none';
                }
            });
        });

        // Listen for task results
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'fix_game' || data.task === 'revert_game') {
                    var logContent = document.getElementById('fixgame-log-content');
                    var logOutput = document.getElementById('fixgame-log');
                    if (logContent && data.log) {
                        logContent.textContent = data.log;
                        if (logOutput) logOutput.classList.remove('hidden');
                    }
                }
            } catch(e) {}
        });
    }

    function onPageEnter() {
        init();
        _loadGameList();
    }

    function _loadGameList() {
        Bridge.callSync('get_fix_game_list', function(json) {
            try {
                var games = JSON.parse(json || '[]');
                var select = document.getElementById('fixgame-game-select');
                if (select) {
                    var current = select.value;
                    select.innerHTML = '<option value="">-- Select a game --</option>';
                    games.forEach(function(game) {
                        var opt = document.createElement('option');
                        opt.value = game.path || game.name;
                        opt.textContent = game.name + (game.app_id ? ' (' + game.app_id + ')' : '');
                        if (game.app_id) opt.dataset.appid = game.app_id;
                        select.appendChild(opt);
                    });
                    if (current) select.value = current;
                }
            } catch(e) {}
        });
    }

    function _applyFix() {
        var gameSelect = document.getElementById('fixgame-game-select');
        var appIdInput = document.getElementById('fixgame-appid');
        var usernameInput = document.getElementById('fixgame-username');
        var steamIdInput = document.getElementById('fixgame-steamid');

        var gamePath = gameSelect ? gameSelect.value : '';
        if (!gamePath) {
            Components.showToast('warning', 'Please select a game first');
            return;
        }

        var appId = appIdInput ? appIdInput.value : '';
        // Try to get appId from select option
        if (!appId && gameSelect) {
            var opt = gameSelect.options[gameSelect.selectedIndex];
            if (opt && opt.dataset.appid) appId = opt.dataset.appid;
        }

        var emuMode = document.querySelector('input[name="emu-mode"]:checked');
        var settingsMode = document.querySelector('input[name="settings-mode"]:checked');
        var gseAuth = document.querySelector('input[name="gse-auth"]:checked');

        var avatarInput = document.getElementById('fixgame-avatar');
        var config = {
            game_path: gamePath,
            app_id: appId,
            emu_mode: emuMode ? emuMode.value : 'regular',
            username: usernameInput ? usernameInput.value : 'Player',
            steam_id: steamIdInput ? steamIdInput.value : '',
            avatar_path: avatarInput ? avatarInput.value : '',
            unpack_steamstub: document.getElementById('fix-steamstub') ? document.getElementById('fix-steamstub').checked : true,
            use_experimental_steamless: document.getElementById('fix-steamless-exp') ? document.getElementById('fix-steamless-exp').checked : true,
            goldberg_update: document.getElementById('fix-goldberg-update') ? document.getElementById('fix-goldberg-update').checked : false,
            create_launch_bat: document.getElementById('fix-launchbat') ? document.getElementById('fix-launchbat').checked : false,
            simple_settings: settingsMode ? settingsMode.value === 'simple' : false,
            gse_auth_mode: gseAuth ? gseAuth.value : 'anonymous',
            gse_username: document.getElementById('gse-username') ? document.getElementById('gse-username').value : '',
            gse_password: document.getElementById('gse-password') ? document.getElementById('gse-password').value : ''
        };

        Components.showToast('info', 'Applying fix to ' + gamePath + '...');
        Bridge.call('fix_game', JSON.stringify(config));
    }

    function _revertFix() {
        var gameSelect = document.getElementById('fixgame-game-select');
        var gamePath = gameSelect ? gameSelect.value : '';
        if (!gamePath) {
            Components.showToast('warning', 'Please select a game first');
            return;
        }
        if (confirm('Revert changes for this game? Original DLLs will be restored.')) {
            Bridge.call('revert_game', gamePath);
            Components.showToast('info', 'Reverting changes...');
        }
    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
