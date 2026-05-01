/**
 * SteaMidra — Tools Page
 * GBE Token Generator, VDF Key Extractor, Workshop Browser
 */

window.Tools = (function() {
    'use strict';

    var _initialized = false;

    function init() {
        if (_initialized) return;
        _initialized = true;

        // GBE Token Generator
        var gbeBrowse = document.getElementById('tool-gbe-browse');
        var gbeGenerate = document.getElementById('tool-gbe-generate');

        if (gbeBrowse) {
            gbeBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var input = document.getElementById('tool-gbe-outdir');
                        if (input) input.value = path;
                    }
                });
            });
        }

        if (gbeGenerate) {
            gbeGenerate.addEventListener('click', function() {
                var apiKey = document.getElementById('tool-gbe-apikey');
                var appId = document.getElementById('tool-gbe-appid');
                var outDir = document.getElementById('tool-gbe-outdir');

                if (!apiKey || !apiKey.value.trim()) {
                    Components.showToast('warning', 'Please enter a Steam Web API key');
                    return;
                }
                if (!appId || !appId.value.trim()) {
                    Components.showToast('warning', 'Please enter an App ID');
                    return;
                }

                var config = {
                    api_key: apiKey.value.trim(),
                    app_id: appId.value.trim(),
                    output_dir: outDir ? outDir.value.trim() : ''
                };

                Components.showToast('info', 'Generating GBE token...');
                Bridge.call('generate_gbe_token', JSON.stringify(config));
            });
        }

        // VDF Key Extractor
        var vdfBrowse = document.getElementById('tool-vdf-browse');
        var vdfExtract = document.getElementById('tool-vdf-extract');

        if (vdfBrowse) {
            vdfBrowse.addEventListener('click', function() {
                Bridge.callSync('open_file_dialog', function(path) {
                    if (path) {
                        var input = document.getElementById('tool-vdf-path');
                        if (input) input.value = path;
                    }
                });
            });
        }

        if (vdfExtract) {
            vdfExtract.addEventListener('click', function() {
                var pathInput = document.getElementById('tool-vdf-path');
                var path = pathInput ? pathInput.value.trim() : '';

                Components.showToast('info', 'Extracting VDF keys...');
                Bridge.callWithCallback('extract_vdf_keys', path, function(json) {
                    try {
                        var keys = JSON.parse(json || '[]');
                        _renderVdfTable(keys);
                    } catch(e) {
                        Components.showToast('error', 'Failed to parse VDF keys');
                    }
                });
            });
        }

        // Listen for GBE token generation result
        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task === 'generate_gbe_token') {
                    var logContent = document.getElementById('tool-gbe-log-content');
                    var logOutput = document.getElementById('tool-gbe-log');
                    if (logContent && data.log) {
                        logContent.textContent = data.log;
                        if (logOutput) logOutput.classList.remove('hidden');
                    }
                }
            } catch(e) {}
        });

        // Workshop Browser
        var workshopOpen = document.getElementById('tool-workshop-open');
        if (workshopOpen) {
            workshopOpen.addEventListener('click', function() {
                var appIdInput = document.getElementById('tool-workshop-appid');
                var appId = appIdInput ? appIdInput.value.trim() : '';
                if (!appId) {
                    Components.showToast('warning', 'Please enter an App ID');
                    return;
                }
                Bridge.call('open_workshop', appId);
            });
        }
    }

    function _renderVdfTable(keys) {
        var tableDiv = document.getElementById('tool-vdf-table');
        var tbody = document.getElementById('tool-vdf-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        keys.forEach(function(entry) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + Components.escapeHtml(String(entry.app_id || '')) + '</td>' +
                '<td>' + Components.escapeHtml(String(entry.depot_id || '')) + '</td>' +
                '<td><code>' + Components.escapeHtml(String(entry.key || '')) + '</code></td>';
            tbody.appendChild(tr);
        });

        if (tableDiv) tableDiv.classList.remove('hidden');
        Components.showToast('success', 'Extracted ' + keys.length + ' keys');
    }

    function onPageEnter() {
        init();
        var apiKeyInput = document.getElementById('tool-gbe-apikey');
        if (apiKeyInput && !apiKeyInput.value) {
            Bridge.callWithCallback('get_setting', 'steam_web_api_key', function(val) {
                if (val && val !== '[ENCRYPTED]' && apiKeyInput && !apiKeyInput.value) {
                    apiKeyInput.value = val;
                }
            });
        }
    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
