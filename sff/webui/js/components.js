/**
 * SteaMidra — Shared UI Components
 * Game cards, modals, tooltips, toasts
 */

window.Components = (function() {
    'use strict';

    // Steam CDN image URL templates — ordered by 2026 reliability (akamai.shared first, matches Steam API responses)
    var _CDN = [
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/library_600x900.jpg',
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/header.jpg',
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/library_header.jpg',
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/capsule_616x353.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/library_600x900.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/header.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/library_header.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/capsule_616x353.jpg',
        'https://shared.steamstatic.com/store_item_assets/steam/apps/{id}/library_600x900.jpg',
        'https://shared.steamstatic.com/store_item_assets/steam/apps/{id}/header.jpg',
        'https://shared.steamstatic.com/store_item_assets/steam/apps/{id}/library_header.jpg',
        'https://shared.steamstatic.com/store_item_assets/steam/apps/{id}/capsule_616x353.jpg',
        'https://cdn.akamai.steamstatic.com/steam/apps/{id}/header.jpg',
        'https://cdn.cloudflare.steamstatic.com/steam/apps/{id}/header.jpg'
    ];
    var STEAM_CDN_LIBRARY = 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg';

    // SVG placeholder for missing game images (image-off icon)
    var NO_IMAGE_SVG = '<svg viewBox="0 0 24 24"><line x1="1" y1="1" x2="23" y2="23"/><path d="M21 21H3a2 2 0 01-2-2V5a2 2 0 012-2h18a2 2 0 012 2v14c0 .553-.224 1.053-.586 1.414"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>';

    function getCoverUrls(appId, canonicalUrl) {
        var ts = '?t=' + Date.now();
        var urls = _CDN.map(function(t) { return t.replace('{id}', appId) + ts; });
        if (canonicalUrl) {
            urls.unshift(canonicalUrl.split('?')[0] + ts);
        }
        return urls;
    }

    function getLibraryCoverUrl(appId) {
        return STEAM_CDN_LIBRARY.replace('{appid}', appId);
    }

    // Create a game card element (grid view)
    function createGameCard(game, options) {
        options = options || {};
        var card = document.createElement('div');
        card.className = 'game-card stagger-in';
        card.dataset.appid = game.app_id;

        var badgesHtml = '';
        if (game.status === 'available') {
            badgesHtml += '<span class="badge badge-available">Available</span>';
        }
        if (game.installed) {
            badgesHtml += '<span class="badge badge-downloaded">Installed</span>';
        }

        var lastUpdated = game.last_updated ? '<div class="game-card-meta">Updated: ' + game.last_updated + '</div>' : '';

        card.innerHTML =
            '<div class="game-card-img-wrap"></div>' +
            '<div class="game-card-badges">' + badgesHtml + '</div>' +
            '<div class="game-card-body">' +
                '<div class="game-card-name">' + escapeHtml(game.name) + '</div>' +
                '<div class="game-card-appid">App ID: ' + game.app_id + '</div>' +
                lastUpdated +
            '</div>' +
            '<div class="game-card-actions">' +
                '<button class="btn btn-primary btn-download" data-appid="' + game.app_id + '" data-name="' + escapeHtml(game.name) + '" data-tooltip="Download this game">Download</button>' +
            '</div>';

        // Load image with 8-tier fallback chain then SVG placeholder
        var wrap = card.querySelector('.game-card-img-wrap');
        var img = document.createElement('img');
        img.className = 'game-card-img';
        img.alt = game.name;
        img.loading = 'lazy';
        var urls = getCoverUrls(game.app_id, game.image_url || null);
        var urlIdx = 0;
        function tryNextCard() {
            urlIdx++;
            if (urlIdx < urls.length) {
                img.onerror = tryNextCard;
                img.src = urls[urlIdx];
            } else {
                img.onerror = null;
                wrap.innerHTML = '<div class="game-card-img-placeholder">' + NO_IMAGE_SVG + '</div>';
            }
        }
        img.onerror = tryNextCard;
        img.src = urls[0];
        wrap.appendChild(img);

        // Stagger animation delay
        if (typeof options.index === 'number') {
            card.style.animationDelay = (options.index * 0.05) + 's';
        }

        return card;
    }

    // Create a game list item (list view)
    function createGameListItem(game) {
        var item = document.createElement('div');
        item.className = 'game-list-item';
        item.dataset.appid = game.app_id;

        item.innerHTML =
            '<div class="game-list-thumb-wrap"></div>' +
            '<div class="game-list-info">' +
                '<div class="game-list-name">' + escapeHtml(game.name) + '</div>' +
                '<div class="game-list-appid">App ID: ' + game.app_id + '</div>' +
            '</div>' +
            '<div class="game-list-actions">' +
                '<button class="btn btn-primary btn-sm btn-download" data-appid="' + game.app_id + '" data-name="' + escapeHtml(game.name) + '">Download</button>' +
            '</div>';

        // Load image with 8-tier fallback chain then SVG placeholder
        var wrap = item.querySelector('.game-list-thumb-wrap');
        var img = document.createElement('img');
        img.className = 'game-list-thumb';
        img.alt = '';
        img.loading = 'lazy';
        var urls = getCoverUrls(game.app_id, game.image_url || null);
        var urlIdx = 0;
        function tryNextList() {
            urlIdx++;
            if (urlIdx < urls.length) {
                img.onerror = tryNextList;
                img.src = urls[urlIdx];
            } else {
                img.onerror = null;
                wrap.innerHTML = '<div class="game-card-img-placeholder" style="height:45px;width:80px;opacity:0.2">' + NO_IMAGE_SVG + '</div>';
            }
        }
        img.onerror = tryNextList;
        img.src = urls[0];
        wrap.appendChild(img);

        return item;
    }

    // Create a download tracking item
    function createDownloadItem(download) {
        var item = document.createElement('div');
        item.className = 'download-item';
        item.dataset.id = download.id || '';

        var progressHtml = '';
        if (download.progress !== undefined && download.progress !== null) {
            progressHtml =
                '<div class="download-progress-bar">' +
                    '<div class="download-progress-fill" style="width:' + download.progress + '%"></div>' +
                '</div>';
        }

        var statusText = download.status || 'Pending';
        if (download.progress !== undefined) {
            statusText += ' — ' + Math.round(download.progress) + '%';
        }

        item.innerHTML =
            '<div class="download-item-info">' +
                '<div class="download-item-name">' + escapeHtml(download.name || 'Unknown') + '</div>' +
                '<div class="download-item-status">' + escapeHtml(statusText) + '</div>' +
                progressHtml +
            '</div>';

        return item;
    }

    // Show a toast notification
    function showToast(type, message) {
        var container = document.getElementById('toast-container');
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = 'toast toast-' + (type || 'info');
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(function() {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 4000);
    }

    // Show/hide a modal
    function showModal(modalId) {
        var modal = document.getElementById(modalId);
        if (modal) modal.classList.remove('hidden');
    }

    function hideModal(modalId) {
        var modal = document.getElementById(modalId);
        if (modal) modal.classList.add('hidden');
    }

    // Show download modal for a specific game
    function showDownloadModal(appId, gameName, platform) {
        var modal = document.getElementById('download-modal');
        var title = document.getElementById('download-modal-title');
        if (title) title.textContent = 'Download: ' + gameName + ' (' + appId + ')';

        // Update labels based on platform
        var fastestTitle = document.getElementById('dl-fastest-title');
        var fastestDesc = document.getElementById('dl-fastest-desc');
        if (platform === 'linux') {
            if (fastestTitle) fastestTitle.textContent = 'Fastest download (Latest version)';
            if (fastestDesc) fastestDesc.textContent = 'Downloads the latest version right away using DepotDownloaderMod.';
        } else {
            if (fastestTitle) fastestTitle.textContent = 'Download through Steam (Fastest)';
            if (fastestDesc) fastestDesc.textContent = 'Downloads manifests + keys so Steam installs the game natively. Fastest method.';
        }

        // Store the app ID for the download buttons
        var dlFastest = document.getElementById('dl-fastest');
        var dlOlder = document.getElementById('dl-older');
        if (dlFastest) dlFastest.dataset.appid = appId;
        if (dlOlder) dlOlder.dataset.appid = appId;

        showModal('download-modal');
    }

    // Show library selection modal
    function showLibraryModal(libraries, callback) {
        var container = document.getElementById('library-options');
        if (!container) return;
        container.innerHTML = '';

        var libs;
        try { libs = typeof libraries === 'string' ? JSON.parse(libraries) : libraries; }
        catch(e) { libs = []; }

        libs.forEach(function(libPath) {
            var btn = document.createElement('button');
            btn.className = 'library-option';
            btn.textContent = libPath;
            btn.addEventListener('click', function() {
                hideModal('library-modal');
                if (callback) callback(libPath);
            });
            container.appendChild(btn);
        });

        showModal('library-modal');
    }

    // HTML escaping utility
    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // Initialize modal close handlers
    function initModals() {
        document.querySelectorAll('.modal-close, .modal-cancel').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var modal = this.closest('.modal');
                if (modal) modal.classList.add('hidden');
            });
        });

        document.querySelectorAll('.modal-overlay').forEach(function(overlay) {
            overlay.addEventListener('click', function() {
                var modal = this.closest('.modal');
                if (modal) modal.classList.add('hidden');
            });
        });
    }

    // Custom styled dropdown that wraps a hidden <select> via MutationObserver.
    // Keeps the hidden <select> as the source of truth so all existing JS works unchanged.
    function CustomSelect(hiddenSelectId, customUiId) {
        this._select = document.getElementById(hiddenSelectId);
        this._ui    = document.getElementById(customUiId);
        if (!this._select || !this._ui) return;

        this._display  = this._ui.querySelector('.custom-select-text');
        this._dropdown = this._ui.querySelector('.custom-select-dropdown');
        if (!this._display || !this._dropdown) return;

        var self = this;
        var syncTimer = null;

        new MutationObserver(function() {
            clearTimeout(syncTimer);
            syncTimer = setTimeout(function() { self._syncOptions(); }, 10);
        }).observe(this._select, { childList: true });

        this._ui.querySelector('.custom-select-display').addEventListener('click', function(e) {
            e.stopPropagation();
            self._toggle();
        });

        document.addEventListener('click', function(e) {
            if (!self._ui.contains(e.target)) {
                self._close();
            }
        });
    }

    CustomSelect.prototype._syncOptions = function() {
        var self = this;
        this._dropdown.innerHTML = '';
        Array.prototype.forEach.call(this._select.options, function(opt) {
            var item = document.createElement('div');
            item.className = 'custom-select-option' + (opt.value && opt.value === self._select.value ? ' selected' : '');
            item.textContent = opt.textContent;
            item.dataset.value = opt.value;
            item.addEventListener('click', function(e) {
                e.stopPropagation();
                self._select.value = opt.value;
                self._syncSelected();
                self._select.dispatchEvent(new Event('change', { bubbles: true }));
                self._close();
            });
            self._dropdown.appendChild(item);
        });
        this._updateDisplay();
    };

    CustomSelect.prototype._syncSelected = function() {
        var val = this._select.value;
        this._dropdown.querySelectorAll('.custom-select-option').forEach(function(item) {
            item.classList.toggle('selected', item.dataset.value === val);
        });
        this._updateDisplay();
    };

    CustomSelect.prototype._updateDisplay = function() {
        var idx = this._select.selectedIndex;
        if (idx >= 0 && this._select.options[idx] && this._select.options[idx].value) {
            this._display.textContent = this._select.options[idx].textContent;
        } else {
            this._display.textContent = '-- Select a game --';
        }
    };

    CustomSelect.prototype._toggle = function() {
        if (this._dropdown.classList.contains('hidden')) {
            this._open();
        } else {
            this._close();
        }
    };

    CustomSelect.prototype._open = function() {
        document.querySelectorAll('.custom-select-dropdown').forEach(function(d) {
            d.classList.add('hidden');
        });
        document.querySelectorAll('.custom-select').forEach(function(el) {
            el.classList.remove('open');
        });
        this._dropdown.classList.remove('hidden');
        this._ui.classList.add('open');
    };

    CustomSelect.prototype._close = function() {
        this._dropdown.classList.add('hidden');
        this._ui.classList.remove('open');
    };

    return {
        getCoverUrls: getCoverUrls,
        getLibraryCoverUrl: getLibraryCoverUrl,
        createGameCard: createGameCard,
        createGameListItem: createGameListItem,
        createDownloadItem: createDownloadItem,
        showToast: showToast,
        showModal: showModal,
        hideModal: hideModal,
        showDownloadModal: showDownloadModal,
        showLibraryModal: showLibraryModal,
        escapeHtml: escapeHtml,
        initModals: initModals,
        CustomSelect: CustomSelect
    };
})();
