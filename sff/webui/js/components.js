/**
 * SteaMidra — Shared UI Components
 * Game cards, modals, tooltips, toasts
 */

window.Components = (function() {
    'use strict';

    var _hideImages = false;

    // A short fallback chain avoids issuing a dozen failed requests for every
    // delisted title while still covering Steam's current asset layouts.
    var _CDN = [
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/library_600x900.jpg',
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/header.jpg',
        'https://shared.steamstatic.com/store_item_assets/steam/apps/{id}/capsule_616x353.jpg',
        'https://cdn.cloudflare.steamstatic.com/steam/apps/{id}/header.jpg'
    ];
    var STEAM_CDN_LIBRARY = 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg';

    var _COVER_CACHE_KEY = 'sff_cover_cache_v2';
    var _COVER_CACHE_MAX = 160;
    var _coverCache = null;

    function _loadCoverCache() {
        if (_coverCache) return _coverCache;
        try {
            _coverCache = JSON.parse(localStorage.getItem(_COVER_CACHE_KEY) || '{}');
        } catch(e) {
            _coverCache = {};
        }
        return _coverCache;
    }

    function _persistCoverCache() {
        var cache = _loadCoverCache();
        var ids = Object.keys(cache);
        if (ids.length > _COVER_CACHE_MAX) {
            ids.sort(function(a, b) {
                return (cache[b].t || 0) - (cache[a].t || 0);
            }).slice(_COVER_CACHE_MAX).forEach(function(id) { delete cache[id]; });
        }
        try { localStorage.setItem(_COVER_CACHE_KEY, JSON.stringify(cache)); } catch(e) {}
    }

    function _getCachedCoverUrl(appId) {
        var entry = _loadCoverCache()[String(appId)];
        if (!entry || !entry.url) return null;
        entry.t = Date.now();
        return entry.url;
    }

    function _saveCoverCache(appId, url) {
        _loadCoverCache()[String(appId)] = { url: url, t: Date.now() };
        _persistCoverCache();
    }

    // SVG placeholder for missing game images (image-off icon)
    var NO_IMAGE_SVG = '<svg viewBox="0 0 24 24"><line x1="1" y1="1" x2="23" y2="23"/><path d="M21 21H3a2 2 0 01-2-2V5a2 2 0 012-2h18a2 2 0 012 2v14c0 .553-.224 1.053-.586 1.414"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>';

    function getCoverUrls(appId, canonicalUrl) {
        var cached = _getCachedCoverUrl(appId);
        if (cached) return [cached];
        var urls = _CDN.map(function(t) { return t.replace('{id}', appId); });
        if (canonicalUrl) {
            urls.unshift(canonicalUrl.split('?')[0]);
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
        if (game.nsfw) {
            badgesHtml += '<span class="badge badge-nsfw">NSFW</span>';
        }

        var lastUpdated = game.last_updated ? '<div class="game-card-meta">Updated: ' + game.last_updated + '</div>' : '';
        var drmBadge = game.drm ? '<span class="badge badge-drm">DRM</span>' : '';

        card.setAttribute('role', 'listitem');
        card.setAttribute('tabindex', '0');
        card.setAttribute('aria-label', game.name + ' - App ID ' + game.app_id);
        card.innerHTML =
            '<div class="game-card-img-wrap"></div>' +
            '<div class="game-card-badges">' + badgesHtml + '</div>' +
            '<div class="game-card-body">' +
                '<div class="game-card-name">' + escapeHtml(game.name) + '</div>' +
                '<div class="game-card-appid">App ID: ' + game.app_id + drmBadge + '</div>' +
                (game.crack_buildid ? '<div class="game-card-buildid" style="color:#ff9800;font-size:11px;margin-top:1px;">Crack BuildID: ' + escapeHtml(String(game.crack_buildid)) + '</div>' : '') +
                lastUpdated +
            '</div>' +
            '<div class="game-card-actions">' +
                '<button class="btn btn-primary btn-download" data-appid="' + game.app_id + '" data-name="' + escapeHtml(game.name) + '" data-tooltip="Download this game">Download</button>' +
            '</div>';

        // Load image with 8-tier fallback chain then SVG placeholder
        var wrap = card.querySelector('.game-card-img-wrap');
        if (_hideImages && !options.forceShowImage) {
            wrap.innerHTML = '<div class="game-card-img-placeholder">' + NO_IMAGE_SVG + '</div>';
        } else {
            var img = document.createElement('img');
            img.className = 'game-card-img';
            img.alt = game.name;
            img.loading = 'lazy';
            img.decoding = 'async';
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
            img.onload = function() { _saveCoverCache(game.app_id, img.src); };
            img.onerror = tryNextCard;
            img.src = urls[0];
            wrap.appendChild(img);
        }

        // Stagger animation delay — capped at 0.4s so large grids don't
        // have late cards blinking in after the user thinks rendering is done.
        if (typeof options.index === 'number') {
            var delay = Math.min(options.index * 0.04, 0.4);
            card.style.animationDelay = delay + 's';
        }

        return card;
    }

    // Create a game list item (list view)
    function createGameListItem(game) {
        var item = document.createElement('div');
        item.className = 'game-list-item';
        item.dataset.appid = game.app_id;

        var listBadges = '';
        if (game.nsfw) {
            listBadges += '<span class="badge badge-nsfw" style="margin-left:6px;">NSFW</span>';
        }
        if (game.drm) {
            listBadges += '<span class="badge badge-drm" style="margin-left:6px;">DRM</span>';
        }
        if (game.platform_label) {
            listBadges += '<span class="badge badge-platform" style="margin-left:6px;">' + escapeHtml(game.platform_label) + '</span>';
        }
        item.setAttribute('role', 'listitem');
        item.setAttribute('tabindex', '0');
        item.setAttribute('aria-label', game.name + ' - App ID ' + game.app_id);
        item.innerHTML =
            '<div class="game-list-thumb-wrap"></div>' +
            '<div class="game-list-info">' +
                '<div class="game-list-name">' + escapeHtml(game.name) + listBadges + '</div>' +
                '<div class="game-list-appid">App ID: ' + game.app_id + '</div>' +
            '</div>' +
            '<div class="game-list-actions">' +
                '<button class="btn btn-primary btn-sm btn-download" data-appid="' + game.app_id + '" data-name="' + escapeHtml(game.name) + '">Download</button>' +
            '</div>';

        // Load image with 8-tier fallback chain then SVG placeholder
        var wrap = item.querySelector('.game-list-thumb-wrap');
        if (_hideImages) {
            wrap.innerHTML = '<div class="game-card-img-placeholder" style="height:45px;width:80px;opacity:0.2">' + NO_IMAGE_SVG + '</div>';
        } else {
            var img = document.createElement('img');
            img.className = 'game-list-thumb';
            img.alt = '';
            img.loading = 'lazy';
            img.decoding = 'async';
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
            img.onload = function() { _saveCoverCache(game.app_id, img.src); };
            img.onerror = tryNextList;
            img.src = urls[0];
            wrap.appendChild(img);
        }

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
    // Uses a generation counter per modal to cancel stale hide timeouts —
    // previously a hideModal timer would fire after a showModal call and
    // re-hide the freshly opened modal (visible as a blink).
    function showModal(modalId) {
        var modal = document.getElementById(modalId);
        if (!modal) return;
        // Bump generation so any pending hideModal setTimeout becomes a no-op
        modal.dataset.modalGen = ((parseInt(modal.dataset.modalGen, 10) || 0) + 1).toString();
        modal.classList.remove('hidden', 'modal-hiding');
    }

    function hideModal(modalId) {
        var modal = document.getElementById(modalId);
        if (!modal || modal.classList.contains('hidden')) return;
        var gen = ((parseInt(modal.dataset.modalGen, 10) || 0) + 1).toString();
        modal.dataset.modalGen = gen;
        modal.classList.add('modal-hiding');
        setTimeout(function() {
            // Only apply if no showModal() or newer hideModal() has run since
            if (modal.dataset.modalGen !== gen) return;
            modal.classList.remove('modal-hiding');
            modal.classList.add('hidden');
        }, 150);
    }

    // Show download modal for a specific game
    function showDownloadModal(appId, gameName, platform) {
        var modal = document.getElementById('download-modal');
        var title = document.getElementById('download-modal-title');
        if (title) title.textContent = 'Download: ' + gameName + ' (' + appId + ')';

        // Linux: hide fastest (through Steam needs LumaCore, Linux uses DDMod only)
        var dlFastest = document.getElementById('dl-fastest');
        if (platform === 'linux') {
            if (dlFastest) dlFastest.style.display = 'none';
        } else {
            if (dlFastest) dlFastest.style.display = '';
            var fastestTitle = document.getElementById('dl-fastest-title');
            var fastestDesc = document.getElementById('dl-fastest-desc');
            if (fastestTitle) fastestTitle.textContent = 'Download through Steam (Fastest)';
            if (fastestDesc) fastestDesc.textContent = 'Downloads manifests + keys so Steam installs the game natively. Fastest method.';
        }

        // Store the app ID for the download buttons
        var dlOlder = document.getElementById('dl-older');
        var dlDdmod = document.getElementById('dl-ddmod');
        var dlDdmodDest = document.getElementById('dl-ddmod-dest-path');
        if (dlFastest) dlFastest.dataset.appid = appId;
        if (dlOlder) dlOlder.dataset.appid = appId;
        if (dlDdmod) dlDdmod.dataset.appid = appId;
        if (dlDdmodDest) dlDdmodDest.value = '';

        // Reset source to default, then pre-fetch Ryuu branches in background
        var defaultSource = document.querySelector('input[name="dl-source"][value="oureveryday"]');
        if (defaultSource) defaultSource.checked = true;
        if (window._updateDownloadSourceHint) window._updateDownloadSourceHint();
        var ryuuOpt = document.getElementById('ryuu-update-option');
        if (ryuuOpt) ryuuOpt.style.display = 'none';
        var localRow = document.getElementById('dl-local-row');
        if (localRow) localRow.style.display = 'none';
        Bridge.callWithCallback('get_game_branches', appId, function(json) {
            _populateRyuuBranches(json);
        });

        // Crack availability banner (CrakFiles). Memory-only lookup; retry
        // once shortly after in case the crack database is still loading.
        var crackBanner = document.getElementById('dl-crack-banner');
        if (crackBanner) crackBanner.style.display = 'none';
        _loadCrackBanner(appId, gameName, 1);

        showModal('download-modal');
    }

    function _loadCrackBanner(appId, gameName, attempt) {
        var crackBanner = document.getElementById('dl-crack-banner');
        if (!crackBanner) return;
        Bridge.callWithCallback('get_crack_info', appId, gameName || '', function(json) {
            var data;
            try { data = JSON.parse(json || '{}'); } catch (err) { data = {}; }
            if (!data.found) {
                if (attempt < 2) {
                    setTimeout(function() { _loadCrackBanner(appId, gameName, attempt + 1); }, 4000);
                }
                return;
            }
            var textEl = document.getElementById('dl-crack-banner-text');
            var olderBtn = document.getElementById('dl-crack-older-btn');
            var srcBtn = document.getElementById('dl-crack-source-btn');
            if (data.match_latest === true) {
                if (textEl) textEl.textContent = 'Crack available for this game — it matches the latest build. Use "Add to Library" (Download through Steam, Fastest) to install it.';
                if (olderBtn) olderBtn.style.display = 'none';
            } else {
                if (textEl) textEl.textContent = 'Crack available for this game — it needs Build ID ' + (data.crack_buildid || '?') + '. Use Download Older Version.';
                if (olderBtn) olderBtn.style.display = '';
            }
            if (olderBtn) {
                olderBtn.onclick = function() {
                    if (window._openOlderVersionForCrack) {
                        window._openOlderVersionForCrack(appId, data.crack_buildid || '');
                    }
                };
            }
            if (srcBtn && data.source_crack && data.source_crack.length) {
                srcBtn.onclick = function() {
                    Bridge.call('open_url', data.source_crack[0]);
                };
            } else if (srcBtn) {
                srcBtn.style.display = 'none';
            }
            crackBanner.style.display = 'block';
        });
    }

    function _populateRyuuBranches(json) {
        var sel = document.getElementById('ryuu-branch-select');
        if (!sel) return;
        sel.innerHTML = '<option value="public">public (default)</option>';
        try {
            var branches = JSON.parse(json || '[]');
            if (!Array.isArray(branches)) return;
            branches.forEach(function(b) {
                if (!b || !b.name || b.name === 'public') return;
                var label = b.name + (b.description ? ' - ' + b.description : '');
                var opt = document.createElement('option');
                opt.value = b.name;
                opt.textContent = label;
                sel.appendChild(opt);
            });
        } catch(e) {}
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
                if (modal) hideModal(modal.id);
            });
        });

        document.querySelectorAll('.modal-overlay:not([data-no-close])').forEach(function(overlay) {
            overlay.addEventListener('click', function() {
                var modal = this.closest('.modal');
                if (modal) hideModal(modal.id);
            });
        });

        // Background branch fetch backfill — fills the Ryuu branch dropdown
        // when the sync call returned empty (Steam CM slow on the first ask).
        Bridge.on('game_branches_ready', function(json) {
            try {
                var p = JSON.parse(json || '{}');
                var modal = document.getElementById('download-modal');
                if (!modal || modal.classList.contains('hidden')) return;
                var dlOlder = document.getElementById('dl-older');
                var current = dlOlder ? dlOlder.dataset.appid : '';
                if (String(p.app_id) !== String(current)) return;
                _populateRyuuBranches(JSON.stringify(p.branches || []));
            } catch (e) {}
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
            // 50ms debounce: batches rapid option inserts (e.g. filling a
            // 300-game dropdown one option at a time) into a single sync,
            // eliminating the visible flicker of intermediate states.
            syncTimer = setTimeout(function() { self._syncOptions(); }, 50);
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

        this._select.addEventListener('input', function() { self._syncSelected(); });

        setTimeout(function() { self._syncOptions(); }, 0);
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

    function setHideImages(val) {
        _hideImages = !!val;
    }

    function showConfirm(title, message, onYes, onNo) {
        var modal = document.getElementById('confirm-dialog');
        var titleEl = document.getElementById('confirm-dialog-title');
        var msgEl = document.getElementById('confirm-dialog-message');
        var yesBtn = document.getElementById('confirm-dialog-yes');
        var noBtn = document.getElementById('confirm-dialog-no');
        var closeBtn = document.getElementById('confirm-dialog-cancel');

        if (titleEl) titleEl.textContent = title || 'Confirm';
        if (msgEl) msgEl.textContent = message || '';

        var cleanup = function() {
            hideModal('confirm-dialog');
            yesBtn.removeEventListener('click', onYesHandler);
            noBtn.removeEventListener('click', onNoHandler);
            if (closeBtn) closeBtn.removeEventListener('click', onNoHandler);
        };

        var onYesHandler = function() { cleanup(); if (onYes) onYes(); };
        var onNoHandler = function() { cleanup(); if (onNo) onNo(); };

        yesBtn.addEventListener('click', onYesHandler);
        noBtn.addEventListener('click', onNoHandler);
        if (closeBtn) closeBtn.addEventListener('click', onNoHandler);

        showModal('confirm-dialog');
    }

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
        showConfirm: showConfirm,
        escapeHtml: escapeHtml,
        initModals: initModals,
        CustomSelect: CustomSelect,
        setHideImages: setHideImages,
        _populateRyuuBranches: _populateRyuuBranches
    };
})();
