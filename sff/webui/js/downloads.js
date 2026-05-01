/**
 * SteaMidra — Downloads Page
 * Active downloads with progress bars + download history.
 */

window.Downloads = (function() {
    'use strict';

    var _downloads = {};
    var _initialized = false;

    function init() {
        if (_initialized) return;
        _initialized = true;

        Bridge.on('download_progress', function(json) {
            try {
                var data = JSON.parse(json);
                _updateDownload(data);
            } catch(e) {}
        });

        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json);
                if (data.task && data.task.indexOf('download') !== -1) {
                    _completeDownload(data);
                }
            } catch(e) {}
        });
    }

    function onPageEnter() {
        init();
        _render();
    }

    function _updateDownload(data) {
        var id = data.id || data.app_id || 'unknown';
        _downloads[id] = {
            id: id,
            name: data.name || ('App ' + id),
            status: data.status || 'Downloading',
            progress: data.progress || 0,
            active: true,
            timestamp: Date.now()
        };
        _render();
    }

    function _completeDownload(data) {
        var id = data.task || data.app_id || 'unknown';
        if (_downloads[id]) {
            _downloads[id].active = false;
            _downloads[id].status = data.success ? 'Completed' : 'Failed';
            _downloads[id].progress = data.success ? 100 : _downloads[id].progress;
        } else {
            _downloads[id] = {
                id: id,
                name: data.message || id,
                status: data.success ? 'Completed' : 'Failed',
                progress: data.success ? 100 : 0,
                active: false,
                timestamp: Date.now()
            };
        }
        _render();
    }

    function _render() {
        var activeList = document.getElementById('downloads-active-list');
        var activeEmpty = document.getElementById('downloads-active-empty');
        var historyList = document.getElementById('downloads-history-list');

        var activeItems = [];
        var historyItems = [];

        Object.keys(_downloads).forEach(function(id) {
            var dl = _downloads[id];
            if (dl.active) {
                activeItems.push(dl);
            } else {
                historyItems.push(dl);
            }
        });

        // Render active downloads
        if (activeList) {
            activeList.innerHTML = '';
            activeItems.forEach(function(dl) {
                activeList.appendChild(Components.createDownloadItem(dl));
            });
        }
        if (activeEmpty) {
            activeEmpty.classList.toggle('hidden', activeItems.length > 0);
        }

        // Render history
        if (historyList) {
            historyList.innerHTML = '';
            historyItems.sort(function(a, b) { return (b.timestamp || 0) - (a.timestamp || 0); });
            historyItems.forEach(function(dl) {
                historyList.appendChild(Components.createDownloadItem(dl));
            });
        }
    }

    return {
        init: init,
        onPageEnter: onPageEnter
    };
})();
