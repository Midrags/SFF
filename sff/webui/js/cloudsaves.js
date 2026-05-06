/**
 * SteaMidra — Cloud Saves Page
 * Steam userdata backup and restore with provider support.
 */

window.CloudSaves = (function() {
    'use strict';

    var _initialized = false;
    var _provider = 'local';
    var _allSavesEntries = [];
    var _restoreLocationsData = {};

    // ── Provider helpers ──────────────────────────────────────────

    function _showProviderConfig(provider) {
        var folderCfg = document.getElementById('provider-config-folder');
        var rcloneCfg = document.getElementById('provider-config-rclone');
        var saveBtn = document.getElementById('provider-save-config');
        var backupDestRow = document.getElementById('cloud-backup-dest-row');
        var backupBtn = document.getElementById('cloud-backup-btn');

        if (folderCfg) folderCfg.style.display = 'none';
        if (rcloneCfg) rcloneCfg.style.display = 'none';
        if (saveBtn) saveBtn.style.display = 'none';
        if (backupDestRow) backupDestRow.style.display = '';

        var gdriveCfg = document.getElementById('provider-config-gdrive');
        if (gdriveCfg) gdriveCfg.style.display = 'none';

        if (provider === 'gdrive') {
            if (gdriveCfg) gdriveCfg.style.display = '';
            if (backupDestRow) backupDestRow.style.display = 'none';
            if (backupBtn) backupBtn.textContent = 'Backup via Google Drive';
        } else if (provider === 'rclone') {
            if (rcloneCfg) rcloneCfg.style.display = '';
            if (saveBtn) saveBtn.style.display = '';
            if (backupDestRow) backupDestRow.style.display = 'none';
            if (backupBtn) backupBtn.textContent = 'Upload via rclone';
        } else {
            if (backupBtn) backupBtn.textContent = 'Backup Selected Game';
        }
    }

    function _setActiveCard(provider) {
        document.querySelectorAll('.provider-card').forEach(function(card) {
            card.classList.toggle('active', card.dataset.provider === provider);
        });
    }

    function _saveProviderConfig() {
        Bridge.call('set_setting', 'cloud_provider', _provider);
        if (_provider === 'rclone') {
            var exe = document.getElementById('provider-rclone-exe');
            var remote = document.getElementById('provider-rclone-remote');
            if (exe) Bridge.call('set_setting', 'cloud_rclone_exe', exe.value.trim());
            if (remote) Bridge.call('set_setting', 'cloud_rclone_remote', remote.value.trim());
        }
        Components.showToast('success', 'Provider config saved');
    }

    function _autofillBundledExe(provider) {
        if (provider === 'rclone') {
            var inp = document.getElementById('provider-rclone-exe');
            if (inp && !inp.value.trim()) {
                Bridge.callWithCallback('get_bundled_tool_path', 'rclone', function(p) {
                    if (p && !inp.value.trim()) inp.value = p;
                });
            }
        }
    }

    function _loadRcloneRemotes() {
        var exeInp = document.getElementById('provider-rclone-exe');
        var rcloneExe = exeInp ? exeInp.value.trim() : '';
        var listBtn = document.getElementById('provider-rclone-list');
        if (listBtn) { listBtn.disabled = true; listBtn.textContent = 'Loading...'; }
        Bridge.call('rclone_list_remotes', JSON.stringify({ rclone_exe: rcloneExe }));
    }

    // ── Init ──────────────────────────────────────────────────────

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
        var saveConfigBtn = document.getElementById('provider-save-config');

        // Provider card clicks
        document.querySelectorAll('.provider-card').forEach(function(card) {
            card.addEventListener('click', function() {
                _provider = this.dataset.provider;
                _setActiveCard(_provider);
                _showProviderConfig(_provider);
                Bridge.call('set_setting', 'cloud_provider', _provider);
                _autofillBundledExe(_provider);
                if (_provider === 'gdrive') _checkGdriveStatus();
            });
        });

        // Google Drive connect / disconnect
        var gdriveConnectBtn = document.getElementById('gdrive-connect-btn');
        var gdriveDisconnectBtn = document.getElementById('gdrive-disconnect-btn');
        if (gdriveConnectBtn) {
            gdriveConnectBtn.addEventListener('click', function() {
                gdriveConnectBtn.disabled = true;
                gdriveConnectBtn.textContent = 'Connecting...';
                Bridge.call('gdrive_authorize');
            });
        }
        if (gdriveDisconnectBtn) {
            gdriveDisconnectBtn.addEventListener('click', function() {
                _setGdriveStatus(false, '');
                Components.showToast('info', 'Google Drive disconnected');
            });
        }

        // rclone provider chips, Load Remotes, Test, Setup in Terminal
        // Provider chip strip — pre-fill remote destination on click
        document.querySelectorAll('.rclone-chip').forEach(function(chip) {
            chip.addEventListener('click', function() {
                var prefix = this.dataset.prefix || '';
                var remoteInp = document.getElementById('provider-rclone-remote');
                if (remoteInp && prefix) remoteInp.value = prefix;
                document.querySelectorAll('.rclone-chip').forEach(function(c) { c.classList.remove('active'); });
                this.classList.add('active');
            });
        });

        // Setup in Terminal
        var rcloneSetupBtn = document.getElementById('provider-rclone-setup');
        if (rcloneSetupBtn) {
            rcloneSetupBtn.addEventListener('click', function() {
                var exeInp = document.getElementById('provider-rclone-exe');
                var rcloneExe = exeInp ? exeInp.value.trim() : '';
                rcloneSetupBtn.disabled = true;
                rcloneSetupBtn.textContent = 'Opening...';
                Bridge.call('rclone_open_config', JSON.stringify({ rclone_exe: rcloneExe }));
            });
        }

        var rcloneListBtn = document.getElementById('provider-rclone-list');
        if (rcloneListBtn) {
            rcloneListBtn.addEventListener('click', _loadRcloneRemotes);
        }
        var rcloneTestBtn = document.getElementById('provider-rclone-test');
        if (rcloneTestBtn) {
            rcloneTestBtn.addEventListener('click', function() {
                var exeInp = document.getElementById('provider-rclone-exe');
                var remoteInp = document.getElementById('provider-rclone-remote');
                var rcloneExe = exeInp ? exeInp.value.trim() : '';
                var remote = remoteInp ? remoteInp.value.trim() : '';
                if (!remote) {
                    Components.showToast('warning', 'Enter a remote destination first');
                    return;
                }
                rcloneTestBtn.disabled = true;
                rcloneTestBtn.textContent = 'Testing...';
                Bridge.call('rclone_test_remote', JSON.stringify({ rclone_exe: rcloneExe, remote: remote }));
            });
        }
        var rcloneDocsLink = document.getElementById('rclone-docs-link');
        if (rcloneDocsLink) {
            rcloneDocsLink.addEventListener('click', function(e) {
                e.preventDefault();
                Bridge.call('open_url', 'https://rclone.org/docs/');
            });
        }

        // Provider config browse buttons
        var folderBrowse = document.getElementById('provider-folder-browse');
        if (folderBrowse) {
            folderBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('provider-folder-path');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        var rcloneBrowse = document.getElementById('provider-rclone-browse');
        if (rcloneBrowse) {
            rcloneBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('provider-rclone-exe');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        if (saveConfigBtn) {
            saveConfigBtn.addEventListener('click', _saveProviderConfig);
        }

        // Steam path / Steam32 ID
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

        // Backup button — routes by provider
        if (backupBtn) {
            backupBtn.addEventListener('click', function() {
                var steamPath = document.getElementById('cloud-steam-path');
                var steam32 = document.getElementById('cloud-steam32');
                var sp = steamPath ? steamPath.value.trim() : '';
                var s32 = steam32 ? steam32.value.trim() : '';

                var tbody = document.getElementById('cloud-games-tbody');
                var selectedRow = tbody ? tbody.querySelector('tr.selected') : null;
                if (!selectedRow) {
                    Components.showToast('warning', 'Select a game from the scan results first');
                    return;
                }
                var appId = selectedRow.dataset.appid;
                var gameName = selectedRow.cells[1] ? selectedRow.cells[1].textContent : '';

                if (!sp || !s32) {
                    Components.showToast('warning', 'Set both Steam path and Steam32 ID first');
                    return;
                }

                if (_provider === 'rclone') {
                    var rExe = document.getElementById('provider-rclone-exe');
                    var rRemote = document.getElementById('provider-rclone-remote');
                    var rExePath = rExe ? rExe.value.trim() : '';
                    var rRemotePath = rRemote ? rRemote.value.trim() : '';
                    if (!rExePath || !rRemotePath) {
                        Components.showToast('warning', 'Set the rclone executable and remote destination first, then save the config');
                        return;
                    }
                    Bridge.call('rclone_backup_save', JSON.stringify({
                        app_id: appId, game_name: gameName,
                        steam_path: sp, steam32_id: s32,
                        rclone_exe: rExePath, remote_dest: rRemotePath
                    }));
                    Components.showToast('info', 'Uploading via rclone...');
                    return;
                }

                var destPath = '';
                if (_provider === 'gdrive') {
                    // Single-game backup via GDrive API — construct entry from selected game
                    var sp2 = sp;
                    var s32a = s32;
                    var entry = {
                        location: 'Steam Userdata',
                        folder_name: String(appId),
                        app_id: parseInt(appId, 10),
                        game_name: gameName || ('App ' + appId),
                        label: appId + (gameName ? ' - ' + gameName : ''),
                        source_path: sp2 + '/userdata/' + s32a + '/' + appId,
                        file_count: 0
                    };
                    Bridge.call('backup_all_save_locations', JSON.stringify({
                        entries: [entry],
                        provider: 'gdrive_api'
                    }));
                    Components.showToast('info', 'Uploading to Google Drive...');
                    return;
                } else {
                    var dest = document.getElementById('cloud-backup-dest');
                    destPath = dest ? dest.value.trim() : '';
                    if (!destPath) {
                        Components.showToast('warning', 'Select a backup destination');
                        return;
                    }
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
                    Components.showToast('warning', 'Select a game from the scan results first');
                    return;
                }
                var appId = selectedRow.dataset.appid;
                var input = document.getElementById('cloud-import-path');
                var importPath = input ? input.value.trim() : '';
                if (!importPath) {
                    Components.showToast('warning', 'Select a backup folder');
                    return;
                }
                var steamPath = document.getElementById('cloud-steam-path');
                var steam32 = document.getElementById('cloud-steam32');
                var sp = steamPath ? steamPath.value.trim() : '';
                var s32 = steam32 ? steam32.value.trim() : '';
                if (!sp || !s32) {
                    Components.showToast('warning', 'Set both Steam path and Steam32 ID first');
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

        // All Save Locations — scan
        var allSavesScanBtn = document.getElementById('all-saves-scan-btn');
        if (allSavesScanBtn) {
            allSavesScanBtn.addEventListener('click', _scanAllSaveLocations);
        }

        // All Save Locations — backup destination browse
        var allSavesDestBrowse = document.getElementById('all-saves-dest-browse');
        if (allSavesDestBrowse) {
            allSavesDestBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('all-saves-dest');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        // All Save Locations — backup all now
        var allSavesBackupBtn = document.getElementById('all-saves-backup-btn');
        if (allSavesBackupBtn) {
            allSavesBackupBtn.addEventListener('click', _backupAllSaves);
        }

        // Select all checkbox
        var selectAll = document.getElementById('all-saves-select-all');
        if (selectAll) {
            selectAll.addEventListener('change', function() {
                document.querySelectorAll('.all-saves-row-check').forEach(function(cb) {
                    cb.checked = selectAll.checked;
                });
            });
        }

        // Restore — backup root browse
        var restoreBackupBrowse = document.getElementById('restore-backup-browse');
        if (restoreBackupBrowse) {
            restoreBackupBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('restore-backup-root');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        // Restore — scan backups
        var restoreScanBtn = document.getElementById('restore-scan-btn');
        if (restoreScanBtn) {
            restoreScanBtn.addEventListener('click', _scanBackupRoot);
        }

        // Restore — location select
        var restoreLocSel = document.getElementById('restore-location-select');
        if (restoreLocSel) {
            restoreLocSel.addEventListener('change', function() {
                _renderRestoreGames(this.value);
            });
        }

        // Restore — restore selected
        var restoreSelectedBtn = document.getElementById('restore-selected-btn');
        if (restoreSelectedBtn) {
            restoreSelectedBtn.addEventListener('click', _doRestoreSelected);
        }

        // Task results
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);

                if (data.task === 'gdrive_authorize') {
                    var btn = document.getElementById('gdrive-connect-btn');
                    if (btn) { btn.disabled = false; btn.textContent = 'Connect Google Drive'; }
                    if (data.success) {
                        _setGdriveStatus(true, data.email || '');
                        Components.showToast('success', 'Google Drive connected');
                    } else {
                        Components.showToast('error', data.message || 'Connection failed');
                    }
                }

                if (data.task === 'scan_cloud_games' && data.games) {
                    _renderGames(data.games);
                }

                if (data.task === 'scan_all_save_locations') {
                    _allSavesEntries = data.entries || [];
                    _renderAllSavesResults(_allSavesEntries);
                }

                if (data.task === 'backup_all_save_locations') {
                    var logEl = document.getElementById('all-saves-log-content');
                    var logDiv = document.getElementById('all-saves-log');
                    if (logEl && data.log) { logEl.textContent = data.log; }
                    if (logDiv) logDiv.classList.remove('hidden');
                    if (data.success) {
                        Components.showToast('success', data.message || 'Backup complete');
                    } else {
                        Components.showToast('error', data.message || 'Backup failed');
                    }
                }

                if (data.task === 'scan_backup_root') {
                    if (data.success && data.locations) {
                        _restoreLocationsData = data.locations;
                        _renderRestoreLocations(data.locations);
                    } else {
                        Components.showToast('error', data.message || 'Scan failed');
                    }
                }

                if (data.task === 'restore_save_location') {
                    var logEl2 = document.getElementById('all-saves-log-content');
                    var logDiv2 = document.getElementById('all-saves-log');
                    if (logEl2 && data.log) { logEl2.textContent = data.log; }
                    if (logDiv2) logDiv2.classList.remove('hidden');
                    if (data.success) {
                        Components.showToast('success', 'Restore complete');
                    } else {
                        Components.showToast('error', data.message || 'Restore failed');
                    }
                }

                if (data.task === 'rclone_test_remote') {
                    var testBtn = document.getElementById('provider-rclone-test');
                    if (testBtn) { testBtn.disabled = false; testBtn.textContent = 'Test'; }
                    var remoteVal = (document.getElementById('provider-rclone-remote') || {}).value || '';
                    if (data.success) {
                        Components.showToast('success', 'Remote OK: ' + remoteVal);
                    } else {
                        Components.showToast('error', 'Remote failed: ' + (data.error || 'unknown error'));
                    }
                }

                if (data.task === 'rclone_list_remotes') {
                    var loadBtn = document.getElementById('provider-rclone-list');
                    if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = 'Load Remotes'; }
                    if (data.success) {
                        var dl = document.getElementById('rclone-remotes-list');
                        if (dl) {
                            dl.innerHTML = '';
                            (data.remotes || []).forEach(function(r) {
                                var opt = document.createElement('option');
                                opt.value = r;
                                dl.appendChild(opt);
                            });
                        }
                        if (!data.remotes || !data.remotes.length) {
                            Components.showToast('warning', 'No remotes found. Click Setup in Terminal to add one.');
                        } else {
                            Components.showToast('success', 'Found ' + data.remotes.length + ' remote(s): ' + data.remotes.join(', '));
                        }
                    } else {
                        Components.showToast('error', 'Could not list remotes: ' + (data.error || 'unknown error'));
                    }
                }

                if (data.task === 'rclone_open_config') {
                    var setupBtn = document.getElementById('provider-rclone-setup');
                    if (setupBtn) { setupBtn.disabled = false; setupBtn.textContent = 'Setup in Terminal'; }
                    if (data.success) {
                        Components.showToast('info', 'rclone config opened. Add a remote, then click Load Remotes.');
                    } else {
                        Components.showToast('error', 'Could not open terminal: ' + (data.error || 'unknown error'));
                    }
                }

                var cloudTasks = ['backup_cloud_save', 'restore_cloud_save', 'rclone_backup_save'];
                if (cloudTasks.indexOf(data.task) !== -1) {
                    var logContent = document.getElementById('cloud-log-content');
                    var logOutput = document.getElementById('cloud-log');
                    if (logContent && data.log) {
                        logContent.textContent = data.log;
                        if (logOutput) logOutput.classList.remove('hidden');
                    }
                    if (data.success) {
                        Components.showToast('success', data.message || 'Done');
                    } else {
                        Components.showToast('error', data.message || 'Operation failed');
                    }
                }
            } catch(e) {}
        });
    }

    function onPageEnter() {
        init();
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
        // Restore saved provider
        Bridge.callWithCallback('get_setting', 'cloud_provider', function(val) {
            if (val) {
                _provider = val;
                _setActiveCard(_provider);
                _showProviderConfig(_provider);
                // Load provider-specific config fields
                if (_provider === 'gdrive') {
                    _checkGdriveStatus();
                } else if (_provider === 'rclone') {
                    Bridge.callWithCallback('get_setting', 'cloud_rclone_exe', function(v) {
                        var inp = document.getElementById('provider-rclone-exe');
                        if (inp) {
                            if (v) { inp.value = v; } else { _autofillBundledExe('rclone'); }
                        }
                    });
                    Bridge.callWithCallback('get_setting', 'cloud_rclone_remote', function(v) {
                        var inp = document.getElementById('provider-rclone-remote');
                        if (inp && v) inp.value = v;
                    });
                }
            }
        });
    }

    function _scanGames() {
        var steamPath = document.getElementById('cloud-steam-path');
        var steam32 = document.getElementById('cloud-steam32');
        var sp = steamPath ? steamPath.value.trim() : '';
        var s32 = steam32 ? steam32.value.trim() : '';

        if (!sp || !s32) {
            Components.showToast('warning', 'Set both Steam path and Steam32 ID first');
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

    // ── Google Drive helpers ───────────────────────────────────────

    function _checkGdriveStatus() {
        try {
            var result = Bridge.callSync('gdrive_status');
            if (result) {
                var status = JSON.parse(result);
                _setGdriveStatus(status.connected, status.email || '');
            }
        } catch(e) {}
    }

    function _setGdriveStatus(connected, email) {
        var statusText = document.getElementById('gdrive-status-text');
        var connectBtn = document.getElementById('gdrive-connect-btn');
        var disconnectBtn = document.getElementById('gdrive-disconnect-btn');
        if (connected) {
            if (statusText) statusText.textContent = 'Connected' + (email ? ': ' + email : '');
            if (connectBtn) connectBtn.style.display = 'none';
            if (disconnectBtn) disconnectBtn.style.display = '';
        } else {
            if (statusText) statusText.textContent = 'Not connected';
            if (connectBtn) { connectBtn.style.display = ''; connectBtn.disabled = false; connectBtn.textContent = 'Connect Google Drive'; }
            if (disconnectBtn) disconnectBtn.style.display = 'none';
        }
    }

    // ── All Save Locations helpers ────────────────────────────────

    function _scanAllSaveLocations() {
        var steamPath = document.getElementById('cloud-steam-path');
        var steam32 = document.getElementById('cloud-steam32');
        var sp = steamPath ? steamPath.value.trim() : '';
        var s32 = steam32 ? steam32.value.trim() : '';
        Components.showToast('info', 'Scanning all save locations...');
        Bridge.call('scan_all_save_locations', JSON.stringify({ steam_path: sp, steam32_id: s32 }));
    }

    function _renderAllSavesResults(entries) {
        var tbody = document.getElementById('all-saves-tbody');
        var resultsDiv = document.getElementById('all-saves-results');
        var backupBtn = document.getElementById('all-saves-backup-btn');
        var destRow = document.getElementById('all-saves-dest-row');
        if (!tbody) return;
        tbody.innerHTML = '';
        entries.forEach(function(entry, idx) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td><input type="checkbox" class="all-saves-row-check" data-idx="' + idx + '" checked></td>' +
                '<td>' + Components.escapeHtml(entry.location) + '</td>' +
                '<td>' + Components.escapeHtml(entry.label) + '</td>' +
                '<td>' + (entry.file_count || 0) + '</td>';
            tbody.appendChild(tr);
        });
        if (resultsDiv) resultsDiv.classList.remove('hidden');
        if (backupBtn) backupBtn.style.display = '';
        // Show dest row only for non-gdrive providers
        if (destRow) destRow.style.display = (_provider === 'gdrive') ? 'none' : '';
        Components.showToast('success', 'Found ' + entries.length + ' save folder(s)');
    }

    function _backupAllSaves() {
        var checked = document.querySelectorAll('.all-saves-row-check:checked');
        var selectedEntries = [];
        checked.forEach(function(cb) {
            var idx = parseInt(cb.dataset.idx, 10);
            if (!isNaN(idx) && _allSavesEntries[idx]) {
                selectedEntries.push(_allSavesEntries[idx]);
            }
        });
        if (!selectedEntries.length) {
            Components.showToast('warning', 'No save folders selected');
            return;
        }
        var destInp = document.getElementById('all-saves-dest');
        var destPath = destInp ? destInp.value.trim() : '';
        var rcloneExeInp = document.getElementById('provider-rclone-exe');
        var rcloneRemoteInp = document.getElementById('provider-rclone-remote');
        var providerKey = _provider === 'gdrive' ? 'gdrive_api' : _provider;
        var needsDest = providerKey === 'local' || providerKey === 'gdrive_sync';
        if (needsDest && !destPath) {
            Components.showToast('warning', 'Set the backup destination folder first');
            return;
        }
        if (providerKey === 'rclone') {
            var rcloneRemote = rcloneRemoteInp ? rcloneRemoteInp.value.trim() : '';
            if (!rcloneRemote) {
                Components.showToast('warning', 'Set the rclone remote destination in the provider config first');
                return;
            }
        }
        Bridge.call('backup_all_save_locations', JSON.stringify({
            entries: selectedEntries,
            provider: providerKey,
            dest_path: destPath,
            rclone_exe: rcloneExeInp ? rcloneExeInp.value.trim() : '',
            remote_dest: rcloneRemoteInp ? rcloneRemoteInp.value.trim() : ''
        }));
        Components.showToast('info', 'Backing up ' + selectedEntries.length + ' folder(s)...');
    }

    function _scanBackupRoot() {
        var rootInp = document.getElementById('restore-backup-root');
        var rootPath = rootInp ? rootInp.value.trim() : '';
        var providerKey = _provider === 'gdrive' ? 'gdrive_api' : _provider;
        if (providerKey === 'rclone') {
            var rcloneRemoteInp = document.getElementById('provider-rclone-remote');
            var rcloneRemote = rcloneRemoteInp ? rcloneRemoteInp.value.trim() : '';
            if (!rcloneRemote) {
                Components.showToast('warning', 'Set the rclone remote destination in the provider config first');
                return;
            }
            var rcloneExeInp = document.getElementById('provider-rclone-exe');
            Components.showToast('info', 'Scanning backups on rclone remote...');
            Bridge.call('scan_backup_root', JSON.stringify({
                provider: 'rclone',
                backup_root: '',
                rclone_exe: rcloneExeInp ? rcloneExeInp.value.trim() : '',
                remote_dest: rcloneRemote
            }));
            return;
        }
        if (providerKey === 'local' && !rootPath) {
            Components.showToast('warning', 'Set the backup root folder first');
            return;
        }
        Components.showToast('info', 'Scanning backups...');
        Bridge.call('scan_backup_root', JSON.stringify({ provider: providerKey, backup_root: rootPath }));
    }

    function _renderRestoreLocations(locations) {
        var sel = document.getElementById('restore-location-select');
        var resultsDiv = document.getElementById('restore-results');
        if (!sel) return;
        sel.innerHTML = '<option value="">Select a location...</option>';
        var keys = Object.keys(locations);
        keys.forEach(function(loc) {
            var opt = document.createElement('option');
            opt.value = loc;
            opt.textContent = loc + ' (' + (locations[loc].games || []).length + ' games)';
            sel.appendChild(opt);
        });
        if (resultsDiv) resultsDiv.classList.remove('hidden');
        // Show/hide restore folder row based on provider
        var restoreFolderRow = document.getElementById('restore-folder-input-row');
        if (restoreFolderRow) restoreFolderRow.style.display = (_provider === 'gdrive') ? 'none' : '';
        Components.showToast('success', 'Found ' + keys.length + ' backup location(s)');
    }

    function _renderRestoreGames(locationName) {
        var gamesSel = document.getElementById('restore-game-select');
        var gamesList = document.getElementById('restore-games-list');
        if (!gamesSel || !locationName) return;
        var loc = _restoreLocationsData[locationName];
        gamesSel.innerHTML = '<option value="">Select a game...</option>';
        if (loc && loc.games) {
            loc.games.forEach(function(game, idx) {
                var opt = document.createElement('option');
                opt.value = idx;
                opt.textContent = game.game_name || game.folder_name;
                if (game.app_id) opt.textContent = game.app_id + ' - ' + opt.textContent;
                if (game.backed_up_at) opt.textContent += '  [' + game.backed_up_at.split('T')[0] + ']';
                gamesSel.appendChild(opt);
            });
        }
        if (gamesList) gamesList.classList.remove('hidden');
    }

    function _doRestoreSelected() {
        var locSel = document.getElementById('restore-location-select');
        var gameSel = document.getElementById('restore-game-select');
        var locName = locSel ? locSel.value : '';
        var gameIdx = gameSel ? parseInt(gameSel.value, 10) : -1;
        if (!locName || isNaN(gameIdx) || gameIdx < 0) {
            Components.showToast('warning', 'Select both a location and a game first');
            return;
        }
        var loc = _restoreLocationsData[locName];
        if (!loc || !loc.games || !loc.games[gameIdx]) {
            Components.showToast('warning', 'Game not found in backup data');
            return;
        }
        var entry = loc.games[gameIdx];
        if (!entry.source_path) {
            Components.showToast('warning', 'No source path in backup metadata — cannot restore');
            return;
        }
        if (!confirm('Restore "' + (entry.game_name || entry.folder_name) + '" to:\n' + entry.source_path + '\n\nA safety backup will be created automatically.')) {
            return;
        }
        var restoreEntry = Object.assign({}, entry);
        if (_provider === 'rclone') {
            var rcloneExeInp = document.getElementById('provider-rclone-exe');
            restoreEntry.rclone_exe = rcloneExeInp ? rcloneExeInp.value.trim() : '';
        }
        Bridge.call('restore_save_location', JSON.stringify(restoreEntry));
        Components.showToast('info', 'Restoring...');
    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
