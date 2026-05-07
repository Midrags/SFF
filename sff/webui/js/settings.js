/**
 * SteaMidra — Settings Page
 * Theme picker, paths, API keys, AppList profiles, preferences.
 */

window.Settings = (function() {
    'use strict';

    var _initialized = false;
    var THEMES = [
        { id: 'dark', name: 'Dark', bg: '#2d2d2d', accent: '#4a9eff' },
        { id: 'light', name: 'Light', bg: '#fafafa', accent: '#2563eb' },
        { id: 'cherry', name: 'Cherry', bg: '#1a0a0a', accent: '#e84040' },
        { id: 'sunset', name: 'Sunset', bg: '#1a0f0a', accent: '#e88040' },
        { id: 'forest', name: 'Forest', bg: '#0a1a0a', accent: '#40e840' },
        { id: 'grape', name: 'Grape', bg: '#120a1a', accent: '#8040e8' },
        { id: 'cyberpunk', name: 'Cyberpunk', bg: '#0a0a1a', accent: '#ff006a' },
        { id: 'pink', name: 'Pink', bg: '#1a0a18', accent: '#e84393' },
        { id: 'nord', name: 'Nord', bg: '#2e3440', accent: '#88c0d0' },
        { id: 'dracula', name: 'Dracula', bg: '#282a36', accent: '#bd93f9' },
        { id: 'pastel', name: 'Pastel', bg: '#faf0e6', accent: '#e6a07c' },
        { id: 'amoled', name: 'AMOLED', bg: '#000000', accent: '#8142fa' },
        { id: 'bee', name: 'Bee', bg: '#fcdd6a', accent: '#fff200' },
        { id: 'blue-gld', name: 'Blue', bg: '#24273a', accent: '#8aadf4' },
        { id: 'crystalmeth', name: 'Crystal', bg: '#69a1cf', accent: '#68d8ff' },
        { id: 'gld-default', name: 'GLD Default', bg: '#141414', accent: '#8142fa' },
        { id: 'discord-dark', name: 'Discord Dark', bg: '#121214', accent: '#5865f2' },
        { id: 'discord-light', name: 'Discord Light', bg: '#f3f3f4', accent: '#5865f2' },
        { id: 'discord', name: 'Discord', bg: '#2c2d32', accent: '#5865f2' },
        { id: 'gaussian', name: 'Gaussian', bg: '#1a1919', accent: '#8142fa' },
        { id: 'less-depressing', name: 'Less Depressing', bg: '#202021', accent: '#7b89f8' },
        { id: 'gld-light', name: 'GLD Light', bg: '#a3adad', accent: '#00adff' },
        { id: 'lsd', name: 'LSD', bg: '#08101f', accent: '#6cff00' },
        { id: 'gld-midnight', name: 'GLD Midnight', bg: '#9aa6ee', accent: '#8789fa' },
        { id: 'neon-rider', name: 'Neon Rider', bg: '#66d1c2', accent: '#f000ff' },
        { id: 'rdr2', name: 'RDR2', bg: '#1c1c1c', accent: '#cc6152' },
        { id: 'real-madrid', name: 'Real Madrid', bg: '#ababab', accent: '#fabc01' },
        { id: 'seaweed', name: 'Seaweed', bg: '#151a1e', accent: '#00ff86' },
        { id: 'steam-gld', name: 'Steam', bg: '#161d25', accent: '#66c0f4' },
        { id: 'void', name: 'Void', bg: '#0c0c0c', accent: '#7b56cc' },
        { id: 'dawn', name: 'Dawn', bg: '#27293b', accent: '#979ffb', image: true },
        { id: 'dusk', name: 'Dusk', bg: '#282121', accent: '#fe7764', image: true },
        { id: 'flow', name: 'Flow', bg: '#005498', accent: '#68d8ff', image: true },
        { id: 'lake', name: 'Lake', bg: '#24273a', accent: '#8aadf4', image: true },
        { id: 'midnight-city', name: 'Midnight City', bg: '#20034a', accent: '#8aadf4', image: true },
        { id: 'snow', name: 'Snow', bg: '#a3cde7', accent: '#00eeff', image: true }
    ];

    function init() {
        if (_initialized) return;
        _initialized = true;

        _renderThemePicker();
        _initPathControls();
        _initProfileControls();
        _initPreferenceControls();
        _initAutoBackupControls();
        _initAboutLinks();
        _initAppListActions();
    }

    function onPageEnter() {
        init();
        _loadCurrentSettings();
        _loadProfiles();
    }

    function _renderThemePicker() {
        var picker = document.getElementById('theme-picker');
        if (!picker) return;

        picker.innerHTML = '';
        var currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';

        THEMES.forEach(function(theme) {
            var swatch = document.createElement('div');
            swatch.className = 'theme-swatch' + (theme.id === currentTheme ? ' active' : '') + (theme.image ? ' theme-swatch-photo' : '');
            if (theme.image) {
                swatch.style.backgroundImage = 'url(img/themes/' + theme.id.replace('midnight-city', 'midnightcity') + '.jpg)';
                swatch.style.backgroundSize = 'cover';
                swatch.style.backgroundPosition = 'center';
            } else {
                swatch.style.background = theme.bg;
            }
            swatch.style.color = theme.accent;
            swatch.style.borderColor = theme.id === currentTheme ? theme.accent : 'transparent';
            swatch.textContent = theme.name;
            swatch.dataset.theme = theme.id;
            swatch.addEventListener('click', function() {
                _applyTheme(theme.id);
                picker.querySelectorAll('.theme-swatch').forEach(function(s) {
                    s.classList.remove('active');
                    s.style.borderColor = 'transparent';
                });
                swatch.classList.add('active');
                swatch.style.borderColor = theme.accent;
            });
            picker.appendChild(swatch);
        });
    }

    function _applyTheme(themeId) {
        document.documentElement.setAttribute('data-theme', themeId);
        localStorage.setItem('theme', themeId);
        Bridge.call('set_setting', 'theme', themeId);
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

    function _initPathControls() {
        // Browse buttons for directory fields
        var browseMap = {
            'setting-steam-browse': { input: 'setting-steam-path', key: 'steam_path', label: 'Steam path' },
            'setting-applist-browse': { input: 'setting-applist-folder', key: 'applist_folder', label: 'AppList folder' },
            'setting-dlc-cache-browse': { input: 'setting-dlc-cache-dir', key: 'dlc_unlocker_cache', label: 'DLC cache directory' },
        };
        Object.keys(browseMap).forEach(function(btnId) {
            var btn = document.getElementById(btnId);
            if (btn) {
                btn.addEventListener('click', function() {
                    var cfg = browseMap[btnId];
                    Bridge.callSync('open_file_dialog', function(path) {
                        if (path) {
                            var input = document.getElementById(cfg.input);
                            if (input) input.value = path;
                            Bridge.call('set_setting', cfg.key, path);
                            Components.showToast('success', cfg.label + ' updated');
                        }
                    });
                });
            }
        });

        // Save buttons for API key fields
        var apiSaveMap = {
            'setting-hubcap-save': { input: 'setting-hubcap-key', key: 'morrenus_key', label: 'Hubcap API key', useConnect: true },
            'setting-steam-web-api-save': { input: 'setting-steam-web-api-key', key: 'steam_web_api_key', label: 'Steam Web API Key' },
            'setting-manifesthub-save': { input: 'setting-manifesthub-key', key: 'manifesthub_api_key', label: 'ManifestHub API Key' },
            'setting-ryuu-save': { input: 'setting-ryuu-key', key: 'ryuu_key', label: 'Ryuu API Key' },
        };
        Object.keys(apiSaveMap).forEach(function(btnId) {
            var btn = document.getElementById(btnId);
            if (btn) {
                btn.addEventListener('click', function() {
                    var cfg = apiSaveMap[btnId];
                    var input = document.getElementById(cfg.input);
                    var val = input ? input.value.trim() : '';
                    if (!val) { Components.showToast('warning', 'Please enter a value'); return; }
                    if (cfg.useConnect) {
                        Bridge.call('connect_store', val);
                    } else {
                        Bridge.call('set_setting', cfg.key, val);
                    }
                    Components.showToast('success', cfg.label + ' saved');
                });
            }
        });

        // Manifest excludes save
        var manifestExcludesSave = document.getElementById('setting-manifest-excludes-save');
        if (manifestExcludesSave) {
            manifestExcludesSave.addEventListener('click', function() {
                var val = (document.getElementById('setting-manifest-excludes') || {}).value || '';
                Bridge.call('set_setting', 'manifest_update_excludes', val.trim());
                Components.showToast('success', 'Manifest excludes saved');
            });
        }

        // AppList management buttons
        var applistClear = document.getElementById('applist-clear');
        var applistRebuild = document.getElementById('applist-rebuild');

        if (applistClear) {
            applistClear.addEventListener('click', function() {
                if (!confirm('Clear ALL IDs from the GreenLuma AppList folder? Game files and Steam library are untouched.')) return;
                Bridge.call('clear_applist');
                Components.showToast('info', 'Clearing AppList...');
            });
        }

        if (applistRebuild) {
            applistRebuild.addEventListener('click', function() {
                Bridge.call('rebuild_applist_from_installed');
                Components.showToast('info', 'Rebuilding AppList from installed games...');
            });
        }

        // Generic save buttons with data-key and data-input attributes
        document.querySelectorAll('.setting-save-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var key = this.dataset.key;
                var inputId = this.dataset.input;
                var input = document.getElementById(inputId);
                if (!input) return;
                var val = input.value.trim();
                if (!val) { Components.showToast('warning', 'Please enter a value'); return; }
                Bridge.call('set_setting', key, val);
                Components.showToast('success', 'Setting saved');
            });
        });
    }

    function _initProfileControls() {
        var switchBtn = document.getElementById('profile-switch');
        var saveBtn = document.getElementById('profile-save');
        var createBtn = document.getElementById('profile-create');
        var renameBtn = document.getElementById('profile-rename');
        var deleteBtn = document.getElementById('profile-delete');

        if (switchBtn) {
            switchBtn.addEventListener('click', function() {
                var select = document.getElementById('profile-select');
                var name = select ? select.value : '';
                if (!name) { Components.showToast('warning', 'Select a profile first'); return; }
                Bridge.call('switch_profile', name);
                Components.showToast('info', 'Switching to profile: ' + name);
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', function() {
                var name = prompt('Save current AppList as profile:');
                if (name) {
                    Bridge.call('save_profile', name);
                    Components.showToast('info', 'Saving profile: ' + name);
                    setTimeout(_loadProfiles, 500);
                }
            });
        }

        if (createBtn) {
            createBtn.addEventListener('click', function() {
                var name = prompt('New profile name:');
                if (name) {
                    Bridge.call('save_profile', name);
                    Components.showToast('success', 'Created profile: ' + name);
                    setTimeout(_loadProfiles, 500);
                }
            });
        }

        if (renameBtn) {
            renameBtn.addEventListener('click', function() {
                var select = document.getElementById('profile-select');
                var oldName = select ? select.value : '';
                if (!oldName) { Components.showToast('warning', 'Select a profile first'); return; }
                var newName = prompt('New name for "' + oldName + '":');
                if (newName && newName !== oldName) {
                    Bridge.call('rename_profile', oldName, newName);
                    Components.showToast('success', 'Renamed profile');
                    setTimeout(_loadProfiles, 500);
                }
            });
        }

        if (deleteBtn) {
            deleteBtn.addEventListener('click', function() {
                var select = document.getElementById('profile-select');
                var name = select ? select.value : '';
                if (!name) { Components.showToast('warning', 'Select a profile first'); return; }
                if (confirm('Delete profile "' + name + '"? This cannot be undone.')) {
                    Bridge.call('delete_profile', name);
                    Components.showToast('info', 'Deleted profile: ' + name);
                    setTimeout(_loadProfiles, 500);
                }
            });
        }
    }

    function _initAutoBackupControls() {
        // Provider chip selection
        var chips = document.querySelectorAll('.autobackup-chip');
        chips.forEach(function(chip) {
            chip.addEventListener('click', function() {
                chips.forEach(function(c) { c.classList.remove('active'); });
                chip.classList.add('active');
                _showAutoBackupPanel(chip.dataset.provider);
            });
        });

        // Browse button for local folder
        var browseBtn = document.getElementById('setting-autobackup-local-browse');
        if (browseBtn) {
            browseBtn.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var inp = document.getElementById('setting-autobackup-local-dest');
                        if (inp) inp.value = path;
                    }
                });
            });
        }

        // Load Remotes button for rclone
        var loadBtn = document.getElementById('setting-autobackup-rclone-loadremotes');
        if (loadBtn) {
            loadBtn.addEventListener('click', function() {
                loadBtn.disabled = true;
                loadBtn.textContent = 'Loading...';
                Bridge.call('rclone_list_remotes', JSON.stringify({ rclone_exe: '' }));
            });
        }

        // Interval input — save on change, timer restarts live via _apply_setting_live
        var intervalInp = document.getElementById('setting-autobackup-interval');
        if (intervalInp) {
            intervalInp.addEventListener('change', function() {
                var val = this.value.trim();
                Bridge.call('set_setting', 'save_watcher_interval', val || '0');
            });
        }

        // Save button
        var saveBtn = document.getElementById('setting-autobackup-save');
        if (saveBtn) {
            saveBtn.addEventListener('click', function() {
                var activeChip = document.querySelector('.autobackup-chip.active');
                var provider = activeChip ? activeChip.dataset.provider : 'local';
                var cfg = { provider: provider };
                if (provider === 'local') {
                    var dest = (document.getElementById('setting-autobackup-local-dest') || {}).value || '';
                    if (!dest) { Components.showToast('warning', 'Select a destination folder first'); return; }
                    cfg.dest_path = dest;
                } else if (provider === 'rclone') {
                    var remote = (document.getElementById('setting-autobackup-rclone-dest') || {}).value || '';
                    if (!remote) { Components.showToast('warning', 'Enter a remote destination first'); return; }
                    cfg.rclone_exe = '';
                    cfg.remote_dest = remote;
                }
                Bridge.call('set_setting', 'last_backup_provider_config', JSON.stringify(cfg));
                Components.showToast('success', 'Auto backup settings saved');
            });
        }

        // Handle rclone_list_remotes result for the Auto Backup datalist
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'rclone_list_remotes') {
                    var btn = document.getElementById('setting-autobackup-rclone-loadremotes');
                    if (btn) { btn.disabled = false; btn.textContent = 'Load Remotes'; }
                    if (data.success && data.remotes) {
                        var dl = document.getElementById('autobackup-rclone-datalist');
                        if (dl) {
                            dl.innerHTML = '';
                            data.remotes.forEach(function(r) {
                                var opt = document.createElement('option');
                                opt.value = r.name + ':';
                                dl.appendChild(opt);
                            });
                        }
                    }
                }
            } catch(e) {}
        });
    }

    function _showAutoBackupPanel(provider) {
        var local  = document.getElementById('autobackup-local-panel');
        var rclone = document.getElementById('autobackup-rclone-panel');
        var gdrive = document.getElementById('autobackup-gdrive-panel');
        if (local)  local.classList.toggle('hidden',  provider !== 'local');
        if (rclone) rclone.classList.toggle('hidden', provider !== 'rclone');
        if (gdrive) gdrive.classList.toggle('hidden', provider !== 'gdrive_api');
    }

    function _initAboutLinks() {
        var githubLink = document.getElementById('about-github');
        var updateLink = document.getElementById('about-update');

        if (githubLink) {
            githubLink.addEventListener('click', function(e) {
                e.preventDefault();
                Bridge.call('open_url', 'https://github.com/Midrags/SFF');
            });
        }

        if (updateLink) {
            updateLink.addEventListener('click', function(e) {
                e.preventDefault();
                Bridge.call('run_game_action', '', 'check_updates');
            });
        }
    }

    function _initAppListActions() {
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'applist_cleared') {
                    if (data.success) {
                        Components.showToast('success', 'AppList cleared — ' + data.count + ' IDs removed');
                    } else {
                        Components.showToast('error', 'AppList clear failed: ' + data.message);
                    }
                } else if (data.task === 'applist_rebuilt') {
                    if (data.success) {
                        Components.showToast('success', 'AppList rebuilt — ' + data.count + ' installed games added');
                    } else {
                        Components.showToast('error', 'AppList rebuild failed: ' + data.message);
                    }
                }
            } catch(e) {}
        });
    }

    function _initPreferenceControls() {
        // Dropdown selects
        var dropdowns = {
            'setting-language': 'language',
            'setting-gl-version': 'greenluma_version',
        };
        Object.keys(dropdowns).forEach(function(id) {
            var el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', function() {
                    Bridge.call('set_setting', dropdowns[id], this.value);
                    if (id === 'setting-language') {
                        if (window.I18n) I18n.applyLanguage(this.value);
                        Components.showToast('success', 'Language updated');
                    } else {
                        Components.showToast('success', 'Setting updated');
                    }
                });
            }
        });

        // Number inputs
        var numbers = {
            'setting-id-limit': 'applist_id_limit',
            'setting-parallel-workers': 'parallel_downloads',
            'setting-backup-retention': 'backup_retention',
        };
        Object.keys(numbers).forEach(function(id) {
            var el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', function() {
                    Bridge.call('set_setting', numbers[id], this.value);
                });
            }
        });

        // Checkbox toggles
        var checkboxes = {
            'setting-notifications': 'enable_notifications',
            'setting-parallel': 'use_parallel_downloads',
            'setting-music': 'play_music',
            'setting-advanced-mode': 'advanced_mode',
            'setting-track-ach': 'gl_track_ach',
            'setting-use-smokeapi': 'use_smokeapi',
            'setting-hide-store-images': 'hide_store_images',
        };
        Object.keys(checkboxes).forEach(function(id) {
            var el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', function() {
                    var val = this.checked ? 'True' : 'False';
                    Bridge.call('set_setting', checkboxes[id], val);
                });
            }
        });

        // Sync hide-store-images flag to Components immediately on change
        var hideImagesEl = document.getElementById('setting-hide-store-images');
        if (hideImagesEl) {
            hideImagesEl.addEventListener('change', function() {
                Components.setHideImages(this.checked);
            });
        }
    }

    function _loadCurrentSettings() {
        Bridge.callSync('get_all_settings', function(json) {
            try {
                var settings = JSON.parse(json || '{}');
                // Text inputs
                _setInputVal('setting-steam-path', settings.steam_path);
                _setInputVal('setting-steam-user', settings.steam_user);
                _setInputVal('setting-steam32-id', settings.steam32_id);
                _setInputVal('setting-onlinefix-user', settings.online_fix_user);
                _setInputVal('setting-applist-folder', settings.applist_folder);
                _setInputVal('setting-dlc-cache-dir', settings.dlc_unlocker_cache);
                // Password fields — only set placeholder text for encrypted values
                _setPasswordField('setting-hubcap-key', settings.morrenus_key);
                _setPasswordField('setting-ryuu-key', settings.ryuu_key);
                _setPasswordField('setting-steam-pass', settings.steam_pass);
                _setPasswordField('setting-onlinefix-pass', settings.online_fix_pass);
                _setPasswordField('setting-steam-web-api-key', settings.steam_web_api_key);
                _setPasswordField('setting-manifesthub-key', settings.manifesthub_api_key);
                // Selects
                _setSelectVal('setting-language', settings.language || 'en');
                _setSelectVal('setting-gl-version', settings.greenluma_version || 'GL2025');
                // Number inputs
                _setInputVal('setting-id-limit', settings.applist_id_limit || '0');
                _setInputVal('setting-parallel-workers', settings.parallel_downloads || '5');
                _setInputVal('setting-backup-retention', settings.backup_retention || '4');
                _setInputVal('setting-manifest-excludes', settings.manifest_update_excludes || '');
                // Auto Backup
                _setInputVal('setting-autobackup-interval', settings.save_watcher_interval || '10');
                try {
                    if (settings.last_backup_provider_config) {
                        var abCfg = JSON.parse(settings.last_backup_provider_config);
                        var prov = abCfg.provider || 'local';
                        document.querySelectorAll('.autobackup-chip').forEach(function(c) {
                            c.classList.toggle('active', c.dataset.provider === prov);
                        });
                        _showAutoBackupPanel(prov);
                        if (prov === 'local' && abCfg.dest_path) {
                            _setInputVal('setting-autobackup-local-dest', abCfg.dest_path);
                        } else if (prov === 'rclone' && abCfg.remote_dest) {
                            _setInputVal('setting-autobackup-rclone-dest', abCfg.remote_dest);
                        }
                    }
                } catch(e) {}
                // Checkboxes
                _setCheckbox('setting-notifications', settings.enable_notifications);
                _setCheckbox('setting-parallel', settings.use_parallel_downloads);
                _setCheckbox('setting-music', settings.play_music);
                _setCheckbox('setting-advanced-mode', settings.advanced_mode);
                _setCheckbox('setting-track-ach', settings.gl_track_ach);
                _setCheckbox('setting-use-smokeapi', settings.use_smokeapi);
                _setCheckbox('setting-hide-store-images', settings.hide_store_images);
                Components.setHideImages(settings.hide_store_images === 'True');
                // Theme
                if (settings.theme) _applyTheme(settings.theme);
            } catch(e) {
                // Fallback: load just steam_path and theme
                Bridge.callWithCallback('get_setting', 'steam_path', function(val) {
                    if (val) _setInputVal('setting-steam-path', val);
                });
            }
        });
    }

    function _setInputVal(id, val) {
        var el = document.getElementById(id);
        if (el && val && val !== '[ENCRYPTED]') el.value = val;
    }

    function _setPasswordField(id, val) {
        var el = document.getElementById(id);
        if (!el) return;
        if (val === '[ENCRYPTED]') {
            el.placeholder = '(encrypted - saved)';
            el.value = '';
        } else if (val) {
            el.value = val;
        }
    }

    function _setSelectVal(id, val) {
        var el = document.getElementById(id);
        if (el && val) {
            el.value = val;
            el.dispatchEvent(new Event('input'));
        }
    }

    function _setCheckbox(id, val) {
        var el = document.getElementById(id);
        if (!el) return;
        el.checked = (val === 'True' || val === 'true' || val === true);
    }

    function _loadProfiles() {
        Bridge.callSync('list_profiles', function(json) {
            try {
                var profiles = JSON.parse(json || '[]');
                var select = document.getElementById('profile-select');
                if (select) {
                    var current = select.value;
                    select.innerHTML = '<option value="">-- Select profile --</option>';
                    profiles.forEach(function(name) {
                        var opt = document.createElement('option');
                        opt.value = name;
                        opt.textContent = name;
                        select.appendChild(opt);
                    });
                    if (current) select.value = current;
                }
            } catch(e) {}
        });
    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
