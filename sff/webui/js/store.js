/**
 * SteaMidra — Store Page
 * Search, grid/list rendering, pagination
 */

window.Store = (function() {
    'use strict';

    var _page = 1;
    var _perPage = 20;
    var _totalPages = 1;
    var _total = 0;
    var _searchQuery = '';
    var _sortBy = 'updated';
    var _viewMode = 'grid';
    var _apiKeyConnected = false;
    var _initialized = false;
    var _imagesHidden = false;
    var _activeGenre = '';
    var _blockNsfw = true;
    var _nsfwNameRe = /(hentai|futanari|furry|sex)/i;
    var _active = false;
    var _lastGames = [];
    var _requestSeq = 0;
    var _activeRequestId = '';
    var _initialFetchDone = false;

    function init() {
        if (_initialized) return;
        _initialized = true;

        var searchInput = document.getElementById('store-search');
        var searchBtn = document.getElementById('store-search-btn');
        var sortSelect = document.getElementById('store-sort');
        var viewGrid = document.getElementById('view-grid');
        var viewList = document.getElementById('view-list');
        var prevBtn = document.getElementById('page-prev');
        var nextBtn = document.getElementById('page-next');
        var apiKeyConnect = document.getElementById('api-key-connect');
        var toggleImagesBtn = document.getElementById('store-toggle-images');
        var providerRefreshBtn = document.getElementById('store-provider-refresh-btn');

        if (searchInput) {
            searchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    _submitSearch(searchInput);
                }
            });
        }

        if (searchBtn) {
            searchBtn.addEventListener('click', function() {
                _submitSearch(searchInput);
            });
        }

        if (sortSelect) {
            sortSelect.addEventListener('change', function() {
                _sortBy = this.value;
                _page = 1;
                _fetchGames();
            });
        }

        if (viewGrid) viewGrid.addEventListener('click', function() { _setViewMode('grid'); });
        if (viewList) viewList.addEventListener('click', function() { _setViewMode('list'); });

        if (toggleImagesBtn) {
            toggleImagesBtn.addEventListener('click', function() {
                _imagesHidden = !_imagesHidden;
                Components.setHideImages(_imagesHidden);
                Bridge.call('set_setting', 'hide_store_images', _imagesHidden ? 'True' : 'False');
                toggleImagesBtn.classList.toggle('active', _imagesHidden);
                _fetchGames();
            });
        }

        var toggleNsfwBtn = document.getElementById('store-toggle-nsfw');
        if (toggleNsfwBtn) {
            toggleNsfwBtn.addEventListener('click', function() {
                _blockNsfw = !_blockNsfw;
                this.classList.toggle('active', _blockNsfw);
                Bridge.call('set_setting', 'store_block_nsfw', _blockNsfw ? 'True' : 'False');
                _fetchGames();
            });
        }

        var disconnectHubcapBtn = document.getElementById('store-disconnect-hubcap');
        if (disconnectHubcapBtn) {
            disconnectHubcapBtn.addEventListener('click', function() {
                Bridge.call('store_disconnect');
                _apiKeyConnected = false;
                disconnectHubcapBtn.classList.add('hidden');
                var connectBtn = document.getElementById('store-connect-hubcap');
                if (connectBtn) connectBtn.classList.remove('hidden');
                _showConnectBanner();
                Components.showToast('info', 'Hubcap disconnected — using Steam fallback search.');
                _fetchGames();
            });
        }

        var connectHubcapBtn = document.getElementById('store-connect-hubcap');
        if (connectHubcapBtn) {
            connectHubcapBtn.addEventListener('click', function() {
                var input = document.getElementById('api-key-input');
                var key = input ? input.value.trim() : '';
                if (!key) {
                    Components.showToast('warning', 'Please enter an API key above');
                    return;
                }
                Bridge.call('connect_store', key);
                _apiKeyConnected = true;
                connectHubcapBtn.classList.add('hidden');
                if (disconnectHubcapBtn) disconnectHubcapBtn.classList.remove('hidden');
                _hideConnectBanner();
                _fetchGames();
                Components.showToast('success', 'API key saved. Loading store...');
            });
        }

        var genreChips = document.querySelectorAll('.genre-chip');
        genreChips.forEach(function(chip) {
            chip.addEventListener('click', function() {
                _activeGenre = chip.dataset.genre || '';
                genreChips.forEach(function(c) { c.classList.remove('active'); });
                chip.classList.add('active');
                _page = 1;
                _fetchGames();
            });
        });

        if (prevBtn) prevBtn.addEventListener('click', function() { if (_page > 1) { _page--; _fetchGames(); } });
        if (nextBtn) nextBtn.addEventListener('click', function() { if (_page < _totalPages) { _page++; _fetchGames(); } });

        var updateListBtn = document.getElementById('store-update-list-btn');
        if (updateListBtn) {
            updateListBtn.addEventListener('click', function() {
                updateListBtn.disabled = true;
                updateListBtn.textContent = 'Updating...';
                Components.showToast('info', 'Downloading game list and metadata from all sources...');
                Bridge.call('update_store_lists');
            });
        }

        if (providerRefreshBtn) {
            providerRefreshBtn.addEventListener('click', function() {
                providerRefreshBtn.disabled = true;
                providerRefreshBtn.textContent = 'Refreshing...';
                _setProviderStatus('Refreshing depot keys...');
                Bridge.call('provider_update_now');
            });
        }

        if (apiKeyConnect) {
            apiKeyConnect.addEventListener('click', function() {
                var input = document.getElementById('api-key-input');
                var key = input ? input.value.trim() : '';
                if (!key) {
                    Components.showToast('warning', 'Please enter an API key');
                    return;
                }
                Bridge.call('connect_store', key);
                _apiKeyConnected = true;
                _hideConnectBanner();
                _fetchGames();
                Components.showToast('success', 'API key saved. Loading store...');
            });
        }

        // Listen for search results
        Bridge.on('search_results', function(json) {
            if (!_active) return;
            try {
                var data = JSON.parse(json);
                if (data.request_id && data.request_id !== _activeRequestId) return;
                _initialFetchDone = true;
                _hideLoading();
                var games = data.games || [];
                if (_blockNsfw) {
                    games = games.filter(function(g) { return !g.nsfw && !_looksNsfwByName(g); });
                }
                _renderGames(games);
                _total = data.total || games.length;
                _totalPages = Math.max(1, Math.ceil(_total / _perPage));
                _updatePagination();
                if (data.has_hubcap || data.has_fallback_data) {
                    _hideConnectBanner();
                    var discBtn = document.getElementById('store-disconnect-hubcap');
                    var connBtn = document.getElementById('store-connect-hubcap');
                    if (discBtn) discBtn.classList.remove('hidden');
                    if (connBtn) connBtn.classList.add('hidden');
                } else {
                    _showConnectBanner();
                    var msgEl = document.getElementById('store-banner-msg');
                    if (msgEl) {
                        msgEl.textContent = 'You can browse all games without a key — Hubcap shows which ones have manifests ready to download.';
                    }
                }
            } catch(e) {
                _hideLoading();
                Components.showToast('error', 'Failed to parse search results');
            }
        });

        Bridge.on('task_finished', function(json) {
            try {
                var data = JSON.parse(json || '{}');
                if (data.task === 'provider_update') {
                    _onProviderUpdateResult(data);
                }
            } catch(e) {}
        });
    }

    function _submitSearch(searchInput) {
        _searchQuery = searchInput ? searchInput.value.trim() : '';
        _page = 1;
        _fetchGames();
    }

    function onApiKeyAvailable(key) {
        _apiKeyConnected = true;
        if (_initialized && !_initialFetchDone) {
            _fetchGames();
        }
    }

    function onPageEnter() {
        init();
        _active = true;
        _page = 1;
        Bridge.call('warm_store_metadata');
        Bridge.callWithCallback('get_setting', 'hide_store_images', function(val) {
            _imagesHidden = (val === 'True');
            Components.setHideImages(_imagesHidden);
            var btn = document.getElementById('store-toggle-images');
            if (btn) btn.classList.toggle('active', _imagesHidden);
        });
        Bridge.callWithCallback('get_setting', 'store_block_nsfw', function(val) {
            _blockNsfw = (val !== 'False');
            var btn = document.getElementById('store-toggle-nsfw');
            if (btn) btn.classList.toggle('active', _blockNsfw);
        });
        _loadProviderStatus();
        _fetchGames();
    }

    function onPageLeave() {
        _active = false;
        _activeRequestId = '';
        _lastGames = [];
        _initialFetchDone = false;
        _releaseStoreImages();
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        var loading = document.getElementById('store-loading');
        if (grid) {
            grid.innerHTML = '';
            grid.classList.add('hidden');
        }
        if (list) {
            list.innerHTML = '';
            list.classList.add('hidden');
        }
        if (loading) loading.classList.add('hidden');
    }

    function _fetchGames() {
        var requestId = String(++_requestSeq);
        _activeRequestId = requestId;
        if (_blockNsfw && _nsfwNameRe.test(_searchQuery || '')) {
            _hideLoading();
            _renderGames([]);
            _total = 0;
            _totalPages = 1;
            _updatePagination();
            _hideConnectBanner();
            return;
        }
        _showLoading();
        var offset = (_page - 1) * _perPage;
        Bridge.call('search_games', _searchQuery, offset, _perPage, _sortBy, _activeGenre, requestId);
    }

    function _looksNsfwByName(game) {
        var name = ((game && game.name) || '').toString();
        return _nsfwNameRe.test(name);
    }

    function _releaseStoreImages() {
        document.querySelectorAll('#store-grid img, #store-list img').forEach(function(img) {
            img.onload = null;
            img.onerror = null;
            img.removeAttribute('src');
        });
    }

    function _renderGames(games) {
        games = games || [];
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        var pagination = document.getElementById('store-pagination');

        _releaseStoreImages();
        _lastGames = (games || []).slice(0);
        if (grid) grid.innerHTML = '';
        if (list) list.innerHTML = '';

        if (games.length === 0) {
            var empty = '<div class="empty-state"><p>No games found. Try a different search.</p></div>';
            if (_viewMode === 'list') {
                if (list) list.innerHTML = empty;
            } else {
                if (grid) grid.innerHTML = empty;
            }
            if (pagination) pagination.classList.add('hidden');
            return;
        }

        _renderCurrentView();

        if (pagination) pagination.classList.remove('hidden');
    }

    function _renderCurrentView() {
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        if (_viewMode === 'list') {
            if (!list || list.children.length) return;
            _lastGames.forEach(function(game) {
                list.appendChild(Components.createGameListItem(game));
            });
            return;
        }
        if (!grid || grid.children.length) return;
        _lastGames.forEach(function(game, index) {
            grid.appendChild(Components.createGameCard(game, { index: index }));
        });
    }

    function _updatePagination() {
        var info = document.getElementById('page-info');
        var prevBtn = document.getElementById('page-prev');
        var nextBtn = document.getElementById('page-next');

        if (info) info.textContent = 'Page ' + _page + ' of ' + _totalPages + ' (' + _total + ' games)';
        if (prevBtn) prevBtn.disabled = _page <= 1;
        if (nextBtn) nextBtn.disabled = _page >= _totalPages;
    }

    function _setViewMode(mode) {
        _viewMode = mode;
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        var viewGrid = document.getElementById('view-grid');
        var viewList = document.getElementById('view-list');

        _releaseStoreImages();
        if (grid) grid.innerHTML = '';
        if (list) list.innerHTML = '';

        if (mode === 'grid') {
            if (grid) grid.classList.remove('hidden');
            if (list) list.classList.add('hidden');
            if (viewGrid) viewGrid.classList.add('active');
            if (viewList) viewList.classList.remove('active');
        } else {
            if (grid) grid.classList.add('hidden');
            if (list) list.classList.remove('hidden');
            if (viewGrid) viewGrid.classList.remove('active');
            if (viewList) viewList.classList.add('active');
        }
        _renderCurrentView();
    }

    function _showLoading() {
        var loading = document.getElementById('store-loading');
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        _lastGames = [];
        _releaseStoreImages();
        if (grid) grid.innerHTML = '';
        if (list) list.innerHTML = '';
        if (loading) loading.classList.remove('hidden');
        if (grid) grid.classList.add('hidden');
        if (list) list.classList.add('hidden');
    }

    function _hideLoading() {
        var loading = document.getElementById('store-loading');
        if (loading) loading.classList.add('hidden');
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        if (_viewMode === 'list') {
            if (list) list.classList.remove('hidden');
        } else {
            if (grid) grid.classList.remove('hidden');
        }
    }

    function _hideConnectBanner() {
        var banner = document.getElementById('store-connect-banner');
        if (banner) banner.classList.add('hidden');
    }

    function _showConnectBanner() {
        var banner = document.getElementById('store-connect-banner');
        if (banner) banner.classList.remove('hidden');
    }

    function _fmtProviderTime(epoch) {
        var n = parseInt(epoch || '0', 10);
        if (!n) return 'never';
        try {
            return new Date(n * 1000).toLocaleString();
        } catch(e) {
            return 'unknown';
        }
    }

    function _setProviderStatus(text) {
        var el = document.getElementById('store-provider-status');
        if (el) el.textContent = text || '';
    }

    function _renderProviderStatus(data) {
        data = data || {};
        var parts = [
            'Depot keys: ' + (data.count || 0) + ' entries',
            'last attempt ' + _fmtProviderTime(data.last_attempt_at),
            'last success ' + _fmtProviderTime(data.last_success_at)
        ];
        if (data.last_error) parts.push('last error: ' + data.last_error);
        _setProviderStatus(parts.join(' • '));
    }

    function _loadProviderStatus() {
        Bridge.callWithCallback('get_provider_cache_status', function(json) {
            var data = {};
            try { data = JSON.parse(json || '{}'); } catch(e) {}
            _renderProviderStatus(data);
        });
    }

    function _onProviderUpdateResult(data) {
        var btn = document.getElementById('store-provider-refresh-btn');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Depot Keys';
        }
        _renderProviderStatus(data);
    }

    return {
        init: init,
        onPageEnter: onPageEnter,
        onPageLeave: onPageLeave,
        refresh: _fetchGames,
        onApiKeyAvailable: onApiKeyAvailable
    };
})();
