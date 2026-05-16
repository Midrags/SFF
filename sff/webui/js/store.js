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
    var _debounceTimer = null;
    var _initialized = false;
    var _imagesHidden = false;
    var _activeGenre = '';

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

        if (searchInput) {
            searchInput.addEventListener('input', function() {
                clearTimeout(_debounceTimer);
                _debounceTimer = setTimeout(function() {
                    _searchQuery = searchInput.value.trim();
                    _page = 1;
                    _fetchGames();
                }, 300);
            });
            searchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    clearTimeout(_debounceTimer);
                    _searchQuery = searchInput.value.trim();
                    _page = 1;
                    _fetchGames();
                }
            });
        }

        if (searchBtn) {
            searchBtn.addEventListener('click', function() {
                _searchQuery = searchInput ? searchInput.value.trim() : '';
                _page = 1;
                _fetchGames();
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
            _hideLoading();
            try {
                var data = JSON.parse(json);
                _renderGames(data.games || []);
                _total = data.total || 0;
                _totalPages = Math.max(1, Math.ceil(_total / _perPage));
                _updatePagination();
                if (data.has_hubcap) {
                    _hideConnectBanner();
                } else {
                    _showConnectBanner();
                    var msgEl = document.getElementById('store-banner-msg');
                    if (msgEl) {
                        msgEl.textContent = 'You can browse all games without a key — Hubcap shows which ones have manifests ready to download.';
                    }
                }
            } catch(e) {
                Components.showToast('error', 'Failed to parse search results');
            }
        });
    }

    function onApiKeyAvailable(key) {
        _apiKeyConnected = true;
        if (_initialized) {
            _fetchGames();
        }
    }

    function onPageEnter() {
        init();
        _page = 1;
        Bridge.callSync('get_setting', 'hide_store_images', function(val) {
            _imagesHidden = (val === 'True');
            Components.setHideImages(_imagesHidden);
            var btn = document.getElementById('store-toggle-images');
            if (btn) btn.classList.toggle('active', _imagesHidden);
        });
        _fetchGames();
    }

    function _fetchGames() {
        _showLoading();
        var offset = (_page - 1) * _perPage;
        var effectiveQuery = _activeGenre
            ? (_searchQuery ? _searchQuery + ' ' + _activeGenre : _activeGenre)
            : _searchQuery;
        Bridge.call('search_games', effectiveQuery, offset, _perPage, _sortBy);
    }

    function _renderGames(games) {
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
        var pagination = document.getElementById('store-pagination');

        if (grid) grid.innerHTML = '';
        if (list) list.innerHTML = '';

        if (games.length === 0) {
            if (grid) grid.innerHTML = '<div class="empty-state"><p>No games found. Try a different search.</p></div>';
            if (pagination) pagination.classList.add('hidden');
            return;
        }

        games.forEach(function(game, index) {
            if (grid) grid.appendChild(Components.createGameCard(game, { index: index }));
            if (list) list.appendChild(Components.createGameListItem(game));
        });

        if (pagination) pagination.classList.remove('hidden');
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
    }

    function _showLoading() {
        var loading = document.getElementById('store-loading');
        var grid = document.getElementById('store-grid');
        var list = document.getElementById('store-list');
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

    return {
        init: init,
        onPageEnter: onPageEnter,
        onApiKeyAvailable: onApiKeyAvailable
    };
})();
