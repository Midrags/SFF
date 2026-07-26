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
        _initPreferenceControls();
        _initAutoBackupControls();
        _initAboutLinks();
        _initAvatarControls();
        _initCustomAppearanceControls();
        _initSettingsBackupControls();
    }

    function onPageEnter() {
        init();
        _loadCurrentSettings();
        _loadCurrentAvatar();
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
        Bridge.callWithCallback('get_setting', 'custom_background_image', function(bgPath) {
            if (bgPath) {
                Bridge.callWithCallback('get_setting', 'custom_accent_color', function(accent) {
                    if (window.App && App.applyCustomAppearance) {
                        App.applyCustomAppearance(bgPath, accent || '');
                    }
                });
            }
        });
    }

    function _initPathControls() {
        // Browse buttons for directory fields
        var browseMap = {
            'setting-steam-browse': { input: 'setting-steam-path', key: 'steam_path', label: 'Steam path' },
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
            'setting-ryuu-save': { input: 'setting-ryuu-key', label: 'Ryuu Reseller Key', useRyuuConnect: true },
            'setting-ryuu-api-save': { input: 'setting-ryuu-api-key', key: 'ryuu_api_key', label: 'Ryuu Premium API Key' },
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
                    } else if (cfg.useRyuuConnect) {
                        Bridge.call('save_ryuu_key', val);
                        setTimeout(function() { Bridge.call('test_ryuu_key'); }, 500);
                    } else {
                        Bridge.call('set_setting', cfg.key, val);
                    }
                    Components.showToast('success', cfg.label + ' saved');
                });
            }
        });

        // Test Ryuu Key — probes the test/refresh endpoint with appid=440.
        // Result lands in the existing task_finished signal handler below.
        var ryuuTestBtn = document.getElementById('setting-ryuu-test');
        if (ryuuTestBtn) {
            ryuuTestBtn.addEventListener('click', function() {
                if (ryuuTestBtn.disabled) return;
                ryuuTestBtn.disabled = true;
                if (!ryuuTestBtn.dataset.originalText) {
                    ryuuTestBtn.dataset.originalText = ryuuTestBtn.textContent;
                }
                ryuuTestBtn.textContent = 'Testing...';
                Bridge.call('test_ryuu_key');
            });
        }

        // Test Ryuu Premium Key
        var ryuuApiTestBtn = document.getElementById('setting-ryuu-api-test');
        if (ryuuApiTestBtn) {
            ryuuApiTestBtn.addEventListener('click', function() {
                if (ryuuApiTestBtn.disabled) return;
                ryuuApiTestBtn.disabled = true;
                if (!ryuuApiTestBtn.dataset.originalText) {
                    ryuuApiTestBtn.dataset.originalText = ryuuApiTestBtn.textContent;
                }
                ryuuApiTestBtn.textContent = 'Testing...';
                Bridge.call('test_ryuu_api_key');
            });
        }

        // Manifest excludes save
        var manifestExcludesSave = document.getElementById('setting-manifest-excludes-save');
        if (manifestExcludesSave) {
            manifestExcludesSave.addEventListener('click', function() {
                var val = (document.getElementById('setting-manifest-excludes') || {}).value || '';
                Bridge.call('set_setting', 'manifest_update_excludes', val.trim());
                Components.showToast('success', 'Manifest excludes saved');
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
                } else if (data.task === 'test_ryuu_key') {
                    var rbtn = document.getElementById('setting-ryuu-test');
                    if (rbtn) {
                        rbtn.disabled = false;
                        rbtn.textContent = rbtn.dataset.originalText || 'Test Ryuu Key';
                    }
                    if (data.ok) {
                        Components.showToast('success', 'Ryuu key works (200 OK)');
                    } else if (data.reason === 'no_api_key') {
                        Components.showToast('warning', 'No Ryuu API key configured');
                    } else if (data.reason === 'appid not in db') {
                        Components.showToast('warning', 'Ryuu key accepted but appid 440 not in db');
                    } else if (data.error) {
                        Components.showToast('error', 'Ryuu test failed: ' + data.error);
                    } else {
                        var bodySnippet = (data.body || '').slice(0, 200);
                        Components.showToast(
                            'error',
                            'Ryuu rejected: ' + (data.status || '?') +
                            (bodySnippet ? ' — ' + bodySnippet : '')
                        );
                    }
                } else if (data.task === 'test_ryuu_api_key') {
                    var rbtn2 = document.getElementById('setting-ryuu-api-test');
                    if (rbtn2) {
                        rbtn2.disabled = false;
                        rbtn2.textContent = rbtn2.dataset.originalText || 'Test Premium Key';
                    }
                    if (data.ok) {
                        Components.showToast('success', 'Ryuu premium key works (200 OK)');
                    } else if (data.reason === 'no_api_key') {
                        Components.showToast('warning', 'No Ryuu premium API key configured');
                    } else if (data.error) {
                        Components.showToast('error', 'Ryuu premium test failed: ' + data.error);
                    } else {
                        Components.showToast('error', 'Ryuu premium rejected: ' + (data.status || '?'));
                    }
                } else if (data.task === 'app_update') {
                    var upBtn = document.getElementById('about-update');
                    if (data.status === 'downloading') {
                        if (upBtn) { upBtn.disabled = true; upBtn.innerHTML = data.progress + '%'; }
                    } else if (data.status === 'installing') {
                        if (upBtn) upBtn.innerHTML = 'Installing...';
                    } else {
                        if (upBtn) { upBtn.disabled = false; upBtn.innerHTML = 'Update'; }
                        Components.showToast(data.success ? 'success' : 'error', data.message || '');
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
        var versionLabel = document.getElementById('settings-version-label');

        function resetUpdateButton() {
            if (!updateLink) return;
            updateLink.disabled = false;
            if (updateLink.dataset.originalHtml) {
                updateLink.innerHTML = updateLink.dataset.originalHtml;
                delete updateLink.dataset.originalHtml;
            }
        }

        if (githubLink) {
            githubLink.addEventListener('click', function(e) {
                e.preventDefault();
                Bridge.call('open_url', 'https://github.com/Midrags/SFF');
            });
        }

        if (updateLink) {
            updateLink.addEventListener('click', function(e) {
                e.preventDefault();
                // Block double-fires while a check is in flight.
                if (updateLink.disabled) return;
                // Stash original markup so app.js task_finished can restore it.
                if (!updateLink.dataset.originalHtml) {
                    updateLink.dataset.originalHtml = updateLink.innerHTML;
                }
                updateLink.innerHTML = '<svg class="spinner" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="42 16" stroke-linecap="round"></circle></svg>';
                updateLink.disabled = true;
                Bridge.callWithCallback('app_update_check', '', function(json) {
                    var data;
                    try { data = JSON.parse(json || '{}'); } catch(err) { data = null; }
                    if (!data || !data.ok) {
                        resetUpdateButton();
                        Components.showToast('error', (data && data.message) || 'Could not check for updates.');
                        return;
                    }
                    if (!data.update_available) {
                        resetUpdateButton();
                        Components.showToast('success', 'SteaMidra is already up to date.');
                        return;
                    }
                    Components.showToast('info', 'Update available: ' + (data.latest || 'new release'));
                    Bridge.call('run_game_action', '', 'check_updates');
                });
            });
        }

        if (versionLabel) {
            Bridge.callSync('get_app_version', function(ver) {
                versionLabel.textContent = ver || '';
            });
        }
    }

    function _initPreferenceControls() {
        // Dropdown selects
        var dropdowns = {
            'setting-language': 'language',
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
            'setting-download-concurrency': 'download_concurrency',
            'setting-parallel-workers': 'parallel_downloads',
            'setting-backup-retention': 'backup_retention',
            'setting-live-log-lines': 'live_log_max_lines',
        };
        Object.keys(numbers).forEach(function(id) {
            var el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', function() {
                    Bridge.call('set_setting', numbers[id], this.value);
                    if (id === 'setting-live-log-lines') {
                        window.dispatchEvent(new CustomEvent('live-log-limit-changed', { detail: this.value }));
                    }
                });
            }
        });

        // Checkbox toggles
        var checkboxes = {
            'setting-notifications': 'enable_notifications',
            'setting-parallel': 'use_parallel_downloads',
            'setting-music': 'play_music',
            'setting-advanced-mode': 'advanced_mode',
            'setting-use-smokeapi': 'use_smokeapi',
            'setting-hide-store-images': 'hide_store_images',
            'setting-auto-update-check': 'auto_update_check',
            'setting-close-to-tray': 'close_to_tray',
            'setting-manifest-preserve': 'manifest_preserve',
            'setting-store-show-software': 'store_show_software',
            'setting-block-nsfw': 'store_block_nsfw',
            'setting-auto-enable-new-game-updates': 'auto_enable_updates_new_games',
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

    function _loadCurrentAvatar() {
        Bridge.callSync('get_avatar_base64', function(dataUrl) {
            var img = document.getElementById('avatar-preview');
            var ph = document.getElementById('avatar-placeholder');
            if (!img) return;
            if (dataUrl && dataUrl.indexOf('data:') === 0) {
                img.src = dataUrl;
                img.style.display = '';
                if (ph) ph.style.display = 'none';
            } else {
                img.style.display = 'none';
                if (ph) ph.style.display = '';
            }
        });
    }

    function _initAvatarControls() {
        var browseBtn = document.getElementById('setting-avatar-browse');
        var applyBtn = document.getElementById('setting-avatar-apply');
        var pathInput = document.getElementById('setting-avatar-path');
        if (browseBtn) {
            browseBtn.addEventListener('click', function() {
                Bridge.callSync('browse_image_file', function(path) {
                    if (path) {
                        if (pathInput) pathInput.value = path;
                        var img = document.getElementById('avatar-preview');
                        var ph = document.getElementById('avatar-placeholder');
                        if (img) {
                            img.src = 'file:///' + path.replace(/\\/g, '/');
                            img.style.display = '';
                            if (ph) ph.style.display = 'none';
                        }
                    }
                });
            });
        }
        if (applyBtn) {
            applyBtn.addEventListener('click', function() {
                var path = pathInput ? pathInput.value.trim() : '';
                if (!path) { Components.showToast('warning', 'Browse for an avatar first'); return; }
                Bridge.callWithCallback('set_global_avatar', path, function(result) {
                    if (result === 'ok') {
                        Components.showToast('success', 'Avatar applied globally');
                        _loadCurrentAvatar();
                    } else {
                        Components.showToast('error', result || 'Failed to apply avatar');
                    }
                });
            });
        }
    }

    function _initCustomAppearanceControls() {
        var bgInput = document.getElementById('setting-custom-background');
        var browseBtn = document.getElementById('setting-custom-background-browse');
        var clearBtn = document.getElementById('setting-custom-background-clear');
        var accentInput = document.getElementById('setting-custom-accent');
        var accentSave = document.getElementById('setting-custom-accent-save');
        var accentClear = document.getElementById('setting-custom-accent-clear');

        if (browseBtn) {
            browseBtn.addEventListener('click', function() {
                Bridge.callSync('browse_custom_background_file', function(path) {
                    if (!path) return;
                    Bridge.callWithCallback('set_custom_background', path, function(json) {
                        var result = {};
                        try { result = JSON.parse(json || '{}'); } catch(e) {}
                        if (!result.ok) {
                            Components.showToast('error', result.error || 'Background update failed');
                            return;
                        }
                        if (bgInput) bgInput.value = result.path || path;
                        if (window.App && App.applyCustomAppearance) {
                            App.applyCustomAppearance(result.path || path, accentInput ? accentInput.value : '');
                        }
                        Components.showToast('success', 'Background updated');
                    });
                });
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                Bridge.callWithCallback('clear_custom_background', function(json) {
                    var result = {};
                    try { result = JSON.parse(json || '{}'); } catch(e) {}
                    if (!result.ok) {
                        Components.showToast('error', result.error || 'Could not clear background');
                        return;
                    }
                    if (bgInput) bgInput.value = '';
                    var themeId = document.documentElement.getAttribute('data-theme') || 'dark';
                    _applyTheme(themeId);
                    Components.showToast('success', 'Background cleared');
                });
            });
        }

        if (accentSave && accentInput) {
            accentSave.addEventListener('click', function() {
                var color = accentInput.value || '';
                if (!/^#[0-9a-fA-F]{6}$/.test(color)) {
                    Components.showToast('warning', 'Pick a valid accent color');
                    return;
                }
                Bridge.call('set_setting', 'custom_accent_color', color);
                if (window.App && App.applyCustomAppearance) {
                    App.applyCustomAppearance(bgInput ? bgInput.value : '', color);
                }
                Components.showToast('success', 'Accent saved');
            });
        }

        if (accentClear && accentInput) {
            accentClear.addEventListener('click', function() {
                Bridge.call('set_setting', 'custom_accent_color', '');
                document.documentElement.style.removeProperty('--accent');
                document.documentElement.style.removeProperty('--sidebar-active');
                accentInput.value = '#4a9eff';
                Components.showToast('success', 'Accent reset');
            });
        }
    }

    function _initSettingsBackupControls() {
        var exportBtn = document.getElementById('settings-export-file');
        var importBtn = document.getElementById('settings-import-file');

        if (exportBtn) {
            exportBtn.addEventListener('click', function() {
                Bridge.callWithCallback('export_settings_file', function(json) {
                    var result = {};
                    try { result = JSON.parse(json || '{}'); } catch(e) {}
                    if (result.cancelled) return;
                    if (!result.ok) {
                        Components.showToast('error', result.message || 'Settings export failed');
                        return;
                    }
                    Components.showToast('success', 'Settings exported');
                });
            });
        }

        if (importBtn) {
            importBtn.addEventListener('click', function() {
                if (!window.confirm('Importing settings will overwrite matching current settings. Continue?')) {
                    return;
                }
                Bridge.callWithCallback('import_settings_file', function(json) {
                    var result = {};
                    try { result = JSON.parse(json || '{}'); } catch(e) {}
                    if (result.cancelled) return;
                    if (!result.ok) {
                        Components.showToast('error', result.message || 'Settings import failed');
                        return;
                    }
                    _loadCurrentSettings();
                    Components.showToast('success', result.message || 'Settings imported');
                });
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
                _setInputVal('setting-dlc-cache-dir', settings.dlc_unlocker_cache);
                // Password fields — only set placeholder text for encrypted values
                _setPasswordField('setting-hubcap-key', settings.morrenus_key);
                _setPasswordField('setting-ryuu-key', settings.ryuu_key);
                _setPasswordField('setting-ryuu-api-key', settings.ryuu_api_key);
                _setPasswordField('setting-steam-pass', settings.steam_pass);
                _setPasswordField('setting-steam-web-api-key', settings.steam_web_api_key);
                _setPasswordField('setting-manifesthub-key', settings.manifesthub_api_key);
                // Selects
                _setSelectVal('setting-language', settings.language || 'en');
                // Number inputs
                _setInputVal('setting-download-concurrency', settings.download_concurrency || '32');
                _setInputVal('setting-parallel-workers', settings.parallel_downloads || '5');
                _setInputVal('setting-backup-retention', settings.backup_retention || '4');
                _setInputVal('setting-live-log-lines', settings.live_log_max_lines || '100');
                _setInputVal('setting-manifest-excludes', settings.manifest_update_excludes || '');
                _setInputVal('setting-custom-background', settings.custom_background_image || '');
                if (settings.custom_accent_color && /^#[0-9a-fA-F]{6}$/.test(settings.custom_accent_color)) {
                    _setInputVal('setting-custom-accent', settings.custom_accent_color);
                }
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
                _setCheckbox('setting-use-smokeapi', settings.use_smokeapi);
                _setCheckbox('setting-hide-store-images', settings.hide_store_images);
                Components.setHideImages(settings.hide_store_images === 'True');
                // A9: default ON unless explicitly stored as False
                var autoUpd = settings.auto_update_check;
                _setCheckbox('setting-auto-update-check', (autoUpd === '' || autoUpd === undefined) ? 'True' : autoUpd);
                // 6.2.4 hotfix: default ON unless explicitly stored as
                // False. Tray behaviour matches the manifest_preserve
                // / auto_update_check pattern. Users who want X = quit
                // can flip it off; everyone else gets close-to-tray.
                var closeToTray = settings.close_to_tray;
                _setCheckbox(
                    'setting-close-to-tray',
                    (closeToTray === '' || closeToTray === undefined)
                        ? 'True'
                        : closeToTray
                );
                // A15: default ON unless explicitly stored as False, mirroring auto_update_check.
                var manifestPreserve = settings.manifest_preserve;
                _setCheckbox(
                    'setting-manifest-preserve',
                    (manifestPreserve === '' || manifestPreserve === undefined)
                        ? 'True'
                        : manifestPreserve
                );
                // A17: default ON unless explicitly stored as False, mirroring auto_update_check.
                var storeShowSoftware = settings.store_show_software;
                _setCheckbox(
                    'setting-store-show-software',
                    (storeShowSoftware === '' || storeShowSoftware === undefined)
                        ? 'True'
                        : storeShowSoftware
                );
                var blockNsfw = settings.store_block_nsfw;
                _setCheckbox(
                    'setting-block-nsfw',
                    (blockNsfw === '' || blockNsfw === undefined)
                        ? 'True'
                        : blockNsfw
                );
                _setCheckbox('setting-auto-enable-new-game-updates', settings.auto_enable_updates_new_games);
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

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
