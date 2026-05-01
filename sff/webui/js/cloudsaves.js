/**
 * SteaMidra — Cloud Saves Page
 * Steam userdata backup and restore.
 */

window.CloudSaves = (function() {
    'use strict';

    var _initialized = false;

    function init() {
        if (_initialized) return;
        _initialized = true;

        var steamBrowse = document.getElementById('cloud-steam-browse');
        var saveIdBtn = document.getElementById('cloud-save-id');
        var scanBtn = document.getElementById('cloud-scan');
        var backupBrowse = document.getElementById('cloud-backup-browse');
        var backupBtn = document.getElementById('cloud-backup-btn');
        var importBrowse = document.getElementById('cloud-import-browse');
        var importBtn = document.getElementById('cloud-import-btn');

        if (steamBrowse) {
            steamBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var input = document.getElementById('cloud-steam-path');
                        if (input) input.value = path;
                    }
                });
            });
        }

        if (saveIdBtn) {
            saveIdBtn.addEventListener('click', function() {
                var input = document.getElementById('cloud-steam32');
                if (input && input.value.trim()) {
                    Bridge.call('set_setting', 'steam32_id', input.value.trim());
                    Components.showToast('success', 'Steam32 ID saved');
                }
            });
        }

        if (scanBtn) {
            scanBtn.addEventListener('click', _scanGames);
        }

        if (backupBrowse) {
            backupBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var input = document.getElementById('cloud-backup-dest');
                        if (input) input.value = path;
                    }
                });
            });
        }

        if (backupBtn) {
            backupBtn.addEventListener('click', function() {
                var tbody = document.getElementById('cloud-games-tbody');
                var selectedRow = tbody ? tbody.querySelector('tr.selected') : null;
                if (!selectedRow) {
                    Components.showToast('warning', 'Please select a game from the scan results first');
                    return;
                }
                var appId = selectedRow.dataset.appid;
                var gameName = selectedRow.cells[1] ? selectedRow.cells[1].textContent : '';
                var dest = document.getElementById('cloud-backup-dest');
                var destPath = dest ? dest.value.trim() : '';
                if (!destPath) {
                    Components.showToast('warning', 'Please select a backup destination');
                    return;
                }
                var steamPath = document.getElementById('cloud-steam-path');
                var steam32 = document.getElementById('cloud-steam32');
                var sp = steamPath ? steamPath.value.trim() : '';
                var s32 = steam32 ? steam32.value.trim() : '';
                if (!sp || !s32) {
                    Components.showToast('warning', 'Please set both Steam path and Steam32 ID first');
                    return;
                }
                Bridge.call('backup_cloud_save', JSON.stringify({
                    app_id: appId, dest_path: destPath,
                    steam_path: sp, steam32_id: s32, game_name: gameName
                }));
                Components.showToast('info', 'Backing up saves for ' + (gameName || 'App ' + appId) + '...');
            });
        }

        if (importBrowse) {
            importBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var input = document.getElementById('cloud-import-path');
                        if (input) input.value = path;
                    }
                });
            });
        }

        if (importBtn) {
            importBtn.addEventListener('click', function() {
                var tbody = document.getElementById('cloud-games-tbody');
                var selectedRow = tbody ? tbody.querySelector('tr.selected') : null;
                if (!selectedRow) {
                    Components.showToast('warning', 'Please select a game from the scan results first');
                    return;
                }
                var appId = selectedRow.dataset.appid;
                var input = document.getElementById('cloud-import-path');
                var importPath = input ? input.value.trim() : '';
                if (!importPath) {
                    Components.showToast('warning', 'Please select a backup folder');
                    return;
                }
                var steamPath = document.getElementById('cloud-steam-path');
                var steam32 = document.getElementById('cloud-steam32');
                var sp = steamPath ? steamPath.value.trim() : '';
                var s32 = steam32 ? steam32.value.trim() : '';
                if (!sp || !s32) {
                    Components.showToast('warning', 'Please set both Steam path and Steam32 ID first');
                    return;
                }
                if (confirm('Restore saves from this backup? A safety backup will be created automatically.')) {
                    Bridge.call('restore_cloud_save', JSON.stringify({
                        backup_path: importPath, app_id: appId,
                        steam_path: sp, steam32_id: s32
                    }));
                    Components.showToast('info', 'Restoring saves...');
                }
            });
        }

        // Listen for task results
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'scan_cloud_games' && data.games) {
                    _renderGames(data.games);
                }
                if (data.task === 'backup_cloud_save' || data.task === 'restore_cloud_save') {
                    var logContent = document.getElementById('cloud-log-content');
                    var logOutput = document.getElementById('cloud-log');
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
        // Auto-fill steam path from settings
        Bridge.callWithCallback('get_setting', 'steam_path', function(val) {
            if (val) {
                var input = document.getElementById('cloud-steam-path');
                if (input && !input.value) input.value = val;
            }
        });
        Bridge.callWithCallback('get_setting', 'steam32_id', function(val) {
            if (val) {
                var input = document.getElementById('cloud-steam32');
                if (input && !input.value) input.value = val;
            }
        });
    }

    function _scanGames() {
        var steamPath = document.getElementById('cloud-steam-path');
        var steam32 = document.getElementById('cloud-steam32');
        var sp = steamPath ? steamPath.value.trim() : '';
        var s32 = steam32 ? steam32.value.trim() : '';

        if (!sp || !s32) {
            Components.showToast('warning', 'Please set both Steam path and Steam32 ID first');
            return;
        }

        Components.showToast('info', 'Scanning for cloud saves...');
        Bridge.call('scan_cloud_games', sp, s32);
    }

    function _renderGames(games) {
        var tableDiv = document.getElementById('cloud-games');
        var tbody = document.getElementById('cloud-games-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        games.forEach(function(game) {
            var tr = document.createElement('tr');
            tr.dataset.appid = game.app_id;
            tr.style.cursor = 'pointer';
            tr.innerHTML =
                '<td>' + game.app_id + '</td>' +
                '<td>' + Components.escapeHtml(game.name || 'Unknown') + '</td>' +
                '<td>' + (game.size || 'N/A') + '</td>';
            tr.addEventListener('click', function() {
                tbody.querySelectorAll('tr.selected').forEach(function(r) { r.classList.remove('selected'); r.style.background = ''; });
                this.classList.add('selected');
                this.style.background = 'var(--btn-bg)';
            });
            tbody.appendChild(tr);
        });

        if (tableDiv) tableDiv.classList.remove('hidden');
        Components.showToast('success', 'Found ' + games.length + ' games with save data');
    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
