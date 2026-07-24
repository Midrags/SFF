// SteaMidra - Steam game setup and manifest tool (SFF)
// Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
//
// This file is part of SteaMidra.
//
// SteaMidra is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// SteaMidra is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

// DLC check modal — renders the structured payload emitted by
// `WebBridge.dlc_check_get_list`. Replaces the old run_game_action
// path that piped Rich console tables into a stdout the Web UI
// never displayed.
(function () {
    'use strict';

    var _initialized = false;
    var _currentAppId = '';

    function _escape(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function _setLoading(text) {
        var body = document.getElementById('dlc-check-body');
        if (!body) return;
        body.innerHTML =
            '<div class="dlc-check-loading">' +
            '<svg class="spinner" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
            '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="42 16" stroke-linecap="round"></circle></svg>' +
            '<span>' + _escape(text) + '</span>' +
            '</div>';
    }

    function _renderEmpty(message) {
        var body = document.getElementById('dlc-check-body');
        if (!body) return;
        body.innerHTML = '<p class="dlc-check-empty">' + _escape(message) + '</p>';
    }

    function _renderError(message) {
        var body = document.getElementById('dlc-check-body');
        if (!body) return;
        body.innerHTML =
            '<p class="dlc-check-error">' + _escape(message) + '</p>';
    }

    function _renderList(payload) {
        var body = document.getElementById('dlc-check-body');
        var summary = document.getElementById('dlc-check-summary');
        if (!body) return;

        var dlcs = payload.dlcs || [];
        if (!dlcs.length) {
            _renderEmpty('No DLCs found for this game.');
            if (summary) summary.textContent = '';
            return;
        }

        if (summary) {
            var owned = payload.owned_count || 0;
            var total = payload.total_count || dlcs.length;
            summary.textContent = owned + ' of ' + total + ' unlocked';
        }

        var rows = dlcs.map(function (dlc) {
            var status = dlc.in_applist
                ? '<span class="dlc-status dlc-status-ok">Unlocked</span>'
                : '<span class="dlc-status dlc-status-missing">Missing</span>';
            var keyTag = '';
            if (dlc.type === 'depot') {
                keyTag = dlc.has_key
                    ? ' <span class="dlc-tag dlc-tag-ok" title="Decryption key present in config.vdf">key</span>'
                    : ' <span class="dlc-tag dlc-tag-warn" title="Decryption key missing — depot won\'t decrypt">no key</span>';
            }
            var typeTag = dlc.type === 'depot'
                ? '<span class="dlc-tag">depot</span>'
                : '<span class="dlc-tag">app id</span>';
            // Checkbox per DLC. Default: only missing rows are checked
            // and unlocked rows are pre-skipped. Depots are disabled
            // because the bulk providers can't ship them as standalone.
            var disabled = (dlc.type === 'depot') ? 'disabled' : '';
            var checked = (!dlc.in_applist && dlc.type !== 'depot') ? 'checked' : '';
            var cb = '<input type="checkbox" class="dlc-row-cb" data-appid="' + _escape(dlc.id) + '" ' + checked + ' ' + disabled + '>';
            return (
                '<tr>' +
                '<td>' + cb + '</td>' +
                '<td>' + status + '</td>' +
                '<td class="dlc-id">' + _escape(dlc.id) + '</td>' +
                '<td>' + _escape(dlc.name) + '</td>' +
                '<td>' + typeTag + keyTag + '</td>' +
                '</tr>'
            );
        }).join('');

        body.innerHTML =
            '<table class="dlc-check-table">' +
            '<thead><tr>' +
            '<th><input type="checkbox" id="dlc-check-all" checked title="Toggle all"></th>' +
            '<th>Status</th><th>App ID</th><th>Name</th><th>Type</th>' +
            '</tr></thead>' +
            '<tbody>' + rows + '</tbody>' +
            '</table>';

        // Header checkbox toggles every row checkbox at once. Disabled
        // depot rows stay disabled, the "select all" only flips the
        // ones the user can act on.
        var allCb = document.getElementById('dlc-check-all');
        if (allCb) {
            allCb.addEventListener('change', function () {
                body.querySelectorAll('.dlc-row-cb:not(:disabled)').forEach(function (cb) {
                    cb.checked = allCb.checked;
                });
            });
        }

        // Provider buttons in the footer route the CHECKED rows.
        //   * hubcap / ryuu  -> single download_game_with_source(parent)
        //                       call. Both providers only ship the full
        //                       parent zip so we hand them the parent appid
        //                       and let them pull every DLC in one go.
        //   * oureveryday    -> per-checked-DLC manifest+key append against
        //                       the parent's existing lua. Loops only over
        //                       what the user actually checked.
        //   * local          -> opens the manifest-folder picker and runs
        //                       the same DDMod local-files flow the Store
        //                       tab uses, scoped to the checked DLC list.
        var bulk = document.getElementById('dlc-check-bulk-actions');
        if (bulk) {
            bulk.style.display = 'flex';
            bulk.querySelectorAll('.dlc-bulk-dl').forEach(function (btn) {
                btn.onclick = function () {
                    var src = this.dataset.source || 'oureveryday';
                    if (!_currentAppId) {
                        Components.showToast('warning', 'Parent app id missing.');
                        return;
                    }
                    var checkedIds = [];
                    body.querySelectorAll('.dlc-row-cb:checked').forEach(function (cb) {
                        if (cb.dataset.appid) checkedIds.push(String(cb.dataset.appid));
                    });
                    if (src === 'hubcap' || src === 'ryuu') {
                        Components.showToast('info',
                            'Queueing parent app (' + _currentAppId + ') through ' + src +
                            ' — DLCs come with the full bundle.');
                        Bridge.call('download_game_with_source',
                            String(_currentAppId), src, '0');
                        return;
                    }
                    if (src === 'local') {
                        if (!checkedIds.length) {
                            Components.showToast('warning', 'Tick at least one DLC first.');
                            return;
                        }
                        // Local-files path: prompt for a manifest folder
                        // and run DDMod against the parent app with the
                        // user's local manifests. DDMod resolves owned
                        // DLCs from the parent's depot map automatically;
                        // the checkbox list is informational here.
                        Bridge.callSync('open_manifest_folder_dialog', function (folder) {
                            if (!folder) return;
                            Components.showToast('info',
                                'Running DDMod (local) against parent ' + _currentAppId + '...');
                            Bridge.call('download_game_ddmod',
                                String(_currentAppId), 'local', '', String(folder), '');
                        });
                        return;
                    }
                    // oureveryday
                    if (!checkedIds.length) {
                        Components.showToast('warning', 'Tick at least one DLC first.');
                        return;
                    }
                    Components.showToast('info', 'Queueing ' + checkedIds.length + ' DLC(s) through oureveryday...');
                    checkedIds.forEach(function (id) {
                        Bridge.call('download_dlc_oureveryday',
                            String(id), String(_currentAppId));
                    });
                };
            });
        }
    }

    function show(appId) {
        if (!appId) {
            Components.showToast('warning', 'Please select a game first.');
            return;
        }
        _currentAppId = String(appId);
        var titleEl = document.getElementById('dlc-check-title');
        var summaryEl = document.getElementById('dlc-check-summary');
        if (titleEl) titleEl.textContent = 'DLC Check — App ' + _currentAppId;
        if (summaryEl) summaryEl.textContent = '';
        Components.showModal('dlc-check-modal');
        _setLoading('Fetching DLC list from Steam...');
        Bridge.call('dlc_check_get_list', _currentAppId);
    }

    function _onTaskFinished(json) {
        try {
            var data = JSON.parse(json);
            if (data.task !== 'dlc_check') return;
            if (data.app_id && data.app_id !== _currentAppId) return;
            if (!data.success) {
                _renderError(data.message || 'Failed to fetch DLC list.');
                return;
            }
            var titleEl = document.getElementById('dlc-check-title');
            if (titleEl && data.base_name) {
                titleEl.textContent = 'DLC Check — ' + data.base_name;
            }
            _renderList(data);
        } catch (e) {
            _renderError('Could not parse DLC payload.');
        }
    }

    function init() {
        if (_initialized) return;
        _initialized = true;
        Bridge.on('task_finished', _onTaskFinished);
    }

    window.DlcCheck = { init: init, show: show };
})();
