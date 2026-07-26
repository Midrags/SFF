# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

"""
QWebChannel bridge — exposes Python backend functions to the web UI.

All I/O methods dispatch to QThread workers and emit results via pyqtSignal.
Only trivial getters use synchronous result= slots.
"""

import json
import logging
import os
import re
import shutil
import ssl as _ssl
import subprocess
import sys
import unicodedata as _ud
from functools import lru_cache

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_DDMOD_PCT_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%\s")
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)

from sff.game_list_fallback import (
    enrich_game_dict,
    has_fallback_data,
    search_games_json,
    search_games_by_tag,
    search_name_fallback,
    ensure_loaded as _ensure_fallback_loaded,
)

_SSL_CTX = None


def _get_ssl_ctx():
    global _SSL_CTX
    if _SSL_CTX is None:
        try:
            import certifi as _certifi
            _SSL_CTX = _ssl.create_default_context(cafile=_certifi.where())
        except Exception:
            _SSL_CTX = _ssl.create_default_context()
    return _SSL_CTX


class _Worker(QObject):
    """Generic thread worker for async bridge operations."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("Worker error: %s", e)
            self.error.emit(str(e))
            self.finished.emit(None)


def _should_show_software() -> str:
    """Return ``"1"`` when STORE_SHOW_SOFTWARE is ON, ``"0"`` when OFF.

    A17 widens the Store list filter to ``{game, application}``. Default
    is ON: missing / empty / True / "True" all resolve to ``"1"``. Only
    an explicit ``False`` / ``"False"`` clamps the list back to games.
    Both Store list callsites in this module share this single helper.
    """
    try:
        from sff.storage.settings import get_setting as _get
        from sff.structs import Settings
        val = _get(Settings.STORE_SHOW_SOFTWARE)
    except Exception:
        return "1"
    if val is False or val == "False" or val == "false" or val == "0":
        return "0"
    return "1"


_NSFW_NAME_RE = re.compile(r"(hentai|futanari|furry|sex)", re.IGNORECASE)
_KNOWN_MACOS_ONLY_APPIDS = {12250}


def _looks_nsfw_by_name(name) -> bool:
    return bool(_NSFW_NAME_RE.search(str(name or "")))


def _store_blocks_nsfw() -> bool:
    try:
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        val = get_setting(Settings.STORE_BLOCK_NSFW)
    except Exception:
        return False
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _filter_store_nsfw_rows(rows):
    return [
        row for row in (rows or [])
        if not row.get("nsfw") and not _looks_nsfw_by_name(row.get("name"))
    ]


def _collect_steamidra_managed_sources(steam_path, saved_lua_root=None) -> dict[str, list[str]]:
    managed_sources: dict[str, set[str]] = {}

    def _remember(appid: str, source: str):
        appid = str(appid or "").strip()
        if appid.isdigit():
            managed_sources.setdefault(appid, set()).add(source)

    def _scan_lua_root(root: Path, source: str):
        if not root.exists():
            return
        for lua_path in list(root.glob("*.lua")) + list(root.glob("*/*.lua")):
            try:
                if lua_path.name.lower() in ("00_letupdate_override.lua", "letupdate_override.lua"):
                    continue
                if lua_path.stem.isdigit():
                    _remember(lua_path.stem, source)
                    continue
                text = lua_path.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r"addappid\s*\(\s*(\d+)", text, re.IGNORECASE)
                if match:
                    _remember(match.group(1), source)
            except Exception:
                continue

    if saved_lua_root is None:
        from sff.utils import root_folder
        saved_lua_root = root_folder(outside_internal=True) / "saved_lua"
    _scan_lua_root(Path(saved_lua_root), "saved_lua")
    cwd_saved = Path.cwd() / "saved_lua"
    if cwd_saved != Path(saved_lua_root).resolve() and cwd_saved.exists():
        _scan_lua_root(cwd_saved, "saved_lua")
    if steam_path:
        _scan_lua_root(Path(steam_path) / "config" / "stplug-in", "stplug-in")
    return {appid: sorted(sources) for appid, sources in managed_sources.items()}


class WebBridge(QObject):
    """QObject subclass registered via QWebChannel.
    JS accesses this as ``channel.objects.bridge``.
    """

    # --- Signals (Python → JS) ---
    search_results = pyqtSignal(str)
    depot_history_results = pyqtSignal(str)
    download_progress = pyqtSignal(str)
    task_finished = pyqtSignal(str)
    task_progress = pyqtSignal(str)
    log_message = pyqtSignal(str)
    lc_progress = pyqtSignal(str)

    def __init__(self, ui, steam_path, parent=None):
        super().__init__(parent)
        self._ui = ui
        self._steam_path = Path(steam_path) if steam_path else None
        self._active_library = None
        self._api_key = None
        self._store_client = None
        self._hubcap_unavailable = False
        self._get_store_client()
        self._hubcap_check_timer = QTimer(self)
        self._hubcap_check_timer.setInterval(15_000)
        self._hubcap_check_timer.timeout.connect(self._check_hubcap_key)
        self._hubcap_check_timer.start()
        self._workers = []  # prevent GC of running workers
        self._threads = []  # prevent GC of running QThreads
        # 6.2.5: per-app update-available state cache. Populated by
        # check_game_update() on success. The badge/popover code
        # reads through get_game_update_state(). Keys are str(app_id).
        # Network/CM failures leave the prior entry intact.
        self._update_state_cache: dict[str, dict] = {}
        self._provider_timer = QTimer(self)
        self._provider_timer.setInterval(60 * 60 * 1000)
        self._provider_timer.timeout.connect(self._maybe_auto_contribute_provider)
        self._provider_timer.start()
        QTimer.singleShot(3000, self._maybe_auto_contribute_provider)
        self._provider_cache_refreshing = False
        self._provider_cache_timer = QTimer(self)
        self._provider_cache_timer.setInterval(10 * 60 * 1000)
        self._provider_cache_timer.timeout.connect(self._maybe_auto_refresh_provider_cache)
        self._provider_cache_timer.start()
        QTimer.singleShot(8000, self._maybe_auto_refresh_provider_cache)
        self._library_image_cache: "_OrderedDict[str, str]" = _OrderedDict()
        self._LIBRARY_IMAGE_CACHE_MAX = 500

        # Pre-cache installed games on a background thread so
        # get_installed_games (a sync @pyqtSlot) never blocks the main thread.
        self._installed_games_cache = None
        self._games_prefetch_timer = QTimer(self)
        self._games_prefetch_timer.setInterval(120_000)
        self._games_prefetch_timer.timeout.connect(self._prefetch_installed_games)
        self._games_prefetch_timer.start()
        QTimer.singleShot(2000, self._prefetch_installed_games)

        # Preload fallback data (games.json + name cache) at startup
        # so the first Store tab search doesn't wait 9s for the
        # download.  Runs deferred so the UI loads first.
        self._preload_all_store_data()

    def _preload_all_store_data(self):
        """Warm cached store metadata without forcing visible network work.

        Deferred 1.5s after construction onto the Qt event loop (not a
        background thread) because ssl.create_default_context — called by
        game_list_fallback — segfaults on Windows when run concurrently
        with QtWebEngine's render process spawn during window.show().
        """
        from PyQt6.QtCore import QTimer as _QTimer

        def _do():
            try:
                from sff.game_list_fallback import ensure_loaded
                ensure_loaded(force=False)
                logger.debug("Preload: cached store metadata warmed")
            except Exception as e:
                logger.debug("Preload: store data preload failed: %s", e)

        _QTimer.singleShot(1500, _do)

    # ── helpers ──────────────────────────────────────────────────

    def _run_async(self, func, *args, on_done=None, on_error=None, **kwargs):
        """Spawn a QThread worker for the given function."""
        # Forward stdout/stderr from the background thread to the parent window's
        # StreamEmitter so that print() output appears in the Modern UI log panel.
        # Classic UI's _start_worker does this too; we mirror that behaviour here.
        parent = self.parent()
        stream = getattr(parent, '_stream_emitter', None) if parent else None
        if stream is not None:
            _orig_func = func
            def func(*_a, **_kw):   # noqa: E731
                import sys as _sys
                _old_out, _old_err = _sys.stdout, _sys.stderr
                _sys.stdout = stream
                _sys.stderr = stream
                try:
                    return _orig_func(*_a, **_kw)
                finally:
                    _sys.stdout = _old_out
                    _sys.stderr = _old_err
        thread = QThread()
        worker = _Worker(func, *args, **kwargs)
        worker.moveToThread(thread)

        def _cleanup(result):
            thread.quit()
            thread.wait()
            if worker in self._workers:
                self._workers.remove(worker)
            if thread in self._threads:
                self._threads.remove(thread)
            if on_done:
                on_done(result)

        def _on_error(msg):
            thread.quit()
            thread.wait()
            if worker in self._workers:
                self._workers.remove(worker)
            if thread in self._threads:
                self._threads.remove(thread)
            if on_error:
                on_error(msg)
            else:
                self.task_finished.emit(json.dumps({
                    "task": "unknown", "success": False, "message": msg
                }))

        worker.finished.connect(_cleanup)
        worker.error.connect(_on_error)
        thread.started.connect(worker.run)
        self._workers.append(worker)
        self._threads.append(thread)
        thread.start()

    def _emit_task_result(self, task_name, success, message="", **extra):
        data = {"task": task_name, "success": success, "message": message}
        data.update(extra)
        self.task_finished.emit(json.dumps(data))

    @pyqtSlot()
    def signal_ready(self):
        parent = self.parent()
        if parent and hasattr(parent, "dismiss_splash"):
            parent.dismiss_splash()

    @pyqtSlot()
    def window_minimize(self):
        parent = self.parent()
        if parent:
            parent.showMinimized()

    @pyqtSlot()
    def window_maximize(self):
        parent = self.parent()
        if parent:
            if parent.windowState() & Qt.WindowState.WindowMaximized:
                parent.showNormal()
            else:
                parent.showMaximized()

    @pyqtSlot(result=str)
    def window_is_maximized(self):
        parent = self.parent()
        if parent:
            return json.dumps({"maximized": bool(parent.windowState() & Qt.WindowState.WindowMaximized)})
        return json.dumps({"maximized": False})

    @pyqtSlot()
    def window_close(self):
        parent = self.parent()
        if parent:
            parent.close()

    @pyqtSlot()
    def toggle_ui(self):
        parent = self.parent()
        if parent and hasattr(parent, "_toggle_web_ui"):
            parent._toggle_web_ui()

    def _maybe_auto_contribute_provider(self):
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            from sff.lua.provider import contributor_due

            enabled = get_setting(Settings.PROVIDER_CONTRIBUTE_KEYS)
            if enabled and contributor_due():
                self.provider_contribute_submit("auto")
        except Exception as exc:
            logger.debug("provider auto-contribute check failed: %s", exc)

    def _maybe_auto_refresh_provider_cache(self):
        if getattr(self, "_provider_cache_refreshing", False):
            return
        try:
            from sff.lua.provider import provider_update_due, download_provider_update

            if not provider_update_due():
                return
            self._provider_cache_refreshing = True

            def _do():
                return download_provider_update()

            def _on_done(result):
                self._provider_cache_refreshing = False
                result = result or {"ok": False, "errors": ["unknown"]}
                ok = bool(result.get("ok"))
                msg = (
                    f"Provider updated from {result.get('url', '')} ({result.get('count', 0)} entries)"
                    if ok else
                    "Provider update failed: " + "; ".join(result.get("errors") or [])
                )
                logger.info("provider cache auto-refresh: %s", msg)
                self._emit_task_result("provider_update", ok, msg, background=True, **result)

            self._run_async(_do, on_done=_on_done)
        except Exception as exc:
            self._provider_cache_refreshing = False
            logger.debug("provider cache auto-refresh check failed: %s", exc)

    def _auto_update_was_registered(self, app_id) -> bool:
        try:
            from sff.auto_update_defaults import steam_game_has_pins

            return steam_game_has_pins(self._steam_path, app_id)
        except Exception:
            return False

    def _apply_auto_update_default(self, app_id, was_registered=False):
        try:
            from sff.auto_update_defaults import apply_new_game_update_default

            result = apply_new_game_update_default(
                self._steam_path,
                app_id,
                was_registered=bool(was_registered),
                log=lambda msg: logger.info(msg),
            )
            if result.get("applied"):
                self._installed_games_cache = None
        except Exception as exc:
            logger.debug("auto-update default skipped for %s: %s", app_id, exc)

    def _get_store_client(self):
        if self._store_client is None and not self._hubcap_unavailable:
            if not self._api_key:
                try:
                    from sff.storage.settings import get_setting
                    from sff.structs import Settings
                    key = get_setting(Settings.HUBCAP_KEY)
                    if key and isinstance(key, str) and key.strip():
                        self._api_key = key.strip()
                except Exception:
                    pass
            if self._api_key:
                from sff.store_browser import StoreApiClient
                self._store_client = StoreApiClient(self._api_key)
        return self._store_client if not self._hubcap_unavailable else None

    def _check_hubcap_key(self):
        if not self._hubcap_unavailable:
            return
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            key = get_setting(Settings.HUBCAP_KEY)
            if key and isinstance(key, str) and key.strip() and key.strip() != (self._api_key or ""):
                self._api_key = key.strip()
                self._store_client = None
                self._hubcap_unavailable = False
                logger.debug("Hubcap key detected, re-enabling store client")
        except Exception:
            pass

    # ── ASYNC slots — dispatch to QThread ────────────────────────

    @pyqtSlot()
    def refresh_store_metadata(self):
        def _do():
            return _ensure_fallback_loaded(force=False)

        def _on_done(ok):
            self._emit_task_result(
                "store_metadata",
                bool(ok),
                "",
                has_fallback_data=has_fallback_data(),
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def warm_store_metadata(self):
        self.refresh_store_metadata()

    @pyqtSlot(str, int, int, str, str)
    @pyqtSlot(str, int, int, str, str, str)
    def search_games(self, query, offset, per_page, sort_by='updated', tag='', request_id=''):
        """Search Steam catalog (primary), then merge fresh hits from
        Hubcap on top.

        Steam's IStoreService catalog is the authoritative source for
        active titles. Hubcap fills in delisted classics (the original
        GTA: San Andreas, GTA Legacy Collection, etc) and exposes a
        manifest-status overlay for matched titles. Both /library and
        /search are queried, and the user query is alias-expanded
        ("gta" -> "grand theft auto", "re" -> "resident evil", ...)
        before being sent to Hubcap so abbreviated typing still hits
        full Hubcap names. Hubcap-only hits are tagged with
        source='hubcap' so the UI can label them. When Steam returns
        nothing, Hubcap becomes the primary result set.

        When tag is set with no query, uses games.json tag search instead.
        """
        def _do():
            block_nsfw = _store_blocks_nsfw()
            if block_nsfw and _looks_nsfw_by_name(query):
                return {
                    "games": [],
                    "total": 0,
                    "has_hubcap": bool(self._get_store_client()),
                    "has_fallback_data": has_fallback_data(),
                }

            # When filtering by tag with no text query, use games.json tag search
            if tag and not query:
                result = search_games_by_tag(tag, 0, 10000)
                rows = result.get("games", [])
                if block_nsfw:
                    rows = _filter_store_nsfw_rows(rows)
                result["total"] = len(rows)
                result["games"] = rows[offset:offset + per_page]
                result['has_hubcap'] = False
                return result

            # Steam catalog is always the primary source.
            result = _search_steam_catalog(query, offset, per_page, sort_by=sort_by or 'updated')
            result.pop('fallback', None)
            if not has_fallback_data():
                _ensure_fallback_loaded()
            for g in result.get('games', []) or []:
                enrich_game_dict(g)

            client = self._get_store_client()
            if not client:
                result['has_hubcap'] = False
                client = None

            result['has_hubcap'] = bool(client) and not self._hubcap_unavailable
            hubcap_hits = {}
            if client and not self._hubcap_unavailable:
                hubcap_hits = {}
                hubcap_queries = []
                if query:
                    hubcap_queries.append(query)
                    alts = _alias_expanded_queries(query)
                    if alts:
                        for alt in alts:
                            if alt.lower() != query.lower():
                                hubcap_queries.append(alt)
                                break
                else:
                    hubcap_queries = [None]
                hubcap_queried = False
                try:
                    for q in hubcap_queries:
                        try:
                            page = client.get_library(
                                limit=200, offset=0,
                                search=q,
                                sort_by=sort_by or 'updated',
                            )
                            hubcap_queried = True
                            for hg in page.games or []:
                                if hg.app_id and hg.app_id not in hubcap_hits:
                                    hubcap_hits[hg.app_id] = hg
                        except Exception as e:
                            logger.debug("Hubcap /library failed for %r: %s", q, e)
                        if q:
                            try:
                                search_hits = client.search_library(
                                    q, limit=50, search_by_appid=False,
                                )
                                hubcap_queried = True
                                for hg in search_hits or []:
                                    if hg.app_id and hg.app_id not in hubcap_hits:
                                        hubcap_hits[hg.app_id] = hg
                            except Exception as e:
                                logger.debug("Hubcap /search failed for %r: %s", q, e)
                except Exception as e:
                    logger.warning("Hubcap merge step crashed: %s", e)
                # Hubcap was hit but returned nothing — key is invalid or expired.
                if hubcap_queried and not hubcap_hits:
                    self._hubcap_unavailable = True
                    logger.debug("Hubcap disabled for session (no results from valid query)")
            if not hubcap_hits:
                logger.debug(
                    "search_games: query=%r yielded no Hubcap hits across %d variant(s)",
                    query, len(queries) if 'queries' in dir() else 1,
                )
                hubcap_hits = {}

            # Structural DLC + platform filter for Hubcap-only candidates.
            # Three drop signals, all derived from Steam's GetItems:
            #
            #   1. parent_appid is set  -> Steam tags this as DLC of
            #      another app. Drops Cyberpunk Phantom Liberty,
            #      RE6 Predator/Onslaught modes, RE Op Raccoon Echo
            #      Six Expansion 1, Elden Ring Shadow of the Erdtree,
            #      etc.
            #   2. delisted_blank is True  -> GetItems returned no
            #      name and no type. Steam strips public metadata
            #      from removed DLC content (RE6 Mercenaries No
            #      Mercy, RE5 Stories Bundle, RE4 weapon tickets).
            #      Real classic delisted GAMES still return
            #      name + type=0 (verified for GTA SA classic, Dark
            #      Souls PTDE, Resident Evil HD), so this signal is
            #      reliably DLC content.
            #   3. platforms set excludes "windows"  -> macOS-only or
            #      Linux-only port (e.g. appid 12250 GTA SA Mac).
            #
            # No name keywords. Steam-confirmed appids that already
            # appear in the Steam catalog result skip the filter
            # entirely so we trust Steam's own listing.
            steam_ids = {g.get('app_id') for g in result.get('games', []) or []}
            extra_ids = [aid for aid in hubcap_hits.keys() if aid not in steam_ids]
            meta_map = _fetch_steam_platforms(extra_ids)
            non_windows_filtered = 0
            dlc_filtered = 0
            kept_hubcap = {}
            for app_id, hg in hubcap_hits.items():
                if int(app_id or 0) in _KNOWN_MACOS_ONLY_APPIDS:
                    non_windows_filtered += 1
                    continue
                if app_id in steam_ids:
                    kept_hubcap[app_id] = hg
                    continue
                meta = meta_map.get(app_id) or {}
                tags = meta.get("platforms") or {"_unknown"}
                parent_appid = meta.get("parent_appid")
                delisted_blank = bool(meta.get("delisted_blank"))
                store_type = (meta.get("type") or "").lower()

                # search filter logs are gated behind SFF_VERBOSE_FILTER=1.
                # default off because the live debug.log was getting
                # thousands of identical "filtered Hubcap appid=..." lines
                # per tab switch and burying real errors.
                import os as _os_filt
                _verbose_filter = _os_filt.environ.get("SFF_VERBOSE_FILTER") == "1"

                # Structural DLC signals.
                if parent_appid:
                    # Re-releases (Enhanced / Definitive / GOTY /
                    # Director's Cut) hang off the base appid the same
                    # way DLC does, but ship as standalone games.
                    # Steam tags them with `type: 14` (rerelease).
                    # Keep those; drop everything else with a parent.
                    if store_type == "rerelease":
                        kept_hubcap[app_id] = hg
                        continue
                    dlc_filtered += 1
                    if _verbose_filter:
                        logger.debug(
                            "search_games: filtered Hubcap appid=%s name=%r parent=%s",
                            app_id, hg.name, parent_appid,
                        )
                    continue
                if delisted_blank:
                    dlc_filtered += 1
                    if _verbose_filter:
                        logger.debug(
                            "search_games: filtered Hubcap appid=%s name=%r (delisted, no Steam metadata)",
                            app_id, hg.name,
                        )
                    continue
                # Belt-and-suspenders type drop. parent_appid covers
                # type=2/4 already. This catches edge cases where
                # GetItems returns type=5/7/9-15 (advertising, tool,
                # video, music) without a parent appid. Re-releases
                # (`type: 14` with parent set) are handled above.
                if store_type and store_type not in ("game", "demo", "mod", "rerelease"):
                    dlc_filtered += 1
                    if _verbose_filter:
                        logger.debug(
                            "search_games: filtered Hubcap appid=%s name=%r type=%s",
                            app_id, hg.name, store_type,
                        )
                    continue

                # Platform check.
                if "_unknown" not in tags:
                    _is_win = sys.platform == "win32"
                    if _is_win and "windows" not in tags:
                        non_windows_filtered += 1
                        if _verbose_filter:
                            logger.debug(
                                "search_games: filtered Hubcap appid=%s name=%r platforms=%s",
                                app_id, hg.name, sorted(tags),
                            )
                        continue
                    if not _is_win and "windows" not in tags and "linux" not in tags:
                        non_windows_filtered += 1
                        if _verbose_filter:
                            logger.debug(
                                "search_games: filtered Hubcap appid=%s name=%r platforms=%s",
                                app_id, hg.name, sorted(tags),
                            )
                        continue
                    # on Linux, tag win-only games with a badge
                    if not _is_win and "linux" not in tags and "windows" in tags:
                        hg._plat_label = "[Win]"
                    elif not _is_win and "linux" in tags and "windows" not in tags:
                        hg._plat_label = "[Linux]"

                kept_hubcap[app_id] = hg
            hubcap_hits = kept_hubcap

            try:
                logger.debug(
                    "search_games: query=%r got %d Steam + %d Hubcap hit(s) across %d variant(s) (%d DLC filtered, %d non-windows filtered)",
                    query, len(result.get('games', [])), len(hubcap_hits),
                    len(queries), dlc_filtered, non_windows_filtered,
                )
            except (NameError, UnboundLocalError):
                logger.debug(
                    "search_games: query=%r got %d Steam + %d Hubcap hit(s)",
                    query, len(result.get('games', [])), len(hubcap_hits),
                )

            # Overlay Hubcap status on Steam rows that share an app_id.
            for g in result.get('games', []) or []:
                hg = hubcap_hits.get(g.get('app_id'))
                if not hg:
                    continue
                if hg.status:
                    g['status'] = hg.status
                if hg.last_updated:
                    g['last_updated'] = hg.last_updated
                if hg.size:
                    g['size'] = hg.size

            # Build the Hubcap-only tail. The merged result behaves
            # like one virtual list: [steam_total Steam rows] then
            # [len(extras) Hubcap rows]. Pagination has to slice that
            # combined list per page; otherwise every page repeats
            # the full Hubcap tail (the bug we used to ship).
            seen_ids = {g.get('app_id') for g in result.get('games', []) or []}
            extras = []
            for app_id, hg in hubcap_hits.items():
                if app_id in seen_ids:
                    continue
                extras.append({
                    'app_id': hg.app_id,
                    'name': hg.name,
                    'status': hg.status or '',
                    'last_updated': hg.last_updated or '',
                    'size': hg.size or '',
                    'image_url': '',
                    'source': 'hubcap',
                    'platform_label': getattr(hg, '_plat_label', ''),
                })

            steam_total = int(result.get('total') or 0)
            steam_rows = result.get('games') or []
            extras_total = len(extras)

            # Enrich ALL rows with games.json metadata (DRM, tags, NSFW,
            # header_image, DLC). This runs on every search but the
            # underlying cache is lazy-loaded and re-checks mtime.
            _ensure_fallback_loaded()
            for g in steam_rows:
                enrich_game_dict(g)
            for g in extras:
                enrich_game_dict(g)

            # Merge games.json + name-cache results so delisted/removed
            # games show up even when Steam + Hubcap return active titles.
            # Use alias expansion so "gta" -> "grand theft auto" hits
            # titles stored under their full name. Runs unconditionally;
            # search_games_json / search_name_fallback return empty lists
            # when the underlying data hasn't been loaded.
            if query:
                try:
                    queries = _alias_expanded_queries(query) or [query]
                    gj_extra = {}
                    for q in queries:
                        try:
                            for g in search_games_json(q, limit=500):
                                if g.get('app_id') and g['app_id'] not in gj_extra:
                                    gj_extra[g['app_id']] = g
                        except Exception:
                            pass
                        try:
                            for g in search_name_fallback(q, limit=500):
                                if g.get('app_id') and g['app_id'] not in gj_extra:
                                    gj_extra[g['app_id']] = g
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug("search_games: fallback merge failed: %s", e)
                    gj_extra = {}
                if gj_extra:
                    existing_ids = {g.get('app_id') for g in steam_rows if g.get('app_id')}
                    existing_ids.update(e.get('app_id') for e in extras if e.get('app_id'))
                    for app_id in list(gj_extra.keys()):
                        if app_id not in existing_ids:
                            g = gj_extra[app_id]
                            enrich_game_dict(g)
                            steam_rows.append(g)
                            steam_total += 1
                            existing_ids.add(app_id)
                    if gj_extra:
                        logger.debug("search_games: merged %d extra games from JSON sources", len(gj_extra))

            # Platform filter for ALL search result rows. Uses Steam GetItems
            # platform data (cached in _STEAM_PLATFORM_CACHE) to drop
            # macOS-only games and tag Linux-specific / Windows-specific titles
            # with a readable label for Linux users.
            _is_win = sys.platform == "win32"
            _all_aids = []
            for g in steam_rows:
                aid = g.get('app_id')
                if aid:
                    _all_aids.append(aid)
            for e in extras:
                aid = e.get('app_id')
                if aid:
                    _all_aids.append(aid)
            if _all_aids:
                _plat_map = _fetch_steam_platforms(_all_aids)
                if _plat_map:
                    _filtered_rows = []
                    for g in steam_rows:
                        aid = g.get('app_id')
                        if int(aid or 0) in _KNOWN_MACOS_ONLY_APPIDS:
                            continue
                        meta = _plat_map.get(aid) if aid else None
                        tags = meta.get("platforms") if meta else {"_unknown"}
                        if "_unknown" in tags:
                            g['platform_label'] = ''
                            _filtered_rows.append(g)
                            continue
                        has_win = "windows" in tags
                        has_lin = "linux" in tags
                        has_mac = "macos" in tags
                        if has_mac and not has_win and not has_lin:
                            continue
                        if _is_win:
                            if not has_win:
                                continue
                            g['platform_label'] = ''
                        else:
                            if not has_win and not has_lin:
                                continue
                            if has_lin and not has_win:
                                g['platform_label'] = '[Linux Only]'
                            elif has_win and not has_lin:
                                g['platform_label'] = '[Windows Only]'
                            else:
                                g['platform_label'] = ''
                        _filtered_rows.append(g)
                    steam_rows = _filtered_rows
                    steam_total = len(steam_rows)
                    _filtered_extras = []
                    for e in extras:
                        aid = e.get('app_id')
                        if int(aid or 0) in _KNOWN_MACOS_ONLY_APPIDS:
                            continue
                        meta = _plat_map.get(aid) if aid else None
                        tags = meta.get("platforms") if meta else {"_unknown"}
                        if "_unknown" in tags:
                            e['platform_label'] = e.get('platform_label', '')
                            _filtered_extras.append(e)
                            continue
                        has_win = "windows" in tags
                        has_lin = "linux" in tags
                        has_mac = "macos" in tags
                        if has_mac and not has_win and not has_lin:
                            continue
                        if _is_win and not has_win:
                            continue
                        if not _is_win and not has_win and not has_lin:
                            continue
                        _filtered_extras.append(e)
                    extras = _filtered_extras
                    extras_total = len(extras)

            # Merge into one list, dedupe, then filter/sort/paginate once.
            merged = []
            seen_merged = set()
            for row in list(steam_rows) + list(extras):
                aid = row.get('app_id')
                if not aid or aid in seen_merged:
                    continue
                seen_merged.add(aid)
                merged.append(row)

            # Fetch Steam content descriptors only when games.json did not
            # provide NSFW/art metadata.
            if merged and not has_fallback_data():
                try:
                    _meta_img, _, _meta_nsfw = _fetch_steam_image_urls([
                        g['app_id'] for g in merged if g.get('app_id')
                    ])
                except Exception as e:
                    logger.debug("search_games: Steam metadata fetch failed: %s", e)
                    _meta_img, _meta_nsfw = {}, {}
                for g in merged:
                    aid = g.get('app_id')
                    if aid and aid in _meta_nsfw:
                        g['nsfw'] = _meta_nsfw[aid]
                    if aid and not g.get('image_url'):
                        g['image_url'] = _meta_img.get(aid) or ''

            # Filter by tag when both tag and text query are set.
            if tag and query:
                tag_lower = tag.lower().strip()
                merged = [
                    g for g in merged
                    if tag_lower in [t.lower() for t in g.get('tags', [])]
                ]

            if block_nsfw:
                merged = _filter_store_nsfw_rows(merged)

            if not merged:
                # Both Steam catalog and Hubcap came back empty. Try
                # games.json + name-cache directly as a last resort so
                # the store tab never shows a completely blank page.
                if has_fallback_data():
                    _last_resort = []
                    if query:
                        for g in search_games_json(query, limit=500):
                            _last_resort.append(g)
                        for g in search_name_fallback(query, limit=500):
                            _last_resort.append(g)
                    else:
                        for g in search_games_json("", limit=200):
                            _last_resort.append(g)
                    if _last_resort:
                        seen_lr = set()
                        _deduped = []
                        for g in _last_resort:
                            aid = g.get('app_id')
                            if not aid or aid in seen_lr:
                                continue
                            seen_lr.add(aid)
                            enrich_game_dict(g)
                            _deduped.append(g)
                        if _deduped:
                            _deduped.sort(key=lambda g: _store_search_score(
                                query,
                                g.get('name', ''),
                                g.get('app_id'),
                            ))
                            result['games'] = _deduped[offset:offset + per_page]
                            result['total'] = len(_deduped)
                            result['fallback_source'] = 'games_json'
                            result['has_fallback_data'] = True
                return result

            merged.sort(key=lambda g: _store_search_score(query, g.get('name', ''), g.get('app_id')))
            total = len(merged)
            if not query and not tag:
                total = max(total, int(result.get('total') or 0))
            page_games = merged[0:per_page]
            if not result.get('games') and any(g.get('source') == 'hubcap' for g in page_games):
                result['fallback_source'] = 'hubcap'
            result['games'] = page_games
            result['total'] = total

            result['has_fallback_data'] = True
            # User searched for something specific but nothing matched.
            # Force-refresh the fallback cache in background so next
            # search picks up fresh game data.
            if query and not merged:
                QTimer.singleShot(200, lambda: _ensure_fallback_loaded(force=True))
            return result

        def _on_done(data):
            self.search_results.emit(json.dumps(_attach_store_request_id(data, request_id)))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, bool)
    def fetch_depot_history(self, app_id, force_refresh):
        """Fetch depot/manifest history for a game. Emits depot_history_results."""
        def _progress(msg):
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": msg, "progress": -1
            }))

        def _do():
            from sff.manifest.depot_history import get_depots_for_app, group_by_version, get_build_ids
            depots = get_depots_for_app(app_id, force_refresh=force_refresh, progress_cb=_progress)
            build_ids = get_build_ids(app_id)
            groups = group_by_version(depots, build_ids=build_ids)
            result = []
            for group in groups:
                result.append({
                    "label": group.label,
                    "date": group.date,
                    "branch": group.branch,
                    "source": group.source,
                    "build_id": group.build_id,
                    "entries": [
                        {"depot_id": str(d), "manifest_id": str(m)}
                        for d, m in group.entries
                    ],
                })
            return result

        def _on_done(data):
            self.depot_history_results.emit(json.dumps(data or []))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def download_game_fastest(self, app_id):
        """Platform-aware fastest download (auto-selects source).
        Windows: prompt-free 11-step pipeline mirroring process_lua_full().
        Linux: auto-selects latest manifests, wraps process_from_store().
        Emits download_progress + task_finished signals."""
        if not app_id or not app_id.strip().isdigit():
            self._emit_task_result("download_fastest", False, f"Invalid App ID: '{app_id}'")
            return
        def _do():
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Starting", "progress": 0
            }))

            if sys.platform == "win32":
                return self._run_windows_fastest(app_id)
            else:
                return self._run_linux_fastest(app_id)

        def _on_done(result):
            success = result is True
            if success:
                QTimer.singleShot(1000, self._maybe_auto_contribute_provider)
            self._emit_task_result(
                "download_fastest",
                success,
                f"Download {'completed' if success else 'failed'} for App {app_id}",
                app_id=app_id,
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, str, str, str, str, str, str)
    @pyqtSlot(str, str, str, str, str, str)
    @pyqtSlot(str, str, str, str, str)
    @pyqtSlot(str, str, str, str)
    @pyqtSlot(str, str, str)
    def download_game_with_source(self, app_id, source, request_update='0', lua_path='', manifest_folder='', branch='', file_type=''):
        """Fastest download with explicit source choice ('hubcap', 'oureveryday', 'ryuu', or 'local').
        Emits download_progress + task_finished signals.
        When source='local', lua_path is required (path to .lua/.zip/.rar/.7z),
        manifest_folder is optional (path to folder with .manifest files)."""
        if not app_id or not app_id.strip().isdigit():
            self._emit_task_result("download_fastest", False, f"Invalid App ID: '{app_id}'")
            return
        def _do():
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Starting", "progress": 0
            }))
            # Local source: bypass all API calls, import directly
            if source == "local":
                return self._run_local_import(app_id, lua_path, manifest_folder)
            if sys.platform == "win32":
                return self._run_windows_fastest(app_id, source=source, request_update=(request_update == '1'), branch=branch, file_type=file_type)
            else:
                return self._run_linux_fastest(app_id)

        def _on_done(result):
            success = result is True
            self._emit_task_result(
                "download_fastest",
                success,
                f"Download {'completed' if success else 'failed'} for App {app_id}",
                app_id=app_id,
            )

        self._run_async(_do, on_done=_on_done)

    def _run_local_import(self, app_id, lua_path, manifest_folder=''):
        """Import a local Lua/archive without any provider API calls.
        Extracts lua + manifests, installs to Steam, writes ACF, registers library entry."""
        try:
            from pathlib import Path as _Path
            from sff.lua.manager import parse_lua_contents
            from sff.steam_tools_compat import install_lua_to_steam
            from sff.lua.writer import ACFWriter, ConfigVDFWriter
            from sff.storage.vdf import ensure_library_has_app
            from sff.zip import read_lua_from_zip

            steam_path = self._steam_path
            dest = _Path(self._active_library) if self._active_library else steam_path
            lua_file = _Path(lua_path) if lua_path else None
            if not steam_path or not dest:
                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Error: No Steam path/library selected", "progress": 0
                }))
                return False
            if not lua_file or not lua_file.exists():
                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": f"Error: Lua file not found: {lua_path}", "progress": 0
                }))
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Extracting local Lua...", "progress": 10
            }))

            lua_install_file = lua_file
            if lua_file.suffix.lower() in (".zip", ".rar", ".7z"):
                _dc = (steam_path / "depotcache") if steam_path else None
                lua_text = read_lua_from_zip(lua_file, decode=True, depotcache=_dc)
                if not lua_text:
                    self.download_progress.emit(json.dumps({
                        "app_id": app_id, "status": "Error: Could not find .lua file inside archive", "progress": 0
                    }))
                    return False
                saved_dir = _Path.cwd() / "saved_lua"
                saved_dir.mkdir(parents=True, exist_ok=True)
                lua_install_file = saved_dir / f"{app_id}.lua"
                lua_install_file.write_text(lua_text, encoding="utf-8")
            else:
                lua_text = lua_file.read_text(encoding="utf-8", errors="replace")
            parsed = parse_lua_contents(lua_text, lua_file)
            if not parsed:
                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Error: Failed to parse Lua", "progress": 0
                }))
                return False
            _auto_update_was_registered = self._auto_update_was_registered(app_id)

            # Copy manifests from manifest_folder if provided
            if manifest_folder:
                import shutil as _shutil
                from sff.utils import manifests_staging_dir
                staging = manifests_staging_dir()
                depotcache = steam_path / "depotcache"
                depotcache.mkdir(parents=True, exist_ok=True)
                mf_path = _Path(manifest_folder)
                if mf_path.exists() and mf_path.is_dir():
                    self.download_progress.emit(json.dumps({
                        "app_id": app_id, "status": "Staging manifests...", "progress": 20
                    }))
                    for mf in mf_path.glob("*.manifest"):
                        _shutil.copy2(mf, staging / mf.name)
                        _shutil.copy2(mf, depotcache / mf.name)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Installing Lua to Steam", "progress": 30
            }))
            install_lua_to_steam(steam_path, app_id, lua_install_file)
            self._apply_auto_update_default(app_id, _auto_update_was_registered)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Writing decryption keys", "progress": 40
            }))
            ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Setting up achievements", "progress": 50
            }))
            try:
                from sff.registry_access import set_stats_and_achievements
                set_stats_and_achievements(app_id)
            except Exception as exc:
                logger.debug("local import stats setup skipped: %s", exc)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Registering app ID", "progress": 60
            }))
            if hasattr(self._ui, "app_list_man") and self._ui.app_list_man:
                self._ui.app_list_man.add_ids(parsed)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Writing ACF", "progress": 70
            }))
            acf = ACFWriter(dest)
            acf.write_acf(parsed)
            if hasattr(acf, "patch_workshop_acf"):
                acf.patch_workshop_acf(parsed)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Registering library entry", "progress": 80
            }))
            ensure_library_has_app(steam_path, dest, app_id)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Complete", "progress": 100
            }))
            return True
        except Exception as exc:
            logger.exception("Local import failed: %s", exc)
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": f"Error: {exc}", "progress": 0
            }))
            return False

    def _run_windows_fastest(self, app_id, source='', request_update=False, branch='', file_type=''):
        """Prompt-free 11-step pipeline for Windows."""
        try:
            from sff.lua.choices import download_lua_direct
            from sff.lua.manager import parse_lua_contents
            from sff.lua.writer import ACFWriter, ConfigVDFWriter
            from sff.steam_tools_compat import install_lua_to_steam
            from sff.storage.vdf import ensure_library_has_app
            from sff.registry_access import set_stats_and_achievements
            from sff.structs import LuaEndpoint

            steam_path = self._steam_path
            lib_path = Path(self._active_library) if self._active_library else steam_path

            # Step 1: download lua
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Downloading Lua", "progress": 10
            }))
            if source == "hubcap":
                selected_source = LuaEndpoint.HUBCAP
            elif source == "oureveryday":
                selected_source = LuaEndpoint.OUREVERYDAY
            elif source == "ryuu":
                selected_source = LuaEndpoint.RYUU
            else:
                selected_source = LuaEndpoint.HUBCAP if self._api_key else LuaEndpoint.OUREVERYDAY
            # Download lua into the per-user backup folder, NOT into
            # <steam>/config/. install_lua_to_steam then copies it into
            # <steam>/config/stplug-in/. Writing to <steam>/config/ directly
            # left a stray <steam>/config/<app_id>.lua next to stplug-in/
            # that the Remove from Library helper never cleans up.
            saved_lua_root = Path.cwd() / "saved_lua"
            saved_lua_root.mkdir(exist_ok=True)
            lua_path = download_lua_direct(
                dest=saved_lua_root,
                app_id=app_id,
                source=selected_source,
                steam_path=steam_path,
                request_update=request_update,
            )
            if not lua_path:
                # Surface a clear failure to the UI so the bar doesnt sit at
                # 10% forever. download_lua_direct returns None on timeout
                # against the Steam CM (30s ceiling) or any other source
                # error. The user can switch source and retry.
                self.download_progress.emit(json.dumps({
                    "task": "download_fastest",
                    "app_id": app_id,
                    "status": (
                        "Lua download failed. Steam CM may be down or the "
                        "selected source returned nothing. Try a different "
                        "provider (Hubcap / oureveryday) and retry."
                    ),
                    "progress": 0,
                }))
                return False

            saved_lua = saved_lua_root
            backup_target = saved_lua / f"{app_id}.lua"
            try:
                if lua_path != backup_target:
                    shutil.copyfile(lua_path, backup_target)
            except Exception:
                pass

            # Step 2: parse lua
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Parsing Lua", "progress": 20
            }))
            lua_contents = lua_path.read_text(encoding="utf-8", errors="replace")
            parsed = parse_lua_contents(lua_contents, lua_path)
            if not parsed:
                return False
            _auto_update_was_registered = self._auto_update_was_registered(app_id)

            # Step 3: set stats and achievements (Windows only)
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Setting up achievements", "progress": 30
            }))
            try:
                set_stats_and_achievements(app_id)
            except Exception as e:
                logger.warning("set_stats_and_achievements failed: %s", e)

            # Step 4: register app ID for injection
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Registering app ID", "progress": 40
            }))
            if hasattr(self._ui, 'app_list_man') and self._ui.app_list_man:
                try:
                    self._ui.app_list_man.add_ids(parsed)
                except Exception as e:
                    logger.warning("add_ids failed: %s", e)

            # Step 5: write decryption keys
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Writing decryption keys", "progress": 50
            }))
            config_writer = ConfigVDFWriter(steam_path)
            try:
                config_writer.add_decryption_keys_to_config(parsed)
            except Exception as e:
                logger.warning("add_decryption_keys failed: %s", e)

            # Step 6: backup & install lua to Steam plugin dir
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Installing Lua to Steam", "progress": 60
            }))
            try:
                install_lua_to_steam(steam_path, app_id, lua_path)
                self._apply_auto_update_default(app_id, _auto_update_was_registered)
            except Exception as e:
                logger.warning("install_lua_to_steam failed: %s", e)

            # Step 7: write ACF + patch workshop ACF
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Writing ACF files", "progress": 70
            }))
            acf_writer = ACFWriter(lib_path)
            try:
                acf_writer.write_acf(parsed)
            except Exception as e:
                logger.warning("write_acf failed: %s", e)
            try:
                if hasattr(acf_writer, 'patch_workshop_acf'):
                    acf_writer.patch_workshop_acf(parsed)
            except Exception as e:
                logger.warning("patch_workshop_acf failed: %s", e)

            # Step 8: register in libraryfolders.vdf
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Registering in library", "progress": 80
            }))
            try:
                ensure_library_has_app(steam_path, lib_path, app_id)
            except Exception as e:
                logger.warning("ensure_library_has_app failed: %s", e)

            # Step 9: download manifests
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Downloading manifests", "progress": 85
            }))
            try:
                from sff.manifest.downloader import ManifestDownloader
                from sff.steam_client import create_provider_for_current_thread
                from sff.storage.settings import get_setting as _get_setting
                from sff.structs import Settings as _Settings
                _provider = create_provider_for_current_thread()
                _dl = ManifestDownloader(_provider, steam_path)
                _use_parallel = _get_setting(_Settings.USE_PARALLEL_DOWNLOADS)
                if _use_parallel:
                    _dl.download_manifests_parallel(parsed, auto_manifest=True)
                else:
                    _dl.download_manifests(parsed, auto_manifest=True)
            except Exception as e:
                logger.warning("download_manifests failed: %s", e)

            # Step 10: track in download manager
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Updating download tracker", "progress": 95
            }))
            if hasattr(self._ui, 'download_manager') and self._ui.download_manager:
                try:
                    dl_id = self._ui.download_manager.track_external(
                        app_id=app_id,
                        game_name=parsed.name if hasattr(parsed, 'name') else f"App {app_id}",
                    )
                    self._ui.download_manager.complete_external(dl_id, success=True)
                except Exception as e:
                    logger.warning("download tracking failed: %s", e)

            # Step 11: done
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Complete", "progress": 100
            }))
            return True

        except Exception as e:
            logger.exception("Windows fastest download failed: %s", e)
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": f"Error: {e}", "progress": 0
            }))
            return False

    def _run_linux_fastest(self, app_id):
        """Wraps process_from_store; distinguishes real, partial, and no-sls runs."""
        # Refuse to run when SLSSteam is not initialized; the old code returned
        # silently and the UI rendered 100% complete despite no work happening.
        sls_man = getattr(self._ui, "sls_man", None)
        if sls_man is None:
            self.download_progress.emit(json.dumps({
                "app_id": app_id,
                "status": "SLSSteam not initialized — cannot proceed",
                "progress": 0,
                "error": True,
            }))
            return False

        try:
            from sff.manifest.depot_history import get_depots_for_app
            from sff.structs import MainReturnCode

            depots = get_depots_for_app(app_id)
            manifest_override = {}
            for depot_id, entries in depots.items():
                if entries:
                    manifest_override[str(depot_id)] = str(entries[0].manifest_id)

            if not manifest_override:
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Downloading via DepotDownloader", "progress": 30
            }))

            from pathlib import Path as _Path
            lib_override = _Path(self._active_library) if self._active_library else self._steam_path
            result = self._ui.process_from_store(
                app_id=app_id,
                manifest_override=manifest_override,
                use_hubcap=bool(self._api_key),
                lib_path=lib_override,
            )

            # process_from_store on Linux + sls_man writes ACF and the library
            # entry, then returns LOOP_NO_PROMPT without running DepotDownloader.
            # Surface a partial-success status, nudge Steam, and skip the bogus
            # Complete/100 emit instead of pretending the download finished.
            if result is MainReturnCode.LOOP_NO_PROMPT:
                self.download_progress.emit(json.dumps({
                    "app_id": app_id,
                    "status": "ACF written, starting DDMod download...",
                    "progress": 50,
                }))
                return self._run_linux_ddmod_fallback(app_id, manifest_override, lib_override)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Complete", "progress": 100
            }))
            return True

        except Exception as e:
            logger.exception("Linux fastest download failed: %s", e)
            return False

    def _run_linux_ddmod_fallback(self, app_id, manifest_override, lib_path):
        """After writing the ACF, kick off DDMod to actually download files."""
        try:
            from sff.depot_downloader import get_ddmod_dll, run_download
            from sff.dotnet_utils import ensure_dotnet_9, find_dotnet
            dotnet = find_dotnet()
            if dotnet is None:
                return False
            dll = get_ddmod_dll()
            if not dll.exists():
                return False

            depots = list(manifest_override.keys()) if manifest_override else []
            if not depots:
                return False

            self.download_progress.emit(json.dumps({
                "app_id": str(app_id), "status": "Downloading via DDMod", "progress": 55
            }))

            game_data = {
                "appid": str(app_id),
                "name": f"App {app_id}",
                "depots": {d: {} for d in depots},
                "manifests": manifest_override or {},
            }
            ok, _size = run_download(
                game_data, depots, lib_path, lib_path,
                print_fn=lambda msg: logger.debug("DDMod: %s", msg),
            )
            if ok:
                self.download_progress.emit(json.dumps({
                    "app_id": str(app_id), "status": "Complete", "progress": 100
                }))
                return True
            return False
        except Exception:
            logger.exception("Linux DDMod fallback failed for app %s", app_id)
            return False

    def _show_linux_fastest_workflow_notice(self, app_id):
        # One-time info-shaped progress event so the Web UI can render a banner
        # explaining the SLSSteam workflow when DepotDownloader was bypassed.
        if getattr(self, "_linux_fastest_notice_shown", False):
            return
        self._linux_fastest_notice_shown = True
        self.download_progress.emit(json.dumps({
            "app_id": app_id,
            "status": (
                "ACF and library entry written. Open Steam, find the game, "
                "click Update — SLSSteam pulls the content directly."
            ),
            "progress": -1,
            "info": True,
        }))

    @pyqtSlot(str, str)
    def download_dlc_oureveryday(self, dlc_appid, parent_appid):
        """Oureveryday DLC-only path: pull just the DLCs depot manifest +
        decryption key without re-downloading the parent game.

        Flow:
          1. Resolve parent app info from Steam, pull every depot whose
             `dlcappid` matches the DLC appid. If Steam exposes the DLC as
             appid-only, append the appid line and stop there.
          2. For each depot, fetch the depot key from the bundled key
             database (same one oureveryday uses for the full game flow).
             Skip any depot whose key isn't on file.
          3. Pull the manifest bytes through the existing cascade
             (gmrc -> ManifestHub https mirrors -> GitHub mirror -> CDN)
             and drop into <steam>/depotcache/.
          4. APPEND `addappid(<depot>, 1, "<key>")` lines to the existing
             <steam>/config/stplug-in/<parent>.lua. Never overwrite the
             whole file, so existing depot keys + setManifestid pins the
             user already has stay intact. If the parent lua doesnt exist
             yet, create it with `addappid(<parent>)` plus the new lines.
        """
        if not dlc_appid or not dlc_appid.strip().isdigit():
            self._emit_task_result("download_dlc", False, f"Invalid DLC App ID: '{dlc_appid}'")
            return
        if not parent_appid or not parent_appid.strip().isdigit():
            self._emit_task_result("download_dlc", False, f"Invalid parent App ID: '{parent_appid}'")
            return

        def _do():
            import json as _json
            from pathlib import Path as _Path
            try:
                from sff.steam_client import create_provider_for_current_thread
                from sff.manifest.downloader import ManifestDownloader
            except Exception as e:
                logger.exception("download_dlc_oureveryday: import failed: %s", e)
                return (False, f"Internal error: {e}")

            steam_path = self._steam_path
            if not steam_path:
                return (False, "Steam path not configured")

            self.download_progress.emit(_json.dumps({
                "app_id": dlc_appid, "status": "Resolving DLC depots", "progress": 10
            }))

            # Step 1: parent appinfo for depot mapping
            # SteamClient binds gevents hub to whichever OS thread built it,
            # so the get_single_app_info call MUST live on the same thread
            # as the client. Building the provider on this thread but
            # submit()ing the I/O onto an executor thread fires
            # "would block forever". Spin a throwaway provider INSIDE the
            # executor for the timed app-info hit, and keep the local
            # `provider` (built on this thread) for the downstream
            # ManifestDownloader / cdn calls below.
            try:
                provider = create_provider_for_current_thread()
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FT
                def _fetch_parent_info():
                    from sff.steam_client import create_provider_for_current_thread as _mk
                    return _mk().get_single_app_info(int(parent_appid))
                with ThreadPoolExecutor(max_workers=1) as _ex:
                    _fut = _ex.submit(_fetch_parent_info)
                    try:
                        parent_info = _fut.result(timeout=30)
                    except _FT:
                        return (False, "Steam app-info timed out (CM down?)")
            except Exception as e:
                logger.warning("download_dlc_oureveryday: provider failed: %s", e)
                return (False, f"Steam query failed: {e}")
            if not parent_info:
                return (False, f"Steam returned no info for parent app {parent_appid}")

            depots = parent_info.get("depots") or {}
            if not isinstance(depots, dict):
                return (False, "Parent depot map is malformed")

            dlc_depots = []
            for depot_id, depot_data in depots.items():
                if not depot_id.isdigit() or not isinstance(depot_data, dict):
                    continue
                if str(depot_data.get("dlcappid", "")) != str(dlc_appid):
                    continue
                manifests = depot_data.get("manifests") or {}
                gid = ""
                if isinstance(manifests, dict):
                    pub = manifests.get("public") or {}
                    if isinstance(pub, dict):
                        gid = str(pub.get("gid") or "")
                dlc_depots.append((depot_id, gid))

            keys_dict = {}
            if dlc_depots:
                # Step 2: bundled depot keys
                self.download_progress.emit(_json.dumps({
                    "app_id": dlc_appid, "status": "Loading depot keys", "progress": 25
                }))
                try:
                    local_db = _Path(__file__).parent.parent / "lua" / "fallback_depotkeys.json"
                    if local_db.exists():
                        keys_dict = _json.loads(local_db.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.debug("download_dlc_oureveryday: key db load failed: %s", e)

            cdn = None
            downloader = None
            saved = 0
            new_lines = []
            if dlc_depots:
                # Step 3: fetch manifests through the standard cascade
                self.download_progress.emit(_json.dumps({
                    "app_id": dlc_appid, "status": "Downloading DLC manifests", "progress": 50
                }))
                downloader = ManifestDownloader(provider, _Path(steam_path))
                try:
                    cdn = downloader.get_cdn_client()
                except Exception as e:
                    logger.debug("download_dlc_oureveryday: cdn client failed: %s", e)

                for depot_id, gid in dlc_depots:
                    key = keys_dict.get(depot_id)
                    if not key:
                        logger.debug("download_dlc_oureveryday: no bundled key for depot %s", depot_id)
                        continue
                    if not gid:
                        # No public manifest GID listed. Still add the key line
                        # so LumaCore can decrypt anything Steam later resolves
                        # for that depot.
                        new_lines.append(f'addappid({depot_id}, 1, "{key}")')
                        continue
                    try:
                        raw = downloader.download_single_manifest(
                            depot_id, gid, cdn_client=cdn, app_id=str(parent_appid),
                        )
                    except Exception as e:
                        logger.debug("download_dlc_oureveryday: depot %s fetch raised: %s", depot_id, e)
                        raw = None
                    if raw:
                        try:
                            if downloader._write_manifest_to_depotcache(raw, depot_id, gid, decrypt=False, dec_key=key):
                                saved += 1
                        except Exception as e:
                            logger.debug("download_dlc_oureveryday: write %s_%s failed: %s", depot_id, gid, e)
                    new_lines.append(f'addappid({depot_id}, 1, "{key}")')
            else:
                self.download_progress.emit(_json.dumps({
                    "app_id": dlc_appid,
                    "status": "DLC is appid-only; updating parent lua",
                    "progress": 70,
                    "info": True,
                }))

            # Always announce the DLC appid as owned even if no depots had
            # keys — the appid alone is enough for LumaCore to mark the
            # title.
            new_lines.append(f"addappid({dlc_appid})")

            # Step 4: merge into existing parent lua, preserving prior keys
            self.download_progress.emit(_json.dumps({
                "app_id": dlc_appid, "status": "Updating parent lua", "progress": 85
            }))
            stplug = _Path(steam_path) / "config" / "stplug-in"
            stplug.mkdir(parents=True, exist_ok=True)
            lua_path = stplug / f"{parent_appid}.lua"
            existing_text = ""
            if lua_path.exists():
                try:
                    existing_text = lua_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.warning("download_dlc_oureveryday: could not read existing lua: %s", e)
                    existing_text = ""
            if not existing_text:
                # Fresh lua. Seed with parent appid line so LumaCore picks
                # the title up.
                existing_text = f"addappid({parent_appid})\n"

            # Dedupe: skip lines that already appear verbatim in the file.
            # Lua matching here is line-for-line, so this avoids double
            # entries on repeat clicks.
            existing_lines = set(l.strip() for l in existing_text.splitlines() if l.strip())
            appended = 0
            extra = []
            for line in new_lines:
                if line not in existing_lines:
                    extra.append(line)
                    existing_lines.add(line)
                    appended += 1
            if extra:
                if not existing_text.endswith("\n"):
                    existing_text += "\n"
                existing_text += "\n".join(extra) + "\n"
                try:
                    lua_path.write_text(existing_text, encoding="utf-8")
                except Exception as e:
                    logger.exception("download_dlc_oureveryday: lua write failed: %s", e)
                    return (False, f"Failed to write parent lua: {e}")

            # Step 5: update parent ACF with DLC depot entries so Steam
            # routes DLC content to the game's library folder, not a random
            # place.  Without this the ACF lacks InstalledDepots for the DLC
            # depots and Steam may put downloaded content in a default library.
            try:
                from sff.storage.vdf import get_steam_libs as _gsl, vdf_load as _vl, vdf_dump as _vd
                _libs = _gsl(steam_path) if steam_path else []
                for _lib in _libs:
                    _acf = _Path(_lib) / "steamapps" / f"appmanifest_{parent_appid}.acf"
                    if not _acf.exists():
                        continue
                    _data = _vl(_acf)
                    _state = _data.get("AppState", {})
                    if not isinstance(_state, dict):
                        break
                    _installed = _state.setdefault("InstalledDepots", {})
                    _mounted = _state.get("MountedDepots", {})
                    _changed = False
                    for _did, _gid in dlc_depots:
                        _ds = str(_did)
                        _gs = str(_gid) if _gid else "0"
                        _entry = _installed.get(_ds)
                        if isinstance(_entry, dict):
                            if _entry.get("manifest", "0") != _gs:
                                _entry["manifest"] = _gs
                                _changed = True
                        else:
                            _installed[_ds] = {"manifest": _gs, "size": "0"}
                            _changed = True
                        if isinstance(_mounted, dict) and _mounted.get(_ds) != _gs:
                            _mounted[_ds] = _gs
                            _changed = True
                    if _changed:
                        _state["InstalledDepots"] = _installed
                        if isinstance(_mounted, dict):
                            _state["MountedDepots"] = _mounted
                        _data["AppState"] = _state
                        _vd(_acf, _data)
                        try:
                            os.chmod(_acf, 0o444)
                        except OSError:
                            pass
                        logger.info(
                            "download_dlc_oureveryday: patched %s with %d DLC depot(s)",
                            _acf.name, len(dlc_depots),
                        )
                    break
            except Exception as e:
                logger.exception("download_dlc_oureveryday: ACF update failed: %s", e)

            self.download_progress.emit(_json.dumps({
                "app_id": dlc_appid, "status": "Complete", "progress": 100
            }))
            if dlc_depots:
                msg = (
                    f"DLC {dlc_appid} added to {parent_appid}.lua "
                    f"({saved} manifest(s) saved, {appended} key line(s) appended, "
                    f"ACF patched with {len(dlc_depots)} DLC depot(s))"
                )
            else:
                state = "already present" if appended == 0 else "appid line appended"
                msg = f"DLC {dlc_appid} added to {parent_appid}.lua ({state}; no separate depots)"
            return (True, msg)

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg = result
                self._emit_task_result("download_dlc", ok, msg, dlc_app_id=dlc_appid, parent_app_id=parent_appid)
            else:
                self._emit_task_result("download_dlc", False, "DLC download failed", dlc_app_id=dlc_appid, parent_app_id=parent_appid)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, str)
    def download_game_version(self, app_id, manifest_override_json, source='oureveryday'):
        """Download specific version via process_from_store().
        Emits download_progress + task_finished signals."""
        if not app_id or not app_id.strip().isdigit():
            return
        def _do():
            try:
                manifest_override = json.loads(manifest_override_json)
            except (json.JSONDecodeError, TypeError):
                return False

            if not manifest_override:
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Starting version download", "progress": 10
            }))

            from pathlib import Path as _Path
            from sff.structs import LuaEndpoint
            lib_override = _Path(self._active_library) if self._active_library else self._steam_path
            src_map = {"hubcap": LuaEndpoint.HUBCAP, "ryuu": LuaEndpoint.RYUU, "oureveryday": LuaEndpoint.OUREVERYDAY}
            selected = src_map.get(source, LuaEndpoint.HUBCAP if self._api_key else LuaEndpoint.OUREVERYDAY)
            try:
                self._ui.process_from_store(
                    app_id=app_id,
                    manifest_override=manifest_override,
                    use_hubcap=(selected == LuaEndpoint.HUBCAP),
                    lib_path=lib_override,
                    source_override=selected,
                )
            except Exception:
                logger.exception("download_game_version: process_from_store failed for %s", app_id)
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Complete", "progress": 100
            }))
            return True

        def _on_done(result):
            success = result is True
            self._emit_task_result(
                "download_version",
                success,
                f"Version download {'completed' if success else 'failed'} for App {app_id}",
                app_id=app_id,
            )

        def _on_error(error_msg):
            self._emit_task_result(
                "download_version", False, error_msg, app_id=app_id
            )

        self._run_async(_do, on_done=_on_done, on_error=_on_error)

    @pyqtSlot(str, str, str)
    def download_game_version_native(self, app_id, manifest_override_json, source='oureveryday'):
        """Download specific version via Steam Native flow.
        Downloads Lua, pins manifests with write_manifest_pins_to_lua,
        installs to Steam plugin folder, writes ACF. Steam downloads
        the actual content. Windows-only."""
        if sys.platform != "win32":
            logger.debug("download_game_version_native: skipped on Linux (Windows-only)")
            return
        if not app_id or not app_id.strip().isdigit():
            return
        def _do():
            try:
                manifest_override = json.loads(manifest_override_json)
            except (json.JSONDecodeError, TypeError):
                return False
            if not manifest_override:
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Starting Steam Native download", "progress": 5
            }))

            from sff.lua.choices import download_lua_direct
            from sff.lua.manager import parse_lua_contents, write_manifest_pins_to_lua
            from sff.steam_tools_compat import install_lua_to_steam
            from sff.lua.writer import ACFWriter, ConfigVDFWriter
            from sff.structs import LuaEndpoint

            steam_path = self._steam_path
            lib_override = Path(self._active_library) if self._active_library else steam_path

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Downloading Lua", "progress": 10
            }))

            saved_lua_root = Path.cwd() / "saved_lua"
            saved_lua_root.mkdir(exist_ok=True)
            src_map = {"hubcap": LuaEndpoint.HUBCAP, "ryuu": LuaEndpoint.RYUU, "oureveryday": LuaEndpoint.OUREVERYDAY}
            selected_source = src_map.get(source, LuaEndpoint.HUBCAP if self._api_key else LuaEndpoint.OUREVERYDAY)
            lua_path = download_lua_direct(
                dest=saved_lua_root, app_id=app_id,
                source=selected_source, steam_path=steam_path,
            )
            if not lua_path:
                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Lua download failed. Try a different source.",
                    "progress": 0, "error": True,
                }))
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Pinning manifests in Lua", "progress": 30
            }))
            pinned = write_manifest_pins_to_lua(lua_path, manifest_override)
            if not pinned:
                logger.warning("download_game_version_native: no manifests pinned for %s", app_id)
                self.download_progress.emit(json.dumps({
                    "app_id": app_id,
                    "status": "No manifest pins were written. ACF was not created.",
                    "progress": 0,
                    "error": True,
                }))
                return False

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Installing Lua to Steam", "progress": 50
            }))
            _auto_update_was_registered = self._auto_update_was_registered(app_id)
            install_lua_to_steam(steam_path, app_id, lua_path)
            self._apply_auto_update_default(app_id, _auto_update_was_registered)

            parsed = parse_lua_contents(
                lua_path.read_text(encoding="utf-8", errors="replace"), lua_path
            )
            if not parsed:
                self.download_progress.emit(json.dumps({
                    "app_id": app_id,
                    "status": "Lua parse failed after pinning. ACF was not created.",
                    "progress": 0,
                    "error": True,
                }))
                return False

            config_writer = ConfigVDFWriter(steam_path)
            config_writer.add_decryption_keys_to_config(parsed)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Writing ACF", "progress": 70
            }))
            buildid = "0"
            try:
                from sff.steam_client import create_provider_for_current_thread
                app_data = create_provider_for_current_thread().get_single_app_info(int(app_id))
                bid = (
                    app_data.get("depots", {})
                    .get("branches", {})
                    .get("public", {})
                    .get("buildid")
                )
                if bid:
                    buildid = str(bid)
            except Exception as exc:
                logger.debug("download_game_version_native: buildid lookup failed for %s: %s", app_id, exc)
            acf_writer = ACFWriter(lib_override)
            acf_writer.write_acf(parsed, manifest_override=manifest_override, buildid=buildid)

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Complete — Steam will download the game", "progress": 100
            }))
            return True

        def _on_done(result):
            success = result is True
            self._emit_task_result(
                "download_version_native",
                success,
                f"Steam Native download {'completed' if success else 'failed'} for App {app_id}",
                app_id=app_id,
            )

        def _on_error(error_msg):
            self._emit_task_result(
                "download_version_native", False, error_msg, app_id=app_id
            )

        self._run_async(_do, on_done=_on_done, on_error=_on_error)

    @pyqtSlot(str)
    def dlc_check_get_list(self, app_id):
        """Fetch DLC list for the selected game and emit a structured
        `task_finished` payload the Web UI can render in a modal.

        Replaces the old run_game_action('dlc_check') flow that piped
        Rich console tables into stdout that the Web UI never displayed.
        Two paths:

          * Steam-side (Web API via SteamInfoProvider): pulls
            `extended.listofdlc` and per-DLC type / depot / manifest
            metadata. Used when the SteamClient is logged in.
          * Steam Store fallback: hits `appdetails` and reads `dlc`
            for the appid list, then pulls per-DLC names from the same
            Store endpoint. Used when the Steam Web client times out.

        Result payload shape:
          { task: 'dlc_check', success: bool, app_id: str, source: str,
            dlcs: [{ id, name, in_applist, has_key, has_manifest, type }],
            owned_count, total_count, message: str }
        """
        if not app_id or not str(app_id).strip().isdigit():
            self._emit_task_result("dlc_check", False, "Invalid app ID",
                                   app_id=str(app_id), dlcs=[])
            return

        def _do():
            base_id = int(app_id)
            local_ids: set = set()
            try:
                if self._ui:
                    inj = getattr(self._ui, 'app_list_man', None) or getattr(self._ui, 'sls_man', None)
                    if inj is not None:
                        local_ids = set(inj.get_local_ids() or [])
            except Exception as e:
                logger.debug("dlc_check_get_list: get_local_ids failed: %s", e)

            # Local-first check. Steam itself reads these on disk so we do
            # the same and don't rely on hubcap/store reporting an install.
            #   1. <steam>\config\stplug-in\<parent>.lua  -> addappid(N)
            #   2. <library>\steamapps\appmanifest_<parent>.acf
            #      -> InstalledDepots / MountedDepots block
            # Anything that shows up in either of those is treated as
            # already unlocked even when the Steam web check is blind to it.
            from pathlib import Path as _Path
            lua_ids: set = set()
            try:
                if self._steam_path:
                    lua_path = _Path(self._steam_path) / "config" / "stplug-in" / f"{base_id}.lua"
                    if lua_path.exists():
                        txt = lua_path.read_text(encoding="utf-8", errors="replace")
                        for m in re.finditer(r"addappid\s*\(\s*(\d+)", txt):
                            try:
                                lua_ids.add(int(m.group(1)))
                            except ValueError:
                                pass
            except Exception as e:
                logger.debug("dlc_check_get_list: parent lua parse failed: %s", e)

            acf_depots: set = set()
            try:
                from sff.storage.vdf import get_steam_libs as _gsl
                libs = _gsl(self._steam_path) if self._steam_path else []
                for lib in libs:
                    acf = _Path(lib) / "steamapps" / f"appmanifest_{base_id}.acf"
                    if not acf.exists():
                        continue
                    raw = acf.read_text(encoding="utf-8", errors="replace")
                    # depot ids appear as "<id>" keys inside the
                    # InstalledDepots / MountedDepots blocks. Cheap regex
                    # is fine here; the file is small and the structure
                    # is stable enough.
                    block = re.search(
                        r'"(?:InstalledDepots|MountedDepots)"\s*\{([^}]*)\}',
                        raw, re.IGNORECASE | re.DOTALL,
                    )
                    if block:
                        for m in re.finditer(r'"(\d+)"', block.group(1)):
                            try:
                                acf_depots.add(int(m.group(1)))
                            except ValueError:
                                pass
                    break
            except Exception as e:
                logger.debug("dlc_check_get_list: acf scan failed: %s", e)

            # Try Steam Web API first via the existing provider; fall back
            # to the Store API when the API call fails or returns no data.
            # The provider.get_single_app_info call goes through SteamKit
            # which hangs forever on a flaky CM ('This operation would
            # block forever' from gevent). 45s ceiling on a worker pool,
            # bumped from 30 because users on slow CMs were timing out.
            dlc_ids: list = []
            base_name = ""
            depot_id_set: set = set()
            # dlc_appid -> set of depot ids (from base_info depots map)
            dlc_depot_map: dict = {}
            steam_api_ok = False
            try:
                if self._ui and getattr(self._ui, 'provider', None):
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FT
                    base_info = None
                    # SteamClient pins gevents hub to the OS thread that
                    # constructed it. self._ui.provider was built on the
                    # GUI thread (or whichever thread first touched the
                    # ui), so calling its methods from a ThreadPoolExecutor
                    # worker fires "would block forever". Build a
                    # throwaway provider inside the executor instead.
                    def _fetch_base_info():
                        from sff.steam_client import create_provider_for_current_thread as _mk
                        return _mk().get_single_app_info(base_id)
                    with ThreadPoolExecutor(max_workers=1) as _ex:
                        _fut = _ex.submit(_fetch_base_info)
                        try:
                            base_info = _fut.result(timeout=45)
                        except _FT:
                            logger.debug("dlc_check_get_list: Steam app-info timed out, falling back to store")
                            base_info = None
                    if base_info:
                        steam_api_ok = True
                        base_name = str(
                            base_info.get('common', {}).get('name', '') or ''
                        )
                        from sff.utils import enter_path
                        raw = enter_path(base_info, 'extended', 'listofdlc')
                        if isinstance(raw, str) and raw.strip():
                            dlc_ids = [
                                int(x) for x in raw.split(',') if x.strip().isdigit()
                            ]
                        depots = base_info.get('depots') or {}
                        if isinstance(depots, dict):
                            for k, v in depots.items():
                                if not isinstance(v, dict):
                                    continue
                                dlc_appid = v.get('dlcappid')
                                if dlc_appid:
                                    try:
                                        dlc_aid_int = int(dlc_appid)
                                        depot_id_set.add(dlc_aid_int)
                                        try:
                                            depot_id_int = int(k)
                                        except (TypeError, ValueError):
                                            depot_id_int = None
                                        if depot_id_int is not None:
                                            dlc_depot_map.setdefault(dlc_aid_int, set()).add(depot_id_int)
                                    except (TypeError, ValueError):
                                        pass
            except Exception as e:
                logger.debug("dlc_check_get_list: Steam API path failed: %s", e)

            # When the live Steam API blew up, try a cached extended.listofdlc
            # from the on-disk app-info cache. That's enough to render the
            # modal even when 'block forever' kills the live call.
            if not dlc_ids:
                try:
                    cache_obj = getattr(self._ui, 'app_info_cache', None) if self._ui else None
                    if cache_obj is not None:
                        cached = None
                        try:
                            cached = cache_obj.get(base_id)
                        except Exception:
                            cached = None
                        if cached:
                            from sff.utils import enter_path
                            raw = enter_path(cached, 'extended', 'listofdlc')
                            if isinstance(raw, str) and raw.strip():
                                dlc_ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
                            if not base_name:
                                base_name = str(cached.get('common', {}).get('name', '') or '')
                            cdepots = cached.get('depots') or {}
                            if isinstance(cdepots, dict):
                                for k, v in cdepots.items():
                                    if not isinstance(v, dict):
                                        continue
                                    da = v.get('dlcappid')
                                    if da:
                                        try:
                                            dai = int(da)
                                            depot_id_set.add(dai)
                                            try:
                                                kid = int(k)
                                                dlc_depot_map.setdefault(dai, set()).add(kid)
                                            except (TypeError, ValueError):
                                                pass
                                        except (TypeError, ValueError):
                                            pass
                except Exception as e:
                    logger.debug("dlc_check_get_list: app-info cache fallback failed: %s", e)

            # Fallback to Store API for the DLC id list when Steam API
            # didn't return anything.
            if not dlc_ids:
                try:
                    from sff.steam_store import get_dlc_list_from_store
                    result = get_dlc_list_from_store(base_id)
                    if result:
                        base_name = result[0] or base_name
                        dlc_ids = list(result[1] or [])
                except Exception as e:
                    logger.debug("dlc_check_get_list: Store API path failed: %s", e)

            if not dlc_ids:
                self._emit_task_result(
                    "dlc_check", True,
                    f"{base_name or 'App ' + str(base_id)} has no DLCs",
                    app_id=str(base_id),
                    base_name=base_name,
                    dlcs=[],
                    owned_count=0,
                    total_count=0,
                )
                return

            # Pull DLC names. Prefer Steam Store API for delisted DLCs
            # since the Web API may not expose them to a non-owning user.
            from sff.steam_store import get_dlc_names_from_store
            try:
                names_map = get_dlc_names_from_store(dlc_ids) or {}
            except Exception as e:
                logger.debug("dlc_check_get_list: name fetch failed: %s", e)
                names_map = {}

            # Decryption keys live in <steam>/config/config.vdf.
            try:
                from sff.lua.writer import ConfigVDFWriter
                cfg = ConfigVDFWriter(self._steam_path) if self._steam_path else None
                key_map = cfg.ids_in_config(dlc_ids) if cfg else {}
            except Exception as e:
                logger.debug("dlc_check_get_list: key map failed: %s", e)
                key_map = {}

            # depotcache scan: filenames look like '<depotid>_<gid>.manifest'.
            # if any depot the dlc owns lands here, count it as on-disk. cheap,
            # one stat per directory entry.
            depotcache_ids: set = set()
            try:
                if self._steam_path:
                    from pathlib import Path as _P2
                    candidates = [
                        _P2(self._steam_path) / "depotcache",
                        _P2(self._steam_path) / "config" / "depotcache",
                    ]
                    for d in candidates:
                        if not d.exists():
                            continue
                        for entry in d.iterdir():
                            n = entry.name
                            if not n.endswith(".manifest"):
                                continue
                            head = n.split("_", 1)[0]
                            if head.isdigit():
                                try:
                                    depotcache_ids.add(int(head))
                                except ValueError:
                                    pass
            except Exception as e:
                logger.debug("dlc_check_get_list: depotcache scan failed: %s", e)

            # Windows registry: HKCU\Software\Valve\Steam\Apps\<dlc>\Installed.
            # Steam writes 1 here when the DLC counts as installed in its own
            # bookkeeping. Linux / non-Windows: silently skip.
            registry_installed: set = set()
            try:
                import sys as _sys
                if _sys.platform == "win32":
                    import winreg as _wr
                    for did in dlc_ids:
                        try:
                            with _wr.OpenKey(
                                _wr.HKEY_CURRENT_USER,
                                rf"Software\\Valve\\Steam\\Apps\\{did}",
                            ) as _k:
                                val, _ = _wr.QueryValueEx(_k, "Installed")
                                if int(val) == 1:
                                    registry_installed.add(int(did))
                        except FileNotFoundError:
                            continue
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("dlc_check_get_list: registry scan failed: %s", e)

            dlcs_payload = []
            owned = 0
            for did in dlc_ids:
                # Source-of-truth merge: SLSSteam local list, parent lua,
                # ACF MountedDepots/InstalledDepots, config.vdf depot keys,
                # depotcache manifests for this dlc's depots, and the win32
                # HKCU\Steam\Apps\<id>\Installed=1 registry flag. Any one
                # of those flags it as on-disk.
                in_local = did in local_ids
                in_lua = did in lua_ids
                in_acf = did in acf_depots
                in_keymap = bool(key_map.get(did, False))
                in_reg = did in registry_installed
                in_depotcache = False
                if depotcache_ids:
                    own_depots = dlc_depot_map.get(did) or set()
                    if own_depots and (own_depots & depotcache_ids):
                        in_depotcache = True
                in_applist = (
                    in_local or in_lua or in_acf or in_keymap
                    or in_reg or in_depotcache
                )
                if in_applist:
                    owned += 1
                is_depot = did in depot_id_set
                dlcs_payload.append({
                    "id": str(did),
                    "name": names_map.get(did, f"DLC {did}"),
                    "in_applist": in_applist,
                    "has_key": in_keymap,
                    "type": "depot" if is_depot else "appid",
                })

            self._emit_task_result(
                "dlc_check", True,
                f"{owned}/{len(dlc_ids)} DLCs unlocked for "
                f"{base_name or 'App ' + str(base_id)}",
                app_id=str(base_id),
                base_name=base_name,
                dlcs=dlcs_payload,
                owned_count=owned,
                total_count=len(dlc_ids),
            )

        def _on_error(msg):
            self._emit_task_result("dlc_check", False, str(msg),
                                   app_id=str(app_id), dlcs=[])

        self._run_async(_do, on_error=_on_error)

    @pyqtSlot(str, str)
    def run_game_action(self, app_id, action):
        """Routes to backend action (crack, dlc_check, etc.).
        Game-specific actions need an ACFInfo; non-game actions call ui methods directly.
        Emits task_finished signal."""
        # SteamAutoCrack must run on the main thread — it uses _start_worker internally.
        # Calling it from _run_async (background thread) causes immediate 'completed'
        # and a freeze/deadlock on the second click.
        if action == "steam_auto":
            from sff.steamauto import get_steamauto_cli_path
            if get_steamauto_cli_path() is None:
                self._emit_task_result("steam_auto", False, "SteamAutoCrack CLI not found")

                return
            acf = self._resolve_acf(app_id)
            if acf is None:
                self._emit_task_result("steam_auto", False, "No game found for the selected App ID")

                return
            parent = self.parent()
            if parent and hasattr(parent, '_run_steam_auto_with_acf'):
                # Web UI showed its own confirm dialog already — suppress the
                # Qt-side double-prompt for this single delegate call.
                if hasattr(parent, '_skip_next_achievement_warn'):
                    parent._skip_next_achievement_warn = True
                else:
                    setattr(parent, '_skip_next_achievement_warn', True)
                parent._run_steam_auto_with_acf(acf)

            return

        # Steamless / Remove DRM must also run on the main thread.
        # _run_steamless_for_acf calls _start_worker internally which
        # creates QThreads — doing that from _run_async's background
        # thread is unsafe and crashes Qt6.
        if action == "steamstub":
            acf = self._resolve_acf(app_id)
            if acf is None:
                self._emit_task_result("steamstub", False, "No game found for the selected App ID")
                return
            parent = self.parent()
            if parent and hasattr(parent, "_run_steamless_for_acf"):
                parent._run_steamless_for_acf(acf)
            return

        def _do():
            from sff.structs import MainMenu, MainReturnCode

            # Non-game-specific actions — call ui methods directly
            non_game_actions = {
                "download_games": lambda: self._ui.process_lua_full(),
                "download_manifests": lambda: self._ui.process_lua_minimal(),
                "recent_lua": lambda: self._ui.recent_files_menu(),
                "update_manifests": lambda: self._ui.update_all_manifests(),
                "injection_menu": lambda: self._ui.injection_menu(),
                "applist_menu": lambda: self._ui.injection_menu(),
                "remove_game": lambda: self._ui.remove_game_menu(),
                "context_menu": lambda: self._ui.manage_context_menu(),
                "check_updates": lambda: self._ui.check_updates(self._ui.os_type),
                "scan_library": lambda: self._ui.scan_library_menu(),
                "analytics": lambda: self._ui.analytics_dashboard_menu(),
            }

            if action in non_game_actions:
                try:
                    from sff.structs import MainReturnCode
                    result = non_game_actions[action]()
                    if result is MainReturnCode.EXIT:
                        return f"Action '{action}' is not supported on this platform or configuration."
                    if action == "check_updates":
                        self.task_finished.emit(json.dumps({"task":"app_update","status":"downloading","progress":10,"message":"Downloading update..."}))
                        from PyQt6.QtWidgets import QApplication
                        QApplication.processEvents()
                        try:
                            result = non_game_actions[action]()
                            return "__check_updates_done__"
                        except Exception as e:
                            self._emit_task_result("app_update", False, str(e))
                            return str(e)
                    return None
                except Exception as e:
                    return str(e)

            # Mute toggle — special handling, not a MainMenu choice
            if action == "mute_toggle":
                try:
                    parent = self.parent()
                    if parent and hasattr(parent, '_toggle_mute'):
                        parent._toggle_mute()
                    elif self._ui and hasattr(self._ui, 'midi_player') and self._ui.midi_player:
                        self._ui.midi_player.set_muted(not self._ui.midi_player._muted)
                    return None
                except Exception as e:
                    return str(e)

            # Game-specific actions — need an ACFInfo from app_id
            game_action_map = {
                "crack": MainMenu.CRACK_GAME,
                "steamstub": MainMenu.REMOVE_DRM,
                "dlc_check": MainMenu.DLC_CHECK,
                "workshop": MainMenu.DL_WORKSHOP_ITEM,
                "multiplayer": MainMenu.MULTIPLAYER_FIX,
                "community_fixes": MainMenu.CRACK_FIX,
                "hv_fix": MainMenu.HV_FIX,
                "achievements": MainMenu.DL_USER_GAME_STATS,
                "dlc_unlockers": MainMenu.MANAGE_DLC_UNLOCKERS,
                "check_mod_updates": MainMenu.CHECK_MOD_UPDATES,
            }

            menu_choice = game_action_map.get(action)
            if menu_choice is None:
                return f"Unknown action: {action}"

            # Build ACFInfo from app_id
            acf = self._resolve_acf(app_id)
            if acf is None:
                return f"No game found for App ID: {app_id}"

            try:
                result = self._ui.run_game_action_with_selection(menu_choice, acf)
                if isinstance(result, tuple) and len(result) == 2:
                    ok, msg = result
                    self._emit_task_result(action, bool(ok), str(msg))
                    return "__handled_no_toast__"
                if result is False or result is MainReturnCode.EXIT:
                    return f"Action '{action}' failed"
                if result is MainReturnCode.LOOP_NO_PROMPT:
                    return "__handled_no_toast__"
                return None
            except Exception as e:
                return str(e)

        def _on_done(error_msg):
            if error_msg == "__handled_no_toast__":
                return
            if error_msg == "__check_updates_done__":
                self._emit_task_result("check_updates", True, "Update check finished.")
                return
            if error_msg:
                self._emit_task_result(action, False, str(error_msg))
            # A None/empty result means the legacy menu flow either handled
            # its own UI, was cancelled, or did not report a result. Do not
            # show a green success toast for that ambiguous state.

        self._run_async(_do, on_done=_on_done)

    def _resolve_acf(self, app_id):
        """Find ACFInfo for a given app_id by scanning Steam libraries.

        Falls back to a synthetic ACFInfo (steam_path / "common") for actions
        that only need the app_id (DLC check, Workshop browse, achievement
        data download). Without this fallback, a SteaMidra-registered game
        whose depot fetch hasn't happened yet would surface "No game found
        for App ID" even though the Store API call doesn't need a game
        folder.
        """
        if not app_id:
            return None
        try:
            from sff.game_specific import ACFInfo
            from sff.storage.vdf import get_steam_libs, vdf_load
            libs = get_steam_libs(self._steam_path) if self._steam_path else []
            for lib in libs:
                steamapps = lib / "steamapps"
                if not steamapps.exists():
                    continue
                acf_path = steamapps / f"appmanifest_{app_id}.acf"
                if acf_path.exists():
                    data = vdf_load(acf_path)
                    state = data.get("AppState", {})
                    installdir = state.get("installdir", "")
                    game_path = steamapps / "common" / installdir
                    return ACFInfo(str(app_id), game_path)
            # Synthetic ACFInfo for app_id-only actions (DLC check, Workshop,
            # achievement data). Game-specific actions that need a real game
            # folder (crack, steamstub) gate on path.exists() themselves.
            if self._steam_path:
                synthetic_path = self._steam_path / "steamapps" / "common" / f"app_{app_id}"
                return ACFInfo(str(app_id), synthetic_path)
        except Exception as e:
            logger.warning("_resolve_acf failed: %s", e)
        return None

    @pyqtSlot(str)
    def fix_game(self, config_json):
        """Apply emulator fix to a game. Emits task_finished."""
        def _do():
            try:
                config = json.loads(config_json)
                from sff.fix_game.service import FixGameService
                raw_id = config.get("app_id", "")
                app_id = int(raw_id) if str(raw_id).strip().isdigit() else 0
                svc = FixGameService()
                success = svc.fix_game(
                    app_id=app_id,
                    game_dir=config.get("game_path", ""),
                    emu_mode=config.get("emu_mode", "regular"),
                    skip_steamstub=not config.get("unpack_steamstub", True),
                    steamless_experimental=config.get("use_experimental_steamless", True),
                    skip_goldberg_update=not config.get("goldberg_update", False),
                    create_launch_bat=config.get("create_launch_bat", False),
                    player_name=config.get("username") or "Player",
                    steam_id=config.get("steam_id") or "76561198001737783",
                    avatar_path=config.get("avatar_path") or None,
                    simple_settings=config.get("simple_settings", False),
                    gse_auth_mode=config.get("gse_auth_mode", "anonymous"),
                    gse_username=config.get("gse_username", ""),
                    gse_password=config.get("gse_password", ""),
                )
                return success
            except Exception as e:
                logger.exception("fix_game failed: %s", e)
                return str(e)

        def _on_done(result):
            if result is True:
                self._emit_task_result("fix_game", True, "Game fix applied successfully")
            else:
                self._emit_task_result("fix_game", False, str(result) if result else "Fix failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def revert_game(self, game_path):
        """Revert emulator changes."""
        def _do():
            try:
                from sff.fix_game.service import FixGameService
                # FixGameService is not stateless — instantiate then call.
                # Returns (success, message) tuple.
                svc = FixGameService()
                success, msg = svc.restore_game(game_path)
                return (bool(success), str(msg) if msg else "Changes reverted")
            except Exception as e:
                logger.exception("revert_game failed")
                return (False, f"Revert failed: {e}")

        def _on_done(result):
            if isinstance(result, tuple) and len(result) == 2:
                ok, msg = result
                self._emit_task_result("revert_game", bool(ok), str(msg))
            else:
                self._emit_task_result("revert_game", False, "Revert failed: unexpected result")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def generate_gbe_token(self, config_json):
        """Generate GBE token files."""
        def _do():
            config = json.loads(config_json)
            api_key = config.get("api_key", "").strip()
            app_id_str = str(config.get("app_id", "")).strip()
            output_dir = config.get("output_dir", "").strip()
            if not api_key:
                return (False, "No Steam Web API key provided.")
            if not app_id_str.isdigit():
                return (False, "App ID must be a number.")
            if not output_dir:
                return (False, "No output directory provided.")
            from sff.tools.gbe_token_generator import GBETokenGenerator
            log_lines = []
            def _log(msg):
                log_lines.append(msg)
                self.log_message.emit(msg)
            gen = GBETokenGenerator(steam_web_api_key=api_key)
            success = gen.generate(int(app_id_str), output_dir, log_func=_log)
            if success:
                try:
                    from sff.storage.settings import set_setting
                    from sff.structs import Settings
                    set_setting(Settings.STEAM_WEB_API_KEY, api_key)
                except Exception:
                    pass
            return (success, "\n".join(log_lines))

        def _on_done(result):
            if isinstance(result, tuple):
                ok, log_text = result
                msg = "GBE config generated successfully" if ok else log_text.split("\n")[-1]
                self._emit_task_result("generate_gbe_token", ok, msg, log=log_text)
            else:
                self._emit_task_result("generate_gbe_token", False, "Generation failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, str)
    def scan_cloud_games(self, steam_path, steam32_id):
        """Scan userdata for cloud saves."""
        def _do():
            from sff.cloud_saves import CloudSaves
            pairs = CloudSaves.list_steam_games(steam_path, steam32_id)
            games = []
            for app_id, game_name in pairs:
                remote_dir = Path(steam_path) / "userdata" / steam32_id / str(app_id) / "remote"
                size = 0
                if remote_dir.exists():
                    try:
                        size = sum(f.stat().st_size for f in remote_dir.rglob("*") if f.is_file())
                    except Exception:
                        pass
                games.append({
                    "app_id": str(app_id),
                    "name": game_name,
                    "size": _format_size(size),
                })
            return games

        def _on_done(games):
            self._emit_task_result("scan_cloud_games", True, "", games=games or [])

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def backup_cloud_save(self, config_json):
        """Backup cloud saves for a game."""
        def _do():
            config = json.loads(config_json)
            app_id = str(config.get("app_id", "")).strip()
            dest_path = config.get("dest_path", "").strip()
            steam_path = config.get("steam_path", "").strip()
            steam32_id = str(config.get("steam32_id", "")).strip()
            game_name = config.get("game_name", f"App {app_id}").strip() or f"App {app_id}"
            if not app_id or not dest_path or not steam_path or not steam32_id:
                return (False, "", "Missing required parameters for backup")
            from sff.cloud_saves import CloudSaves
            log_lines = []
            result = CloudSaves().backup_steam_save(
                steam_path, steam32_id, int(app_id), game_name, dest_path,
                log_func=log_lines.append,
            )
            log_text = "\n".join(log_lines)
            if result:
                return (True, log_text, f"Saves backed up for {game_name}")
            return (False, log_text, "Backup failed — check log")

        def _on_done(result):
            if isinstance(result, tuple):
                ok, log_text, msg = result
                self._emit_task_result("backup_cloud_save", ok, msg, log=log_text)
            else:
                self._emit_task_result("backup_cloud_save", False, "Backup failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def restore_cloud_save(self, config_json):
        """Restore cloud saves from backup."""
        def _do():
            config = json.loads(config_json)
            backup_path = config.get("backup_path", "").strip()
            app_id = str(config.get("app_id", "")).strip()
            steam_path = config.get("steam_path", "").strip()
            steam32_id = str(config.get("steam32_id", "")).strip()
            if not backup_path or not app_id or not steam_path or not steam32_id:
                return (False, "", "Missing required parameters for restore")
            from sff.cloud_saves import CloudSaves
            log_lines = []
            ok = CloudSaves().restore_steam_save(
                backup_path, steam_path, steam32_id, int(app_id),
                log_func=log_lines.append,
            )
            log_text = "\n".join(log_lines)
            if ok:
                return (True, log_text, "Saves restored successfully")
            return (False, log_text, "Restore failed — check log")

        def _on_done(result):
            if isinstance(result, tuple):
                ok, log_text, msg = result
                self._emit_task_result("restore_cloud_save", ok, msg, log=log_text)
            else:
                self._emit_task_result("restore_cloud_save", False, "Restore failed")

        self._run_async(_do, on_done=_on_done)

    # ── Bundled tool resolution ───────────────────────────────────

    @staticmethod
    def _get_bundled_tool_path(tool: str) -> Path | None:
        """Return path to a bundled executable in third_party/<tool>/<tool>.exe.
        Checks sys._MEIPASS first (frozen EXE), then project root (dev mode).
        Returns None if not found.

        rclone has a Linux-only sibling layout: `third_party/rclone_linux/rclone`
        (no .exe, no rclone_linux folder name on Windows). The helper resolves
        the right location based on sys.platform without altering the Windows
        path.
        """
        from sff.utils import root_folder
        ext = ".exe" if sys.platform == "win32" else ""
        # rclone ships as a per-platform folder so the Windows .exe and the
        # Linux ELF binary can coexist in the source tree without one
        # clobbering the other.
        if tool == "rclone":
            tool_folder = "rclone" if sys.platform == "win32" else "rclone_linux"
        else:
            tool_folder = tool
        rel = Path("third_party") / tool_folder / f"{tool}{ext}"
        if getattr(sys, "frozen", False):
            meipass = Path(getattr(sys, "_MEIPASS", ""))
            p = meipass / rel
            if p.exists():
                return p
        try:
            p = root_folder() / rel
            if p.exists():
                return p
        except Exception:
            pass
        return None

    @pyqtSlot(str, result=str)
    def get_bundled_tool_path(self, tool_name: str) -> str:
        """Return the absolute path to a bundled tool executable, or empty string."""
        p = self._get_bundled_tool_path(tool_name)
        return str(p) if p else ""

    @pyqtSlot(str)
    def rclone_backup_save(self, config_json):
        """Upload a game's Steam userdata saves to an rclone remote."""
        def _do():
            import subprocess
            import tempfile
            config = json.loads(config_json)
            app_id = str(config.get("app_id", "")).strip()
            rclone_exe = config.get("rclone_exe", "").strip()
            remote_dest = config.get("remote_dest", "").strip()
            steam_path = config.get("steam_path", "").strip()
            steam32_id = str(config.get("steam32_id", "")).strip()
            game_name = config.get("game_name", f"App {app_id}").strip() or f"App {app_id}"
            if not rclone_exe:
                bundled = WebBridge._get_bundled_tool_path("rclone")
                if bundled:
                    rclone_exe = str(bundled)
            if not app_id or not rclone_exe or not remote_dest or not steam_path or not steam32_id:
                return (False, "", "Missing rclone configuration")
            if not Path(rclone_exe).exists():
                return (False, "", f"rclone executable not found: {rclone_exe}")
            from sff.cloud_saves import CloudSaves
            log_lines = []
            tmp = Path(tempfile.mkdtemp(prefix="steamidra_rclone_"))
            try:
                result = CloudSaves().backup_steam_save(
                    steam_path, steam32_id, int(app_id), game_name, str(tmp),
                    log_func=log_lines.append,
                )
                if not result:
                    return (False, "\n".join(log_lines), "Local backup step failed")
                local_dir = Path(result)
                remote_path = remote_dest.rstrip("/") + "/" + local_dir.name
                _no_win = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
                proc = subprocess.run(
                    [
                        rclone_exe, "copy", str(local_dir), remote_path,
                        "--update",
                        "--transfers", "10", "--checkers", "20",
                        "--create-empty-src-dirs",
                        "--fast-list",
                    ],
                    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300, **_no_win,
                )
                log_lines.append(proc.stdout)
                if proc.returncode == 0:
                    return (True, "\n".join(log_lines), f"Uploaded to {remote_path}")
                log_lines.append(proc.stderr)
                return (False, "\n".join(log_lines), f"rclone failed (exit {proc.returncode})")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def _on_done(result):
            if isinstance(result, tuple):
                ok, log_text, msg = result
                self._emit_task_result("rclone_backup_save", ok, msg, log=log_text)
            else:
                self._emit_task_result("rclone_backup_save", False, "Upload failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def rclone_list_remotes(self, rclone_exe_json):
        """Run rclone listremotes --long and return JSON list of configured remote names."""
        def _do():
            import subprocess
            try:
                rclone_exe = json.loads(rclone_exe_json).get("rclone_exe", "").strip()
            except Exception:
                rclone_exe = ""
            if not rclone_exe:
                bundled = WebBridge._get_bundled_tool_path("rclone")
                rclone_exe = str(bundled) if bundled else ""
            if not rclone_exe or not Path(rclone_exe).exists():
                return json.dumps({"ok": False, "error": "rclone executable not found"})
            _no_win = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            try:
                proc = subprocess.run(
                    [rclone_exe, "listremotes", "--long"],
                    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15, **_no_win,
                )
                if proc.returncode != 0:
                    return json.dumps({"ok": False, "error": proc.stderr.strip()[:300]})
                remotes = []
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if line:
                        name = line.split()[0]
                        remotes.append(name)
                return json.dumps({"ok": True, "remotes": remotes})
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})

        def _on_done(result):
            try:
                parsed = json.loads(result or "{}")
            except Exception:
                parsed = {}
            if parsed.get("ok"):
                self._emit_task_result("rclone_list_remotes", True, "", remotes=parsed.get("remotes", []))
            else:
                self._emit_task_result("rclone_list_remotes", False, "", error=parsed.get("error", "Failed to list remotes"))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def rclone_test_remote(self, config_json):
        """Test an rclone remote by running lsd with a short timeout. Returns JSON ok/error."""
        def _do():
            import subprocess
            config = json.loads(config_json)
            rclone_exe = config.get("rclone_exe", "").strip()
            remote = config.get("remote", "").strip()
            if not rclone_exe:
                bundled = WebBridge._get_bundled_tool_path("rclone")
                rclone_exe = str(bundled) if bundled else ""
            if not rclone_exe or not Path(rclone_exe).exists():
                return json.dumps({"ok": False, "error": "rclone executable not found"})
            if not remote:
                return json.dumps({"ok": False, "error": "No remote specified"})
            # Test only the remote root — the backup subfolder may not exist yet
            remote_root = remote.split(":")[0] + ":" if ":" in remote else remote + ":"
            _no_win = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            try:
                proc = subprocess.run(
                    [rclone_exe, "lsd", remote_root, "--max-depth", "1", "--timeout", "15s"],
                    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=20, **_no_win,
                )
                if proc.returncode == 0:
                    return json.dumps({"ok": True})
                return json.dumps({"ok": False, "error": proc.stderr.strip()[:300]})
            except subprocess.TimeoutExpired:
                return json.dumps({"ok": False, "error": "Timed out after 20s"})
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})

        def _on_done(result):
            try:
                parsed = json.loads(result or "{}")
            except Exception:
                parsed = {}
            if parsed.get("ok"):
                self._emit_task_result("rclone_test_remote", True, "")
            else:
                self._emit_task_result("rclone_test_remote", False, "", error=parsed.get("error", "Remote test failed")[:300])

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def rclone_open_config(self, rclone_exe_json):
        """Open rclone config in a new terminal window so the user can add or edit remotes."""
        import sys
        import subprocess
        try:
            rclone_exe = json.loads(rclone_exe_json).get("rclone_exe", "").strip()
        except Exception:
            rclone_exe = ""
        if not rclone_exe:
            bundled = WebBridge._get_bundled_tool_path("rclone")
            rclone_exe = str(bundled) if bundled else ""
        if not rclone_exe or not Path(rclone_exe).exists():
            self._emit_task_result("rclone_open_config", False, "", error="rclone executable not found")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    ["cmd", "/k", rclone_exe, "config"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                cmd = [rclone_exe, "config"]
                launched = False
                for term, args in [
                    ("x-terminal-emulator", ["-e"]),
                    ("gnome-terminal", ["--"]),
                    ("xterm", ["-e"]),
                    ("konsole", ["-e"]),
                    ("xfce4-terminal", ["-e"]),
                ]:
                    try:
                        subprocess.Popen([term] + args + cmd)
                        launched = True
                        break
                    except FileNotFoundError:
                        continue
                if not launched:
                    self._emit_task_result("rclone_open_config", False, "", error="No terminal emulator found. Open a terminal and run: rclone config")
                    return
            self._emit_task_result("rclone_open_config", True, "")
        except Exception as e:
            self._emit_task_result("rclone_open_config", False, "", error=str(e))

    @pyqtSlot(str)
    def open_workshop(self, app_id):
        """Open the workshop browser for a game."""
        try:
            from sff.gui.workshop_browser import open_workshop_browser
            open_workshop_browser(app_id, self.parent())
        except Exception as e:
            logger.exception("open_workshop failed: %s", e)

    @pyqtSlot(str)
    def download_workshop_item(self, params_json):
        """Download a workshop item using 4-method cascade (SteamWebAPI, GGNetwork, SteamCMD).
        params_json: {"app_id": "...", "item_url": "..."} or {"app_id": "...", "item_id": "..."}
        Emits task_finished with task='workshop_download'."""
        def _do():
            try:
                params = json.loads(params_json)
                app_id = str(params.get("app_id", "0"))
                item_url = params.get("item_url") or params.get("item_id") or ""
                from sff.manifest.workshop_dl import (
                    download_workshop_item as _dl,
                    parse_workshop_item_id,
                )
                from sff.storage.settings import get_setting
                from sff.structs import Settings
                item_id = parse_workshop_item_id(item_url)
                if not item_id:
                    return {"success": False, "error": f"Could not parse item ID from: {item_url}"}
                from sff.utils import sff_data_dir
                out_dir = sff_data_dir() / "downloaded_files" / "workshop" / item_id
                user = get_setting(Settings.STEAM_USER) or "anonymous"
                pwd = get_setting(Settings.STEAM_PASS) or ""
                result = _dl(item_id, app_id, out_dir, steam_username=user, steam_password=pwd)
                return result
            except Exception as e:
                return {"success": False, "error": str(e)}

        def _on_done(result):
            result = result or {}
            self._emit_task_result(
                "workshop_download",
                bool(result.get("success")),
                result.get("method") or result.get("error") or "",
                path=result.get("path") or "",
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def workshop_auto_import(self, app_id):
        """Scan local subscribed-mod folders and enqueue every not-yet-downloaded
        workshop item. Emits task_finished with task='workshop_auto_import'.

        The downloader adapter wraps the existing 4-method `download_workshop_item`
        cascade so each enqueue runs through SteamWebAPI -> GGNetwork -> SteamCMD
        -> authenticated SteamCMD just like the manual single-item button.
        """
        def _do():
            try:
                if not self._steam_path:
                    return {"success": False, "error": "Steam path not set"}
                if not str(app_id).strip().isdigit():
                    return {"success": False, "error": f"Invalid App ID: {app_id!r}"}
                aid = int(app_id)

                from sff.manifest.workshop_auto_import import (
                    workshop_auto_import as _impl,
                )
                from sff.manifest.workshop_dl import (
                    download_workshop_item as _dl,
                )
                from sff.storage.settings import get_setting
                from sff.structs import Settings
                from sff.utils import sff_data_dir

                user = get_setting(Settings.STEAM_USER) or "anonymous"
                pwd = get_setting(Settings.STEAM_PASS) or ""

                class _Adapter:
                    """Adapter around download_workshop_item so the auto-import
                    module can call enqueue(app_id, workshop_id) without knowing
                    the cascade or output dir layout."""
                    def enqueue(self, a_id: int, wid: str) -> None:
                        out_dir = sff_data_dir() / "downloaded_files" / "workshop" / wid
                        out_dir.mkdir(parents=True, exist_ok=True)
                        _dl(
                            wid, str(a_id), out_dir,
                            steam_username=user, steam_password=pwd,
                            log=logger.info,
                        )

                return _impl(self._steam_path, aid, _Adapter(), logger.info)
            except Exception as e:
                logger.exception("workshop_auto_import slot failed for app_id=%s", app_id)
                return {"success": False, "error": str(e)}

        def _on_done(result):
            result = result or {}
            success = bool(result.get("success"))
            added = result.get("added") or []
            skipped = result.get("skipped") or []
            found = result.get("found") or []
            if success:
                msg = (
                    f"Imported {len(added)} new, skipped {len(skipped)} already local "
                    f"({len(found)} found)"
                )
            else:
                msg = result.get("error") or "Auto-import failed"
            self._emit_task_result(
                "workshop_auto_import",
                success,
                msg,
                added=added,
                skipped=skipped,
                found=found,
                error=result.get("error") or "",
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def workshop_bypass_download(self, params_json):
        """Ownership-bypass workshop download.

        ``params_json`` shape:
            {"input": "<URL or paste-list or collection URL>",
             "api_key": "<optional override>"}

        Streams ``task_progress`` events per item and finishes with
        ``task_finished`` carrying the aggregate counts. The bypass path
        sends only the Web API key and the UGC CDN GET, never Steam session
        cookies.
        """
        def _do():
            try:
                params = json.loads(params_json)
                raw_input = str(params.get("input") or "").strip()
                override_key = str(params.get("api_key") or "").strip()
                from sff.manifest.workshop_dl import run_bypass_batch
                from sff.storage.settings import get_setting
                from sff.structs import Settings
                from sff.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY

                api_key = override_key
                if not api_key:
                    saved = get_setting(Settings.STEAM_WEB_API_KEY)
                    if isinstance(saved, str) and saved.strip():
                        api_key = saved.strip()
                if not api_key:
                    api_key = _DEFAULT_KEY

                from sff.utils import sff_data_dir
                out_dir = sff_data_dir() / "downloaded_files" / "workshop"

                def _emit_progress(payload):
                    try:
                        self.task_progress.emit(json.dumps(payload))
                    except Exception:
                        logger.debug("task_progress emit failed", exc_info=True)

                summary = run_bypass_batch(
                    raw_input,
                    out_dir,
                    api_key,
                    on_progress=_emit_progress,
                )
                return summary
            except Exception as e:
                logger.exception("workshop_bypass_download failed: %s", e)
                return {"success": False, "error": str(e)}

        def _on_done(result):
            result = result or {}
            self._emit_task_result(
                "workshop_bypass",
                bool(result.get("success")),
                "",
                added=int(result.get("added") or 0),
                failed=int(result.get("failed") or 0),
                error=result.get("error") or "",
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def check_game_update(self, app_id):
        """Compare installed ACF buildid against Steam CM public buildid.
        If Steam CM is newer: download updated manifests and patch the ACF.
        Emits task_finished with task='update_check'."""
        def _do():
            try:
                from pathlib import Path as _Path
                from sff.storage.vdf import get_steam_libs, vdf_load
                from sff.lua.writer import ACFWriter
                from sff.manifest.downloader import ManifestDownloader
                from sff.lua.manager import LuaManager, LuaChoice, write_manifest_pins_to_lua
                from sff.steam_client import create_provider_for_current_thread
                from sff.storage.settings import get_setting
                from sff.structs import OSType, Settings
                from sff.steam_tools_compat import install_lua_to_steam

                steam_libs = get_steam_libs(self._steam_path) if self._steam_path else []
                acf_path = None
                lib_path = None
                for lib in steam_libs:
                    candidate = lib / "steamapps" / f"appmanifest_{app_id}.acf"
                    if candidate.exists():
                        acf_path = candidate
                        lib_path = lib
                        break

                if acf_path is None:
                    return {"found": False, "error": f"ACF not found for App ID {app_id}"}

                acf_data = vdf_load(acf_path)
                state = acf_data.get("AppState", {})
                installed_buildid = str(state.get("buildid", "0")).strip()

                provider = create_provider_for_current_thread()
                app_data = provider.get_single_app_info(int(app_id))
                cm_buildid = str(
                    app_data.get("depots", {})
                    .get("branches", {})
                    .get("public", {})
                    .get("buildid", "0")
                ).strip()

                if not cm_buildid or cm_buildid == "0":
                    return {"found": True, "error": "Could not retrieve buildid from Steam CM"}

                if installed_buildid == cm_buildid:
                    return {
                        "found": True,
                        "up_to_date": True,
                        "installed_buildid": installed_buildid,
                        "cm_buildid": cm_buildid,
                    }

                os_type = OSType.WINDOWS if sys.platform == "win32" else OSType.LINUX
                lua_manager = LuaManager(os_type)
                saved_lua_path = _Path.cwd() / "saved_lua" / f"{app_id}.lua"
                if not saved_lua_path.exists():
                    new_manifest_map = {}
                    depots = app_data.get("depots", {}) if isinstance(app_data, dict) else {}
                    for depot_id, depot_data in depots.items():
                        if not str(depot_id).isdigit() or not isinstance(depot_data, dict):
                            continue
                        public_manifest = (
                            depot_data.get("manifests", {})
                            .get("public", {})
                        )
                        gid = ""
                        if isinstance(public_manifest, dict):
                            gid = str(public_manifest.get("gid") or "").strip()
                        elif public_manifest:
                            gid = str(public_manifest).strip()
                        if gid and gid.isdigit():
                            new_manifest_map[str(depot_id)] = gid

                    if new_manifest_map:
                        acf_writer = ACFWriter(lib_path)
                        acf_writer.patch_acf_depot_manifests(acf_path, new_manifest_map)
                        acf_writer._patch_acf_error_state(acf_path)
                        return {
                            "found": True,
                            "up_to_date": False,
                            "updated": True,
                            "acf_only": True,
                            "installed_buildid": installed_buildid,
                            "cm_buildid": cm_buildid,
                            "manifests_updated": 0,
                            "acf_depots_patched": len(new_manifest_map),
                        }

                    return {
                        "found": True,
                        "up_to_date": False,
                        "installed_buildid": installed_buildid,
                        "cm_buildid": cm_buildid,
                        "error": f"No saved .lua for App ID {app_id}. Steam CM did not expose public manifest IDs either, so SteaMidra cannot patch this one automatically.",
                    }

                parsed_lua = lua_manager.fetch_lua(LuaChoice.ADD_LUA, saved_lua_path)
                if parsed_lua is None:
                    return {
                        "found": True,
                        "up_to_date": False,
                        "error": "Failed to parse saved .lua file",
                    }
                parsed_lua.manifest_overrides = {}

                install_lua_to_steam(self._steam_path, str(parsed_lua.app_id), saved_lua_path)

                downloader = ManifestDownloader(provider, self._steam_path)
                use_parallel = get_setting(Settings.USE_PARALLEL_DOWNLOADS)
                if use_parallel:
                    manifest_paths = downloader.download_manifests_parallel(parsed_lua, auto_manifest=True)
                else:
                    manifest_paths = downloader.download_manifests(parsed_lua, auto_manifest=True)

                new_manifest_map = {}
                for mp in (manifest_paths or []):
                    stem = _Path(mp).stem
                    parts = stem.split("_")
                    if len(parts) == 2 and all(p.isdigit() for p in parts):
                        new_manifest_map[parts[0]] = parts[1]

                if new_manifest_map:
                    acf_writer = ACFWriter(lib_path)
                    acf_writer.patch_acf_depot_manifests(acf_path, new_manifest_map)
                    acf_writer._patch_acf_error_state(acf_path)
                    pinned_count = write_manifest_pins_to_lua(saved_lua_path, new_manifest_map)
                    if pinned_count:
                        install_lua_to_steam(self._steam_path, str(parsed_lua.app_id), saved_lua_path)

                return {
                    "found": True,
                    "up_to_date": False,
                    "updated": True,
                    "installed_buildid": installed_buildid,
                    "cm_buildid": cm_buildid,
                    "manifests_updated": len(new_manifest_map),
                    "lua_pins_written": pinned_count if new_manifest_map else 0,
                }

            except Exception as e:
                logger.exception("check_game_update failed: %s", e)
                return {"found": True, "error": str(e)}

        def _on_done(result):
            result = result or {}
            success = bool(result.get("up_to_date") or result.get("updated"))
            msg = ""
            if result.get("up_to_date"):
                msg = f"Already up to date (build {result.get('installed_buildid', '')})"
            elif result.get("updated"):
                if result.get("acf_only"):
                    msg = f"Patched ACF to build {result.get('cm_buildid', '')}. Run Download Games if depotcache manifests are missing."
                else:
                    msg = f"Updated to build {result.get('cm_buildid', '')}"
            elif result.get("error"):
                msg = result["error"]
            # 6.2.5: feed the per-app update-state cache that the badge UI
            # reads through get_game_update_state(). On a network or Steam
            # CM failure, leave the prior entry intact and log the error.
            try:
                self._record_update_state(str(app_id), result)
            except Exception as cache_err:
                logger.debug("update-state cache write failed: %s", cache_err)
            # Strip keys that collide with _emit_task_result's positional params,
            # otherwise we get TypeError: got multiple values for 'success'/'message'/'task'.
            extras = {
                k: v for k, v in result.items()
                if k not in ("error", "success", "message", "task")
            }
            self._emit_task_result("update_check", success, msg, **extras)

        self._run_async(_do, on_done=_on_done)

    # ── 6.2.5: per-game and global update-available toggle ───────

    def _record_update_state(self, app_id_str: str, result: dict) -> None:
        """Write a check_game_update result into the in-memory cache.

        Successful checks (up_to_date or updated) refresh installed and
        CM build ids plus checked_at. A network / Steam CM failure
        leaves the previous cache entry intact and logs at debug level.
        Both code paths emit one INFO log line so debug.log records
        every check outcome (R18.4, R18.5).
        """
        import time as _time
        prev = self._update_state_cache.get(app_id_str, {})
        if not result.get("found"):
            logger.info(
                "update-state: app_id=%s skipped, ACF not found", app_id_str,
            )
            return
        err = result.get("error")
        if err and not (result.get("up_to_date") or result.get("updated")):
            logger.warning(
                "update-state: app_id=%s left stale, error=%s", app_id_str, err,
            )
            return
        installed = str(result.get("installed_buildid") or prev.get("installed_buildid") or "")
        cm = str(result.get("cm_buildid") or prev.get("cm_buildid") or "")
        up_to_date = bool(result.get("up_to_date"))
        enabled = self._app_update_check_enabled(app_id_str)
        self._update_state_cache[app_id_str] = {
            "enabled": enabled,
            "up_to_date": up_to_date,
            "installed_buildid": installed,
            "cm_buildid": cm,
            "checked_at": int(_time.time()),
        }
        if len(self._update_state_cache) > 1500:
            oldest = sorted(self._update_state_cache.items(),
                            key=lambda x: x[1].get("checked_at", 0))[:500]
            for k, _ in oldest:
                del self._update_state_cache[k]
        logger.info(
            "update-state: app_id=%s up_to_date=%s installed=%s cm=%s",
            app_id_str, up_to_date, installed, cm,
        )

    def _app_update_check_enabled(self, app_id_str: str) -> bool:
        """Resolve the effective enabled flag for an app.

        Per-app override wins when present. Otherwise the global gate
        decides. Defaults: GLOBAL_UPDATE_CHECK off (matches the declared
        SettingItem default in `Settings.GLOBAL_UPDATE_CHECK`), no
        override. Users opt in from the global Settings panel or per
        tile in the home page.
        """
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
        except Exception:
            return False
        global_on = get_setting(Settings.GLOBAL_UPDATE_CHECK)
        if global_on is None or global_on == "":
            global_on = False
        if isinstance(global_on, str):
            global_on = global_on.lower() in ("true", "1", "yes", "on")
        raw = get_setting(Settings.UPDATE_CHECK_OVERRIDES) or "{}"
        try:
            overrides = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            overrides = {}
        if app_id_str in overrides:
            return bool(overrides[app_id_str])
        return bool(global_on)

    @pyqtSlot(str, bool, result=str)
    def set_game_update_override(self, app_id, enabled):
        """Toggle the per-game LetUpdate override.

        On True: write `<steam>/config/stplug-in/<appid>/00_LetUpdate_override.lua`
        and stamp Settings.GAME_UPDATE_OVERRIDE so the next session knows.
        On False: remove the override file (and any legacy variants) and
        clear the setting key.

        Returns a JSON string `{"ok": bool, "enabled": bool, "msg": str}`.
        """
        try:
            from sff.let_update_override import set_enabled as _set_lc
            ok = _set_lc(self._steam_path, str(app_id), bool(enabled))
            return json.dumps({
                "ok": bool(ok),
                "enabled": bool(enabled),
                "msg": "" if ok else "Override write failed; check debug.log",
            })
        except Exception as e:
            logger.exception("set_game_update_override failed: %s", e)
            return json.dumps({"ok": False, "enabled": False, "msg": str(e)})

    @pyqtSlot(result=str)
    def let_updates_list_games(self):
        """Return stplug-in Lua files that have manifest pins.

        Checked in the UI means Steam is allowed to auto-update that game,
        implemented by commenting every setManifestid line in that Lua.
        """
        try:
            from sff.lua.update_pins import discover_games, helper_status

            games = discover_games(self._steam_path)
            return json.dumps({
                "ok": True,
                "steam_path": str(self._steam_path or ""),
                "games": games,
                "count": len(games),
                "helper": helper_status(self._steam_path),
            })
        except Exception as e:
            logger.exception("let_updates_list_games failed: %s", e)
            return json.dumps({"ok": False, "error": str(e), "games": []})

    @pyqtSlot(bool, result=str)
    def let_updates_set_helper(self, enabled):
        """Create or remove the global 00_LetUpdate_override.lua helper."""
        try:
            from sff.lua.update_pins import set_helper_enabled

            return json.dumps(set_helper_enabled(self._steam_path, bool(enabled)))
        except Exception as e:
            logger.exception("let_updates_set_helper failed: %s", e)
            return json.dumps({"ok": False, "error": str(e), "enabled": False})

    @pyqtSlot(str, result=str)
    def let_updates_apply(self, payload_json):
        """Apply the per-game Steam auto-update selection."""
        try:
            from sff.lua.update_pins import apply_selection_json

            return apply_selection_json(self._steam_path, payload_json or "{}")
        except Exception as e:
            logger.exception("let_updates_apply failed: %s", e)
            return json.dumps({"ok": False, "error": str(e), "games": []})

    @pyqtSlot(str, result=bool)
    def get_game_update_override(self, app_id):
        """Return whether 00_LetUpdate_override.lua is active for this app."""
        try:
            from sff.let_update_override import is_enabled as _is_lc
            return bool(_is_lc(str(app_id)))
        except Exception:
            return False

    @pyqtSlot(str, bool)
    def set_game_update_check(self, app_id, enabled):
        """Persist the per-app update-check override.

        Stores a JSON map under Settings.UPDATE_CHECK_OVERRIDES so the
        periodic timer and the badge UI both observe the same gate.
        """
        try:
            from sff.storage.settings import get_setting, set_setting
            from sff.structs import Settings
            raw = get_setting(Settings.UPDATE_CHECK_OVERRIDES) or "{}"
            try:
                overrides = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                overrides = {}
            if not isinstance(overrides, dict):
                overrides = {}
            overrides[str(app_id)] = bool(enabled)
            set_setting(Settings.UPDATE_CHECK_OVERRIDES, json.dumps(overrides))
            # Refresh the cached state's enabled flag in-place so the
            # badge UI reflects the toggle without waiting for the next
            # check_game_update tick.
            entry = self._update_state_cache.get(str(app_id))
            if entry is not None:
                entry["enabled"] = bool(enabled)
            logger.info(
                "set_game_update_check: app_id=%s enabled=%s", app_id, enabled,
            )
        except Exception as e:
            logger.exception("set_game_update_check failed: %s", e)

    @pyqtSlot(str, result=str)
    def get_game_update_state(self, app_id):
        """Return the cached update state for an app as a JSON string.

        Fields: enabled, up_to_date, installed_buildid, cm_buildid,
        checked_at. Missing entries return a default with enabled
        resolved against the global gate plus per-app override.
        """
        try:
            key = str(app_id)
            cached = self._update_state_cache.get(key)
            if cached is None:
                state = {
                    "enabled": self._app_update_check_enabled(key),
                    "up_to_date": None,
                    "installed_buildid": None,
                    "cm_buildid": None,
                    "checked_at": 0,
                }
            else:
                state = dict(cached)
                state["enabled"] = self._app_update_check_enabled(key)
            # per-tile state read fires for every game in the library on
            # every refresh tick. silenced; debug.log was drowning.
            return json.dumps(state)
        except Exception as e:
            logger.exception("get_game_update_state failed: %s", e)
            return json.dumps({
                "enabled": True,
                "up_to_date": None,
                "installed_buildid": None,
                "cm_buildid": None,
                "checked_at": 0,
            })

    @pyqtSlot(str, result=str)
    def get_game_branches(self, app_id):
        """Return JSON array of available branches from Steam appinfo.
        Tries fresh fetch first, falls back to cache if Steam CM is down."""
        return self._fetch_branches(app_id, force_refresh=False)

    @pyqtSlot(str, result=str)
    def refresh_game_branches(self, app_id):
        """Force-refresh branches from Steam, ignoring cache."""
        return self._fetch_branches(app_id, force_refresh=True)

    def _fetch_branches(self, app_id, force_refresh=False):
        try:
            from sff.steam_client import create_provider_for_current_thread
            if force_refresh:
                from sff.cache import get_cache
                cache = get_cache()
                cache.invalidate(f"app_info_{app_id}")
            provider = create_provider_for_current_thread()
            info = provider.get_single_app_info(int(app_id))
            depots = info.get("depots", {})
            branches = depots.get("branches", {})
            if not isinstance(branches, dict) or not branches:
                return json.dumps([])
            result = []
            for name, b in branches.items():
                if isinstance(b, dict):
                    result.append({
                        "name": name,
                        "buildid": str(b.get("buildid", "")),
                        "description": str(b.get("description", "")),
                        "password_required": bool(b.get("pwdrequired", False)),
                    })
            result.sort(key=lambda x: (x["name"] != "public", x["name"]))
            return json.dumps(result)
        except Exception as e:
            logger.warning("get_game_branches failed for %s: %s", app_id, e)
            return json.dumps([])

    @pyqtSlot(str, str)
    def ryuu_request_branch(self, app_id, branch):
        """Request a specific branch from Ryuu using the premium API key. Runs async."""
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        api_key = (get_setting(Settings.RYUU_API_KEY) or "").strip()
        if not api_key:
            self._emit_task_result("ryuu_request_branch", False,
                "No Ryuu premium API key set. Add it in Settings.", ok=False)
            return
        def _do():
            import httpx
            try:
                resp = httpx.get(
                    "https://generator.ryuu.lol/requestbranch",
                    params={"appid": str(app_id), "branch": str(branch)},
                    headers={"X-Auth-Key": api_key},
                    timeout=15, follow_redirects=True,
                )
                if resp.status_code == 200:
                    msg = resp.json().get("message", "OK")
                    return {"ok": True, "message": msg}
                return {"ok": False, "error": f"HTTP {resp.status_code}: {(resp.text or '')[:500]}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        def _on_done(result):
            result = result or {"ok": False, "error": "unknown"}
            self._emit_task_result("ryuu_request_branch", bool(result.get("ok")),
                result.get("message") or result.get("error") or "",
                **{k: v for k, v in result.items() if k != "ok"})
        self._run_async(_do, on_done=_on_done)

    def lure_fix_acf(self, app_id):
        """Patch the game's ACF with the latest Steam CM manifest IDs and buildid.
        No files are downloaded — pure ACF update to suppress Steam's update prompt.
        Emits task_finished with task='lure_fix'."""
        def _do():
            try:
                from pathlib import Path as _Path
                from sff.storage.vdf import get_steam_libs, vdf_load, vdf_dump
                from sff.lua.writer import ACFWriter
                from sff.steam_client import create_provider_for_current_thread

                steam_libs = get_steam_libs(self._steam_path) if self._steam_path else []
                acf_path = None
                lib_path = None
                for lib in steam_libs:
                    candidate = lib / "steamapps" / f"appmanifest_{app_id}.acf"
                    if candidate.exists():
                        acf_path = candidate
                        lib_path = lib
                        break

                if acf_path is None:
                    return {"success": False, "error": f"ACF not found for App ID {app_id}"}

                provider = create_provider_for_current_thread()
                app_data = provider.get_single_app_info(int(app_id))
                depots_data = app_data.get("depots", {})

                cm_buildid = str(
                    depots_data.get("branches", {})
                    .get("public", {})
                    .get("buildid", "0")
                ).strip()

                if not cm_buildid or cm_buildid == "0":
                    return {"success": False, "error": "Could not retrieve buildid from Steam CM"}

                acf_data = vdf_load(acf_path)
                state = acf_data.get("AppState", {})
                installed = state.get("InstalledDepots", {})

                new_manifest_map = {}
                for depot_id in list(installed.keys()):
                    mani_pub = (
                        depots_data.get(str(depot_id), {})
                        .get("manifests", {})
                        .get("public", {})
                    )
                    if isinstance(mani_pub, dict):
                        gid = mani_pub.get("gid")
                    else:
                        gid = mani_pub
                    if gid:
                        new_manifest_map[depot_id] = str(gid)

                if new_manifest_map:
                    acf_writer = ACFWriter(lib_path)
                    acf_writer.patch_acf_depot_manifests(acf_path, new_manifest_map)

                acf_data = vdf_load(acf_path)
                state = acf_data.get("AppState", {})
                state["buildid"] = cm_buildid
                state["StateFlags"] = "4"
                state["TargetBuildID"] = "0"
                state["DownloadType"] = "0"
                state["UpdateResult"] = "0"
                state["ScheduledAutoUpdate"] = "0"
                state["BytesToDownload"] = "0"
                state["BytesDownloaded"] = "0"
                state["BytesToStage"] = "0"
                state["BytesStaged"] = "0"
                acf_data["AppState"] = state
                vdf_dump(acf_path, acf_data)
                try:
                    os.chmod(acf_path, 0o444)
                except OSError:
                    pass

                return {
                    "success": True,
                    "cm_buildid": cm_buildid,
                    "depots_patched": len(new_manifest_map),
                }

            except Exception as e:
                logger.exception("lure_fix_acf failed: %s", e)
                return {"success": False, "error": str(e)}

        def _on_done(result):
            result = result or {}
            if result.get("success"):
                msg = (
                    f"ACF patched to build {result.get('cm_buildid', '')} "
                    f"({result.get('depots_patched', 0)} depot(s)). Restart Steam."
                )
            else:
                msg = result.get("error", "Lure fix failed")
            # Strip keys that collide with _emit_task_result's positional params.
            # The previous code spread the whole `result` dict and crashed on
            # success because `success` and `message` would arrive twice (once
            # positional, once keyword) — TypeError, propagated through Qt signal
            # delivery, which closed the whole window.
            extras = {
                k: v for k, v in result.items()
                if k not in ("error", "success", "message", "task")
            }
            self._emit_task_result("lure_fix", bool(result.get("success")), msg, **extras)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def restart_steam(self):
        """Restart or launch Steam."""
        def _do():
            if sys.platform == "win32":
                import time
                from sff.processes import (
                    SteamProcess,
                    is_proc_running,
                    launch_steam_unelevated,
                )

                if not self._steam_path:
                    return (False, "Steam path not set")

                steam_proc = SteamProcess(self._steam_path)

                if is_proc_running(steam_proc.exe_name):
                    self.download_progress.emit(json.dumps({
                        "status": "Stopping Steam", "progress": 30, "restart": True
                    }))
                    steam_proc.kill()
                    max_wait = 10
                    waited = 0
                    while is_proc_running(steam_proc.exe_name) and waited < max_wait:
                        time.sleep(0.5)
                        waited += 0.5
                    if is_proc_running(steam_proc.exe_name):
                        return (False, "Steam did not close in time — try again")

                self.download_progress.emit(json.dumps({
                    "status": "Starting Steam", "progress": 60, "restart": True
                }))
                injector = self._steam_path / "steam.exe"
                ok, msg = launch_steam_unelevated(injector, self._steam_path)
                return (ok, msg)

            else:
                from sff.linux.steam_process import kill_steam, start_steam
                kill_steam()
                result = start_steam(steam_path=self._steam_path)
                if result == "SUCCESS":
                    return (True, "Steam restarted")
                return (False, f"Steam start failed: {result}")

        def _on_done(result):
            if isinstance(result, tuple):
                success, msg = result
            else:
                success, msg = bool(result), "Steam restarted" if result else "Failed to restart Steam"
            self._emit_task_result("restart_steam", success, msg)

        def _on_error(error_msg):
            self._emit_task_result("restart_steam", False, error_msg)

        self._run_async(_do, on_done=_on_done, on_error=_on_error)

    @pyqtSlot()
    def open_log_window(self):
        """Opens the existing GlobalLogWindow as a standalone native window."""
        parent = self.parent()
        if hasattr(parent, '_log_window'):
            parent._log_window.show()
            parent._log_window.raise_()
            parent._log_window.activateWindow()

    @pyqtSlot(str)
    def copy_to_clipboard(self, text):
        """Copy text to system clipboard via Qt (works in QWebEngine)."""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    @pyqtSlot(result=str)
    def browse_game_folder(self):
        """Open a native folder-picker dialog and return the selected path (or '')."""
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self.parent(), "Select game folder")
        return path or ""

    @pyqtSlot(str, str, str)
    @pyqtSlot(str, str, str, str)
    def run_game_action_outside(self, game_path, game_name_or_app_id, app_id_or_action, action=None):
        """Run a game action against a folder outside the Steam library.
        Builds ACFInfo from the explicit path instead of scanning steamapps."""
        from pathlib import Path as _Path
        from sff.game_specific import ACFInfo

        if action is None:
            game_name = ""
            app_id = game_name_or_app_id
            action = app_id_or_action
        else:
            game_name = (game_name_or_app_id or "").strip()
            app_id = app_id_or_action

        p = _Path(game_path)
        if not p.is_dir():
            self._emit_task_result(action, False, f"Folder not found: {game_path}")
            return

        acf = ACFInfo(app_id or "0", p, game_name)

        if action == "steam_auto":
            from sff.steamauto import get_steamauto_cli_path
            if get_steamauto_cli_path() is None:
                self._emit_task_result("steam_auto", False, "SteamAutoCrack CLI not found")
                return
            parent = self.parent()
            if parent and hasattr(parent, '_run_steam_auto_with_acf'):
                # Web UI showed its own confirm dialog already — suppress the
                # Qt-side double-prompt for this single delegate call.
                setattr(parent, '_skip_next_achievement_warn', True)
                parent._run_steam_auto_with_acf(acf)
            return

        if action == "steamstub":
            parent = self.parent()
            if parent and hasattr(parent, "_run_steamless_for_acf"):
                parent._run_steamless_for_acf(acf)
            return

        def _do():
            from sff.structs import MainMenu, MainReturnCode
            game_action_map = {
                "crack": MainMenu.CRACK_GAME,
                "steamstub": MainMenu.REMOVE_DRM,
                "dlc_check": MainMenu.DLC_CHECK,
                "workshop": MainMenu.DL_WORKSHOP_ITEM,
                "multiplayer": MainMenu.MULTIPLAYER_FIX,
                "community_fixes": MainMenu.CRACK_FIX,
                "hv_fix": MainMenu.HV_FIX,
                "achievements": MainMenu.DL_USER_GAME_STATS,
                "dlc_unlockers": MainMenu.MANAGE_DLC_UNLOCKERS,
                "check_mod_updates": MainMenu.CHECK_MOD_UPDATES,
            }
            menu_choice = game_action_map.get(action)
            if menu_choice is None:
                return f"Unknown action: {action}"
            if action == "steamstub":
                parent = self.parent()
                if parent and hasattr(parent, "_run_steamless_for_acf"):
                    parent._run_steamless_for_acf(acf)
                    return "__handled_no_toast__"
            try:
                result = self._ui.run_game_action_with_selection(menu_choice, acf)
                if isinstance(result, tuple) and len(result) == 2:
                    ok, msg = result
                    self._emit_task_result(action, bool(ok), str(msg))
                    return "__handled_no_toast__"
                if result is False or result is MainReturnCode.EXIT:
                    return f"Action '{action}' failed"
                if result is MainReturnCode.LOOP_NO_PROMPT:
                    return "__handled_no_toast__"
                return None
            except Exception as e:
                return str(e)

        def _on_done(error_msg):
            if error_msg == "__handled_no_toast__":
                return
            if error_msg:
                self._emit_task_result(action, False, str(error_msg))
            # A None/empty result means the legacy menu flow either handled
            # its own UI, was cancelled, or did not report a result. Do not
            # show a green success toast for that ambiguous state.

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def install_lumacore(self, steam_path_str, variant=""):
        """Copy LumaCore DLLs into the Steam folder and clean up legacy injection files.

        *variant* picks the build flavour ('release' default or 'debug').
        The Auto LC Setup modal radio buttons send 'debug' when the user
        wants the verbose-logging build for support sessions.
        """
        def _do():
            from pathlib import Path
            from sff.lumacore_setup import install_lumacore
            steam_path = Path(steam_path_str) if steam_path_str else self._ui.steam_path
            def _progress(msg):
                self.lc_progress.emit(msg)
            picked = (variant or "release").strip().lower()
            if picked not in ("release", "debug"):
                picked = "release"
            success, message = install_lumacore(steam_path, _progress, variant=picked)
            return success, message

        def _on_done(result):
            success, message = result if isinstance(result, tuple) else (False, str(result))
            self._emit_task_result("auto_lc_setup", success, message)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(result=str)
    def steam_updates_get_state(self):
        """Return 'blocked', 'unblocked', or 'unknown' based on the
        BootStrapperInhibitAll line in <steam>/steam.cfg.

        - blocked   : steam.cfg exists AND the line is set to Enable/true/1
        - unblocked : steam.cfg exists AND the line is set to False/0/no
        - unknown   : file missing OR no BootStrapperInhibitAll line found
        """
        try:
            steam_path = self._steam_path
            if not steam_path:
                return "unknown"
            cfg_path = steam_path / "steam.cfg"
            if not cfg_path.is_file():
                return "unknown"
            text = cfg_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key, _, val = stripped.partition("=")
                if key.strip().lower() != "bootstrapperinhibitall":
                    continue
                normalised = val.strip().lower()
                if normalised in ("enable", "enabled", "true", "1", "yes"):
                    return "blocked"
                if normalised in ("false", "0", "no", "disable", "disabled"):
                    return "unblocked"
                return "unknown"
            return "unknown"
        except Exception as exc:
            logger.warning("steam_updates_get_state failed: %s", exc)
            return "unknown"

    @pyqtSlot(str, result=str)
    def steam_updates_set_state(self, action):
        """Write or update the BootStrapperInhibitAll line in
        <steam>/steam.cfg based on `action`.

        action = 'block'   sets BootStrapperInhibitAll=Enable
        action = 'unblock' sets BootStrapperInhibitAll=False

        Preserves any other lines already in steam.cfg. Creates the file
        when it doesn't exist. Returns the new state ('blocked', 'unblocked')
        on success, or an error message string on failure.
        """
        try:
            steam_path = self._steam_path
            if not steam_path:
                return "Steam path not set"
            cfg_path = steam_path / "steam.cfg"

            normalised = (action or "").strip().lower()
            if normalised == "block":
                new_value = "Enable"
                final_state = "blocked"
            elif normalised == "unblock":
                new_value = "False"
                final_state = "unblocked"
            else:
                return f"unknown action: {action!r}"

            existing_lines = []
            if cfg_path.is_file():
                existing_lines = cfg_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()

            replaced = False
            new_lines = []
            for line in existing_lines:
                stripped = line.strip()
                if "=" in stripped and not stripped.startswith("#"):
                    key, _, _ = stripped.partition("=")
                    if key.strip().lower() == "bootstrapperinhibitall":
                        new_lines.append(f"BootStrapperInhibitAll={new_value}")
                        replaced = True
                        continue
                new_lines.append(line)
            if not replaced:
                new_lines.append(f"BootStrapperInhibitAll={new_value}")

            body = "\n".join(new_lines).rstrip() + "\n"
            cfg_path.write_text(body, encoding="utf-8")
            logger.info(
                "steam_updates_set_state: %s -> %s (%s)",
                final_state, cfg_path, new_value,
            )
            return final_state
        except Exception as exc:
            logger.warning("steam_updates_set_state failed: %s", exc)
            return f"write failed: {exc}"

    @pyqtSlot(str, result=str)
    def lumacore_check_update(self, _arg=""):
        """Return JSON {installed, latest, update_available, source} for the
        Settings / Home update banner. Honours the 6-hour cooldown so the
        first call after launch hits GitHub and subsequent calls reuse the
        cached answer.

        Accepts an unused string argument because the JS bridge calls this
        through callWithCallback, which always sends the leading argument
        before the callback. Slots without a parameter slot were silently
        dropped, so the modal never repopulated.

        When the argument is the literal string "force", the cooldown is
        bypassed and a fresh probe hits GitHub. Used by the Check for
        updates button so users get an answer they can trust.
        """
        try:
            from sff.lumacore_setup import check_for_lumacore_update
            force = (str(_arg).strip().lower() == "force")
            data = check_for_lumacore_update(self._steam_path, force=force)
            return json.dumps(data)
        except Exception as exc:
            logger.warning("lumacore_check_update failed: %s", exc)
            return json.dumps({
                "installed": "",
                "latest": "",
                "update_available": False,
                "source": "error",
                "error": str(exc),
            })

    @pyqtSlot()
    def lumacore_deactivate(self):
        """Close Steam, remove LumaCore + dwmapi + lcoverlay DLLs, clear the
        installed-version cache. Emits lc_progress for each step and
        task_finished{auto_lc_deactivate} when done.
        """
        def _do():
            from sff.lumacore_setup import deactivate_lumacore
            def _progress(msg):
                self.lc_progress.emit(msg)
            success, message = deactivate_lumacore(self._steam_path, _progress)
            return success, message

        def _on_done(result):
            success, message = result if isinstance(result, tuple) else (False, str(result))
            self._emit_task_result("auto_lc_deactivate", success, message)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def toggle_online_fix(self, app_id):
        """Toggle the LC Online Fix launch option for app_id in localconfig.vdf.

        Steam is automatically closed first when running, otherwise it would
        clobber the localconfig.vdf write on next shutdown.
        """
        def _do():
            from sff.launch_options import toggle_online_fix
            from sff.processes import SteamProcess, is_proc_running
            import time

            if sys.platform == "win32" and is_proc_running("steam.exe"):
                print("Closing Steam before toggling LC Online Fix...", flush=True)
                steam_proc = SteamProcess(self._steam_path) if self._steam_path else None
                if steam_proc:
                    steam_proc.kill()
                    waited = 0.0
                    while is_proc_running("steam.exe") and waited < 10.0:
                        time.sleep(0.5)
                        waited += 0.5
                    if is_proc_running("steam.exe"):
                        return False, "Steam did not close in time. Close it manually and try again."
                    print("Steam closed.", flush=True)

            success, message = toggle_online_fix(self._ui.steam_path, app_id)
            return success, message

        def _on_done(result):
            success, message = result if isinstance(result, tuple) else (False, str(result))
            self._emit_task_result("lc_online_fix", success, message)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, result=str)
    def get_launch_option_status(self, app_id):
        """Return a human-readable string describing the current LC Online Fix state for app_id."""
        try:
            from sff.launch_options import online_fix_enabled
            enabled = online_fix_enabled(self._ui.steam_path, app_id)
            return "LC Online Fix: enabled" if enabled else "LC Online Fix: disabled"
        except Exception as exc:
            return f"Error: {exc}"

    # ── SYNC slots — fast, no I/O ────────────────────────────────

    @pyqtSlot(result=str)
    def get_applist_games(self):
        """Returns JSON list of {app_id, name} for installed Steam games with saved .lua files."""
        try:
            from pathlib import Path as _Path
            saved_lua = _Path().cwd() / "saved_lua"
            saved_ids = {p.stem for p in saved_lua.glob("*.lua")} if saved_lua.exists() else set()
            installed = json.loads(self.get_installed_games())
            games = [
                {"app_id": str(g["app_id"]), "name": g["name"]}
                for g in installed
                if str(g["app_id"]) in saved_ids
            ]
            games.sort(key=lambda x: x["name"].lower())
            return json.dumps(games)
        except Exception as e:
            logger.warning("get_applist_games failed: %s", e)
            return json.dumps([])

    @pyqtSlot(result=str)
    def get_platform(self):
        """Returns 'win32' or 'linux'."""
        return sys.platform

    @pyqtSlot(result=str)
    def get_app_version(self):
        """Returns the current SteaMidra version string."""
        from sff.strings import VERSION
        return VERSION

    @pyqtSlot(str, result=str)
    def app_update_check(self, _arg=""):
        """Return the current GitHub update status for the Settings button."""
        try:
            from sff.strings import VERSION
            from sff.updater import Updater
            is_newer, release = Updater.update_available()
            if release is None:
                return json.dumps({
                    "ok": False,
                    "update_available": False,
                    "current": VERSION,
                    "latest": "",
                    "message": "Could not fetch the latest release.",
                })
            latest = (release.get("tag_name") or "").strip()
            return json.dumps({
                "ok": True,
                "update_available": bool(is_newer),
                "current": VERSION,
                "latest": latest,
                "release_url": release.get("html_url") or "",
            })
        except Exception as exc:
            logger.warning("app_update_check failed: %s", exc)
            return json.dumps({
                "ok": False,
                "update_available": False,
                "current": "",
                "latest": "",
                "message": str(exc),
            })

    @pyqtSlot(str, result=str)
    def get_disk_usage(self, path):
        """Return disk usage JSON {total, used, free} for the given path."""
        import shutil
        import json as _json
        try:
            usage = shutil.disk_usage(path)
            return _json.dumps({"total": usage.total, "used": usage.used, "free": usage.free})
        except Exception:
            return _json.dumps({"error": True})

    @pyqtSlot(str)
    def connect_store(self, api_key):
        """Validates and stores Hubcap API key."""
        if not api_key or not api_key.strip():
            self._emit_task_result("store_connect", False, "API key is empty")
            return
        from sff.store_browser import StoreApiClient
        if not StoreApiClient.validate_api_key(api_key):
            self._emit_task_result("store_connect", False, "Invalid API key — must start with smm_ and be at least 10 characters")
            return
        self._api_key = api_key
        self._store_client = StoreApiClient(api_key)
        self._hubcap_unavailable = False
        from sff.storage.settings import set_setting
        from sff.structs import Settings
        set_setting(Settings.HUBCAP_KEY, api_key)
        self.task_finished.emit(json.dumps({"task": "api_key_connected"}))

    @pyqtSlot()
    def store_disconnect(self):
        """Disconnect Hubcap store — clear key and fall back to Steam search."""
        self._store_client = None
        self._api_key = None
        self._hubcap_unavailable = True
        try:
            from sff.storage.settings import clear_setting
            from sff.structs import Settings
            clear_setting(Settings.HUBCAP_KEY)
        except Exception:
            pass
        self.task_finished.emit(json.dumps({"task": "store_disconnected"}))

    @pyqtSlot(str)
    def save_ryuu_key(self, key):
        """Save Ryuu API key to settings."""
        from sff.storage.settings import set_setting as _set
        from sff.structs import Settings
        try:
            _set(Settings.RYUU_KEY, key.strip())
            self.task_finished.emit(json.dumps({"task": "ryuu_key_saved", "success": True}))
        except Exception as e:
            logger.warning("Failed to save Ryuu key: %s", e)
            self._emit_task_result("ryuu_key_saved", False, f"Failed to save key: {e}")

    @pyqtSlot()
    def test_ryuu_key(self):
        """Probe the Ryuu test/refresh endpoint with appid=440 to verify the saved key.

        Emits ``task_finished`` with task=``test_ryuu_key`` and a payload
        shaped like ``{ok: True}``, ``{ok: False, reason: 'appid not in db'}``,
        or ``{ok: False, status: <code>, body: <truncated_body>}``. When no
        key is configured we return ``{ok: False, reason: 'no_api_key'}``
        without firing any HTTP request — never send an empty ``auth_code``.
        """
        from sff.storage.settings import get_setting
        from sff.structs import Settings

        key = (get_setting(Settings.RYUU_KEY) or "").strip()
        if not key:
            self._emit_task_result(
                "test_ryuu_key", False, "", ok=False, reason="no_api_key"
            )
            return

        def _do():
            import httpx as _httpx
            # Try old endpoint first (auth_code param, normal users)
            try:
                resp = _httpx.get("https://generator.ryuu.lol/resellerrequestupdate",
                    params={"appid": "440", "auth_code": key}, timeout=30, follow_redirects=True)
                if resp.status_code == 200:
                    return {"ok": True}
            except Exception:
                pass
            # Fall back to new endpoint (X-Auth-Key header, premium users)
            try:
                resp = _httpx.get("https://generator.ryuu.lol/requestupdate",
                    params={"appid": "440"}, headers={"X-Auth-Key": key}, timeout=30, follow_redirects=True)
            except Exception as e:
                return {"ok": False, "error": str(e)}
            if resp.status_code == 200:
                return {"ok": True}
            if resp.status_code == 400:
                return {"ok": False, "reason": "appid not in db"}
            return {
                "ok": False,
                "status": resp.status_code,
                "body": (resp.text or "")[:4096],
            }

        def _on_done(result):
            result = result or {"ok": False, "error": "unknown"}
            self._emit_task_result(
                "test_ryuu_key",
                bool(result.get("ok")),
                "",
                **{k: v for k, v in result.items() if k != "ok"},
                ok=bool(result.get("ok")),
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def test_ryuu_api_key(self):
        """Test the premium Ryuu API key (X-Auth-Key header) against the requestupdate endpoint."""
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        key = (get_setting(Settings.RYUU_API_KEY) or "").strip()
        if not key:
            self._emit_task_result("test_ryuu_api_key", False, "", ok=False, reason="no_api_key")
            return
        def _do():
            import httpx as _httpx
            try:
                resp = _httpx.get("https://generator.ryuu.lol/requestupdate",
                    params={"appid": "440"}, headers={"X-Auth-Key": key}, timeout=30, follow_redirects=True)
                if resp.status_code == 200:
                    return {"ok": True}
                return {"ok": False, "status": resp.status_code, "body": (resp.text or "")[:4096]}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        def _on_done(result):
            result = result or {"ok": False, "error": "unknown"}
            self._emit_task_result("test_ryuu_api_key", bool(result.get("ok")), "",
                **{k: v for k, v in result.items() if k != "ok"}, ok=bool(result.get("ok")))
        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(result=str)
    def get_stored_api_key(self):
        """Returns saved API key from settings (may be empty)."""
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        key = get_setting(Settings.HUBCAP_KEY)
        if key:
            self._api_key = key
        return key or ""

    @pyqtSlot(str)
    def open_url(self, url):
        """Open a URL in the system default browser."""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))

    @pyqtSlot(str)
    def launch_game(self, app_id):
        app_id = str(app_id or "").strip()
        if not app_id.isdigit():
            self._emit_task_result("launch_game", False, f"Invalid App ID: {app_id!r}", app_id=app_id)
            return
        try:
            acf = self._resolve_acf(app_id)
            game_dir = Path(getattr(acf, "path", "") or "")
            if not game_dir.exists():
                raise FileNotFoundError("Installed game folder not found")

            def _is_linux_binary(path: Path) -> bool:
                try:
                    if not path.is_file() or not os.access(path, os.X_OK):
                        return False
                    with path.open("rb") as fh:
                        return fh.read(4) == b"\x7fELF"
                except Exception:
                    return False

            def _score(path: Path) -> tuple:
                name = path.name.lower()
                bad = any(x in name for x in ("unins", "unitycrash", "crashpad", "redist", "setup", "install"))
                depth = len(path.relative_to(game_dir).parts)
                return (1 if bad else 0, depth, len(path.name), str(path).lower())

            if sys.platform == "win32":
                candidates = [p for p in game_dir.rglob("*.exe") if p.is_file()]
            else:
                candidates = [p for p in game_dir.rglob("*") if _is_linux_binary(p)]

            if not candidates:
                raise FileNotFoundError("No executable found in game folder")
            exe = sorted(candidates, key=_score)[0]
            subprocess.Popen([str(exe)], cwd=str(exe.parent))
            self._emit_task_result("launch_game", True, f"Launched {exe.name}", app_id=app_id, path=str(exe))
        except Exception as exc:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            ok = QDesktopServices.openUrl(QUrl(f"steam://run/{app_id}"))
            self._emit_task_result(
                "launch_game",
                bool(ok),
                "Executable launch failed, sent launch to Steam" if ok else f"Could not launch game: {exc}",
                app_id=app_id,
            )

    @pyqtSlot(str, str)
    def set_setting(self, key, value):
        """Set a setting by key name, then apply it live (same as classic UI)."""
        from sff.storage.settings import set_setting as _set
        from sff.structs import Settings
        for s in Settings:
            if s.key_name == key or s.name.lower() == key.lower():
                # Convert string "True"/"False" to real bool for bool-typed settings
                if s.type == bool:
                    value = value in ('True', 'true', '1')
                try:
                    _set(s, value)
                except Exception as e:
                    logger.warning("Failed to save setting %s=%s: %s", key, value, e)
                # A17: flipping store_show_software invalidates the Steam
                # applist cache so the next Store browse rebuilds the
                # list with the new filter. Drop the in-memory cache and
                # nuke the on-disk all_games.txt mirror in lockstep.
                if s.key_name == "store_show_software":
                    try:
                        global _STEAM_APPLIST_CACHE, _STEAM_APPLIST_CACHE_TIME
                        _STEAM_APPLIST_CACHE = None
                        _STEAM_APPLIST_CACHE_TIME = 0.0
                        # Defence-in-depth: drop the Store grid cache so
                        # list_games rebuilds with the fresh toggle on
                        # the next round trip.
                        try:
                            from sff import store_browser as _sb
                            _sb._cached_grid = None
                        except Exception:
                            pass
                        from sff.utils import root_folder
                        _all_games = root_folder(outside_internal=True) / "all_games.txt"
                        if _all_games.exists():
                            _all_games.unlink()
                    except Exception as _e:
                        logger.debug("store_show_software cache flush failed: %s", _e)
                # Apply live so changes take effect immediately
                parent = self.parent()
                if parent and hasattr(parent, '_apply_setting_live'):
                    try:
                        parent._apply_setting_live(s)
                    except Exception as e:
                        logger.warning("_apply_setting_live(%s) failed: %s", key, e)
                return

    @pyqtSlot(str, result=str)
    def get_setting(self, key):
        """Get a setting by key name."""
        from sff.storage.settings import get_setting as _get
        from sff.structs import Settings
        for s in Settings:
            if s.key_name == key or s.name.lower() == key.lower():
                val = _get(s)
                return str(val) if val is not None else ""
        return ""

    @pyqtSlot(result=str)
    def provider_contribute_preview(self):
        """Return a privacy-safe count of keys that would be submitted."""
        try:
            from sff.lua.provider import collect_submit_candidates

            data = collect_submit_candidates(self._steam_path)
            return json.dumps({
                "valid": data["valid"],
                "invalid": data["invalid"],
                "duplicates": data["duplicates"],
                "already_submitted": data.get("already_submitted", 0),
                "items": data["items"][:200],
            })
        except Exception as exc:
            logger.warning("provider_contribute_preview failed: %s", exc)
            return json.dumps({"valid": 0, "invalid": 0, "duplicates": 0, "already_submitted": 0, "items": [], "error": str(exc)})

    @pyqtSlot(str)
    def provider_contribute_submit(self, mode="manual"):
        """Submit clean provider keys in the background."""
        def _do():
            from sff.lua.provider import (
                collect_submit_candidates,
                enrich_submit_items_with_steam_appinfo,
                mark_contributor_run,
                submit_items,
            )
            from sff.storage.settings import get_setting
            from sff.structs import Settings

            data = collect_submit_candidates(self._steam_path)
            enrich_stats = {"enabled": False}
            if get_setting(Settings.PROVIDER_ENRICH_STEAM_METADATA):
                enrich_stats = enrich_submit_items_with_steam_appinfo(data["items"])
                data["steam_metadata_enrichment"] = enrich_stats
            if not data["items"]:
                mark_contributor_run()
                return {"ok": True, "already_submitted": True, "accepted": 0, **data}
            result = submit_items(data["items"])
            if result.get("ok"):
                mark_contributor_run()
            return {**data, **result}

        def _on_done(result):
            result = result or {"ok": False, "error": "unknown"}
            already = bool(result.get("already_submitted"))
            ok = bool(result.get("ok"))
            if already:
                msg = "Already submitted"
            elif ok:
                msg = f"Submitted {int(result.get('accepted') or 0)} provider key(s)"
            else:
                msg = result.get("error") or "Provider submission failed"
            self._emit_task_result(
                "provider_contribute",
                ok,
                msg,
                mode=mode,
                valid=int(result.get("valid") or 0),
                invalid=int(result.get("invalid") or 0),
                duplicates=int(result.get("duplicates") or 0),
                already_submitted_count=int(result.get("already_submitted") or 0),
                accepted=int(result.get("accepted") or 0),
                already_submitted=already,
                submission_ids=result.get("submission_ids") or [],
                steam_metadata_enrichment=result.get("steam_metadata_enrichment") or {},
                error=result.get("error") or "",
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def provider_update_now(self):
        """Download the latest provider JSON to the AppData cache."""
        def _do():
            from sff.lua.provider import download_provider_update
            return download_provider_update()

        def _on_done(result):
            result = result or {"ok": False, "errors": ["unknown"]}
            ok = bool(result.get("ok"))
            msg = (
                f"Provider updated from {result.get('url', '')} ({result.get('count', 0)} entries)"
                if ok else
                "Provider update failed: " + "; ".join(result.get("errors") or [])
            )
            self._emit_task_result("provider_update", ok, msg, **result)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(result=str)
    def get_provider_cache_status(self):
        try:
            from sff.lua.provider import provider_update_state, load_provider

            data = provider_update_state()
            data["count"] = len(load_provider())
            return json.dumps(data)
        except Exception as exc:
            return json.dumps({
                "last_attempt_at": 0,
                "last_success_at": 0,
                "last_error": str(exc),
                "count": 0,
                "due": True,
                "interval_seconds": 6 * 60 * 60,
            })

    @pyqtSlot()
    def linux_setup_now(self):
        """Rerun Linux SLSsteam and .NET setup."""
        def _do():
            if not sys.platform.startswith("linux"):
                return (False, "Linux setup is only available on Linux.")
            log_lines: list[str] = []
            try:
                from pathlib import Path as _Path
                from sff.linux.slssteam import detect_steam_type, install_from_github, setup_via_headcrab
                from sff.dotnet_utils import ensure_dotnet_9

                if detect_steam_type() == "flatpak":
                    steam_path = _Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam"
                else:
                    steam_path = _Path.home() / ".steam" / "steam"
                ok = setup_via_headcrab(steam_path, log_lines.append)
                if not ok:
                    log_lines.append("headcrab failed, falling back to direct SLSsteam install...")
                    install_from_github(steam_path, log_lines.append)
                ensure_dotnet_9(print_fn=log_lines.append)
                return (True, "\n".join(str(x) for x in log_lines) or "Linux setup completed.")
            except Exception as exc:
                logger.exception("linux_setup_now failed: %s", exc)
                return (False, str(exc))

        def _on_done(result):
            ok, msg = result if isinstance(result, tuple) else (False, "Linux setup failed")
            self._emit_task_result("linux_setup", ok, msg)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, result=str)
    def get_webui_translations(self, lang):
        """Return the webui translation JSON for the given language."""
        from sff.utils import root_folder
        from pathlib import Path as _Path
        locales_dir = root_folder() / "sff" / "locales"
        if lang in ("Auto", "", None):
            lang = "en"
        path = locales_dir / f"webui_{lang}.json"
        if not path.exists():
            path = locales_dir / "webui_en.json"
        if not path.exists():
            return "{}"
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return "{}"

    @pyqtSlot(result=str)
    def get_steam_libraries(self):
        """Returns JSON array of Steam library paths."""
        from sff.storage.vdf import get_steam_libs
        if not self._steam_path:
            return "[]"
        try:
            libs = get_steam_libs(self._steam_path)
            return json.dumps([str(p) for p in libs])
        except Exception:
            return "[]"

    @pyqtSlot(str)
    def set_active_library(self, path):
        """Sets the library path for the next download."""
        self._active_library = path

    @pyqtSlot(result=str)
    def browse_ddmod_download_folder(self):
        """Open a folder picker for DDMod's direct-download destination."""
        start_dir = ""
        try:
            start_dir = str(self._active_library or self._steam_path or "")
        except Exception:
            start_dir = ""
        path = QFileDialog.getExistingDirectory(
            self.parent(),
            "Select DDMod Download Location",
            start_dir,
        )
        return path or ""

    @pyqtSlot(str, result=str)
    def browse_steam_path(self, _unused=""):
        """Folder picker for the Steam install root. Validates the pick and
        returns the chosen path on success, '' on cancel or invalid pick.
        Updates `self._steam_path` so every other slot picks up the new
        path immediately, then returns it so the frontend can persist it
        through `set_setting('steam_path')` for next launch."""
        from sff.steam_path import validate_steam_path

        parent = self.parent()
        picked = QFileDialog.getExistingDirectory(parent, "Select Steam install folder")
        if not picked:
            return ""
        p = Path(picked)
        if not validate_steam_path(p):
            # Invalid pick. Surface a hint by returning '' so the frontend
            # status line stays untouched. The user can pick again.
            logger.warning("browse_steam_path: %s is not a valid Steam install root", p)
            return ""
        resolved = p.resolve()
        # Update in-memory cache so get_installed_games / get_game_list /
        # everything else that reads self._steam_path uses the new value
        # without needing a process restart. Also drop the games cache
        # so the next list call re-walks the new install.
        self._steam_path = resolved
        try:
            self._installed_games_cache = None
        except Exception:
            pass
        return str(resolved)

    @pyqtSlot(result=str)
    def open_file_dialog(self):
        """Opens native QFileDialog, returns selected path."""
        parent = self.parent()
        path = QFileDialog.getExistingDirectory(parent, "Select Folder")
        return path or ""

    @pyqtSlot(result=str)
    def open_archive_dialog(self):
        """Opens a file picker for ZIP/RAR/7z archives. Returns selected file path."""
        path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Select Archive",
            "",
            "Archives (*.zip *.rar *.7z);;All Files (*)",
        )
        return path or ""

    @pyqtSlot(result=str)
    def open_exe_file_dialog(self):
        """Opens a file picker for executables. Returns selected file path."""
        path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Select Executable",
            "",
            "Executables (*.exe);;All Files (*)",
        )
        return path or ""

    @pyqtSlot(result=str)
    def browse_image_file(self):
        """Opens a native file picker filtered to PNG/JPG/JPEG images. Returns selected path or ''."""
        from PyQt6.QtWidgets import QFileDialog as _QFD
        path, _ = _QFD.getOpenFileName(
            self.parent(),
            "Select Avatar Image",
            "",
            "Image Files (*.png *.jpg *.jpeg)",
        )
        return path or ""

    @pyqtSlot(result=str)
    def browse_custom_background_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Select Background Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.webp)",
        )
        return path or ""

    @pyqtSlot(result=str)
    def export_settings_file(self):
        try:
            from sff.storage.settings import export_settings

            path, _ = QFileDialog.getSaveFileName(
                self.parent(),
                "Export Settings",
                "settings_export.json",
                "JSON Files (*.json);;All Files (*)",
            )
            if not path:
                return json.dumps({"ok": False, "cancelled": True, "message": "Export cancelled"})
            export_path = Path(path)
            if export_path.suffix.lower() != ".json":
                export_path = export_path.with_suffix(".json")
            ok = export_settings(export_path, include_sensitive=False)
            return json.dumps({
                "ok": bool(ok),
                "path": str(export_path),
                "message": f"Settings exported to {export_path}" if ok else "Failed to export settings",
            })
        except Exception as exc:
            logger.warning("export_settings_file failed: %s", exc)
            return json.dumps({"ok": False, "message": str(exc)})

    @pyqtSlot(result=str)
    def import_settings_file(self):
        try:
            from sff.storage.settings import import_settings

            path, _ = QFileDialog.getOpenFileName(
                self.parent(),
                "Import Settings",
                "",
                "JSON Files (*.json);;All Files (*)",
            )
            if not path:
                return json.dumps({"ok": False, "cancelled": True, "message": "Import cancelled"})
            ok, message = import_settings(Path(path))
            return json.dumps({"ok": bool(ok), "path": path, "message": message})
        except Exception as exc:
            logger.warning("import_settings_file failed: %s", exc)
            return json.dumps({"ok": False, "message": str(exc)})

    @pyqtSlot(result=str)
    def import_depot_manifest_html(self):
        try:
            from sff.manifest.html_manifest_import import (
                flatten_manifest_groups,
                format_manifest_entries,
                parse_depot_manifest_html_files,
            )

            paths, _ = QFileDialog.getOpenFileNames(
                self.parent(),
                "Import Depot Manifest HTML",
                "",
                "HTML/Text Files (*.html *.htm *.txt);;All Files (*)",
            )
            if not paths:
                return json.dumps({"ok": False, "cancelled": True, "message": "Import cancelled"})
            groups = parse_depot_manifest_html_files([Path(path) for path in paths])
            entries = flatten_manifest_groups(groups)
            if not entries:
                return json.dumps({"ok": False, "message": "No depot manifest IDs found in those files"})
            line_text = format_manifest_entries(entries)
            return json.dumps({
                "ok": True,
                "paths": paths,
                "groups": groups,
                "entries": entries,
                "line_text": line_text,
                "message": f"Imported {len(entries)} depot manifest ID(s)",
            })
        except Exception as exc:
            logger.warning("import_depot_manifest_html failed: %s", exc)
            return json.dumps({"ok": False, "message": str(exc)})

    @pyqtSlot(str, result=str)
    def set_custom_background(self, source_path):
        try:
            from sff.storage.settings import set_setting
            from sff.structs import Settings
            from sff.utils import sff_data_dir

            src = Path(source_path)
            if not src.is_file():
                return json.dumps({"ok": False, "error": "File not found"})
            ext = src.suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                return json.dumps({"ok": False, "error": "Use PNG, JPG, JPEG, or WebP"})
            if src.stat().st_size > 10 * 1024 * 1024:
                return json.dumps({"ok": False, "error": "Image must be 10 MB or smaller"})
            target_dir = sff_data_dir() / "webui_custom"
            target_dir.mkdir(parents=True, exist_ok=True)
            for old in target_dir.glob("background.*"):
                try:
                    old.unlink()
                except OSError:
                    pass
            dst = target_dir / f"background{ext}"
            shutil.copy2(src, dst)
            set_setting(Settings.CUSTOM_BACKGROUND_IMAGE, str(dst))
            return json.dumps({"ok": True, "path": str(dst), "url": dst.resolve().as_uri()})
        except Exception as exc:
            logger.warning("set_custom_background failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(result=str)
    def clear_custom_background(self):
        try:
            from sff.storage.settings import clear_setting
            from sff.structs import Settings
            from sff.utils import sff_data_dir

            clear_setting(Settings.CUSTOM_BACKGROUND_IMAGE)
            target_dir = sff_data_dir() / "webui_custom"
            if target_dir.exists():
                for old in target_dir.glob("background.*"):
                    try:
                        old.unlink()
                    except OSError:
                        pass
            return json.dumps({"ok": True})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(result=str)
    def open_lua_file_dialog(self):
        """Opens a file picker for Lua files. Returns selected file path."""
        path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Select Lua File",
            "",
            "Lua/Archive Files (*.lua *.zip *.rar *.7z);;All Files (*)",
        )
        return path or ""

    @pyqtSlot(result=str)
    def open_manifest_folder_dialog(self):
        """Opens a folder picker for selecting a directory containing .manifest files."""
        path = QFileDialog.getExistingDirectory(
            self.parent(),
            "Select Manifest Folder",
            "",
        )
        return path or ""

    # ── A12 Bulk Import bridge slots ─────────────────────────────
    #
    # Folder Scan, Drag-and-Drop, and Batch Queue all funnel into the
    # same singleton BulkImportQueue so per-file dedupe works across the
    # three surfaces. Single-file imports never touch this code path.

    def _get_bulk_import_queue(self):
        """Return a singleton BulkImportQueue, creating it on first use."""
        from sff.gui.bulk_import import BulkImportQueue

        existing = getattr(self, "_bulk_import_queue", None)
        if existing is not None:
            return existing
        queue = BulkImportQueue(
            ui=self._ui,
            steam_path=self._steam_path,
            active_library=self._active_library,
            progress_cb=self._emit_bulk_progress,
        )
        self._bulk_import_queue = queue
        return queue

    def _reset_bulk_import_queue(self):
        self._bulk_import_queue = None

    def _emit_bulk_progress(self, payload):
        try:
            self.download_progress.emit(json.dumps(payload))
        except Exception as exc:
            logger.debug("bulk download_progress emit failed: %s", exc)

    @pyqtSlot()
    def open_folder_scan(self):
        """Open a native dir picker, walk recursively, validate `.lua`/
        `.manifest` candidates, and enqueue the valid ones into the
        singleton BulkImportQueue. Auto-starts the drain when
        BULK_IMPORT_MODE is `process_immediately`.
        """
        parent = self.parent()
        folder = QFileDialog.getExistingDirectory(parent, "Select Folder")
        if not folder:
            return

        def _do():
            from sff.gui.bulk_import import BulkImportQueue

            queue = self._get_bulk_import_queue()
            files = BulkImportQueue.collect_from_folder(Path(folder))
            queue.enqueue_files(files)
            self._maybe_drain_queue(queue)
            return queue.summary()

        def _on_done(summary):
            self._emit_bulk_summary("folder_scan", summary)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def enqueue_dropped_files(self, files_json):
        """Accept a JSON list of file paths from the JS Drop Zone or
        Quick Start drop, validate each against the existing single-file
        parsers, dedupe, and enqueue the valid ones.
        """
        try:
            paths = json.loads(files_json or "[]")
        except Exception as exc:
            logger.warning("enqueue_dropped_files: bad JSON: %s", exc)
            return

        def _do():
            queue = self._get_bulk_import_queue()
            queue.enqueue_files(Path(p) for p in paths if p)
            self._maybe_drain_queue(queue)
            return queue.summary()

        def _on_done(summary):
            self._emit_bulk_summary("drop", summary)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def enqueue_dropped_blobs(self, blobs_json):
        """Accept a JSON list of dropped file payloads from the JS Drop
        Zone, write each blob to a per-session temp folder, and enqueue
        those temp paths through the standard bulk-import pipeline.

        QtWebEngine's Chromium 124+ no longer exposes `file.path` on
        drag-and-drop, so the JS side cannot read the user's actual
        filesystem path. Instead it reads file CONTENT via
        `file.arrayBuffer()`, base64-encodes it, and passes
        ``[{name, content_b64}]`` here. We materialize each entry to
        ``<sff_data>/.bulk_import_drop/<safe-name>`` and feed those
        paths into BulkImportQueue. Validation, dedupe, and the rest
        of the pipeline are unchanged from the folder-scan path.
        """
        try:
            blobs = json.loads(blobs_json or "[]")
        except Exception as exc:
            logger.warning("enqueue_dropped_blobs: bad JSON: %s", exc)
            return
        if not isinstance(blobs, list) or not blobs:
            return

        def _do():
            import base64 as _b64
            from sff.utils import sff_data_dir

            staging = sff_data_dir() / ".bulk_import_drop"
            staging.mkdir(parents=True, exist_ok=True)
            paths: list[Path] = []

            for blob in blobs:
                if not isinstance(blob, dict):
                    continue
                name = str(blob.get("name", "")).strip()
                content_b64 = blob.get("content_b64", "")
                if not name or not content_b64:
                    continue
                # Reject anything that doesn't end in .lua / archive / .manifest;
                # bulk_import already does this, but we save the I/O round trip.
                lower = name.lower()
                if not (lower.endswith(".lua") or lower.endswith(".zip") or lower.endswith(".rar") or lower.endswith(".7z") or lower.endswith(".manifest")):
                    continue
                safe = _UNSAFE_FILENAME_RE.sub("_", name)
                target = staging / safe
                # Avoid overwriting a sibling drop with the same name in the
                # same session; suffix by appending a counter.
                counter = 0
                base_target = target
                while target.exists():
                    counter += 1
                    target = base_target.with_name(f"{base_target.stem}__{counter}{base_target.suffix}")
                try:
                    raw = _b64.b64decode(content_b64, validate=False)
                    target.write_bytes(raw)
                except Exception as exc:
                    logger.warning(
                        "enqueue_dropped_blobs: write failed for %r: %s", name, exc
                    )
                    continue
                paths.append(target)

            if not paths:
                return None
            queue = self._get_bulk_import_queue()
            queue.enqueue_files(iter(paths))
            self._maybe_drain_queue(queue)
            return queue.summary()

        def _on_done(summary):
            self._emit_bulk_summary("drop", summary)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def run_bulk_import(self):
        """Start the queue drain. Used by the `collect_then_confirm` mode
        where files are queued first and the user clicks a Run button to
        kick off processing.
        """
        def _do():
            queue = self._get_bulk_import_queue()
            return queue.drain()

        def _on_done(summary):
            self._emit_bulk_summary("run", summary)
            self._reset_bulk_import_queue()

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def cancel_bulk_import(self):
        """Raise the cancel signal on the in-flight queue. The current
        file finishes its pipeline cleanly; no new files are dequeued.
        """
        queue = getattr(self, "_bulk_import_queue", None)
        if queue is not None:
            queue.cancel()
        self._emit_task_result("bulk_import", False, "Bulk import cancelled")

    def _maybe_drain_queue(self, queue):
        """Honor BULK_IMPORT_MODE: drain immediately when set to
        `process_immediately` (the default), or wait for an explicit
        `run_bulk_import` call when set to `collect_then_confirm`.
        """
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings as _Settings

            mode = get_setting(_Settings.BULK_IMPORT_MODE) or "process_immediately"
        except Exception:
            mode = "process_immediately"
        if str(mode) == "process_immediately":
            queue.drain()

    def _emit_bulk_summary(self, source, summary):
        if summary is None:
            return
        try:
            payload = {
                "task": "bulk_import",
                "success": summary.failed == 0 and summary.skipped == 0,
                "source": source,
                "total": summary.total,
                "succeeded": summary.succeeded,
                "failed": summary.failed,
                "skipped": summary.skipped,
                "results": [
                    {
                        "path": str(r.path),
                        "app_id": r.app_id or "",
                        "ok": bool(r.ok),
                        "skipped": bool(r.skipped),
                        "reason": r.reason or "",
                        "failing_step": r.failing_step or "",
                    }
                    for r in summary.results
                ],
            }
            self.task_finished.emit(json.dumps(payload))
        except Exception as exc:
            logger.debug("bulk summary emit failed: %s", exc)

    @pyqtSlot(result=str)
    def get_recent_lua_files(self):
        """Returns JSON array of recent Lua files [{name, path}, ...] from RecentFilesManager."""
        try:
            from sff.recent_files import get_recent_files_manager
            mgr = get_recent_files_manager()
            files = mgr.get_all()
            return json.dumps([{"name": p.name, "path": str(p)} for p in files])
        except Exception as e:
            logger.warning("get_recent_lua_files failed: %s", e)
            return "[]"

    @pyqtSlot(str, str, str, str, str)
    def download_game_ddmod(self, app_id, source, lua_path, manifest_folder='', target_os='', branch='', file_type=''):
        """Download a game using DepotDownloaderMod.
        source: 'hubcap' | 'oureveryday' | 'ryuu' | 'local'
        lua_path: used when source == 'local'
        Emits download_progress + task_finished signals."""
        if not app_id or not app_id.strip().isdigit():
            self._emit_task_result("download_ddmod", False, f"Invalid App ID: '{app_id}'")
            return
        def _do():
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Starting DDMod download", "progress": 0
            }))
            try:
                from pathlib import Path as _Path
                from sff.lua.endpoints import get_hubcap, get_oureverday, get_ryuu
                from sff.lua.manager import parse_lua_contents
                from sff.depot_downloader import run_download, filter_depots_by_os

                steam_path = self._steam_path
                dest = _Path(self._active_library) if self._active_library else steam_path
                if dest is None:
                    return (False, "No Steam library selected. Please select a download location.")
                # Resolve the library where the game's ACF lives (or will live)
                # so downloads land on the correct SSD when the game already
                # has an .acf in a non-default library.
                try:
                    from sff.storage.vdf import get_steam_libs
                    libs = get_steam_libs(steam_path) if steam_path else []
                    for lib in libs:
                        acf = lib / "steamapps" / f"appmanifest_{app_id}.acf"
                        if acf.is_file():
                            dest = lib
                            break
                except Exception:
                    pass

                # Download the source lua into per-user saved_lua/, not
                # <steam>/config/. The final copy step below moves the
                # parsed lua into <steam>/config/stplug-in/. Writing to
                # <steam>/config/ directly left a stray
                # <steam>/config/<app_id>.lua that Remove from Library
                # never cleaned up.
                lua_dest = Path.cwd() / "saved_lua"
                try:
                    lua_dest.mkdir(parents=True, exist_ok=True)
                except Exception:
                    lua_dest = _Path(".")

                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Fetching Lua file...", "progress": 5
                }))

                if source == "local":
                    lua_file = _Path(lua_path) if lua_path else None
                    if not lua_file or not lua_file.exists():
                        return (False, f"Lua file not found: {lua_path}")
                elif source == "hubcap":
                    lua_file = get_hubcap(lua_dest, app_id, depotcache=(steam_path / "depotcache") if steam_path else None)
                elif source == "oureveryday":
                    lua_file = get_oureverday(lua_dest, app_id)
                elif source == "ryuu":
                    lua_file = get_ryuu(lua_dest, app_id, request_update=False, branch=branch, file_type=file_type, depotcache=(steam_path / "depotcache") if steam_path else None)
                else:
                    return (False, f"Unknown source: {source}")

                if not lua_file or not lua_file.exists():
                    return (False, f"Failed to obtain Lua file from source '{source}'")

                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Parsing Lua...", "progress": 15
                }))

                lua_install_file = lua_file
                # Archives: extract lua text and seed depotcache with any embedded manifests
                if lua_file.suffix.lower() in ('.zip', '.rar', '.7z'):
                    from sff.zip import read_lua_from_zip
                    _dc = (steam_path / "depotcache") if steam_path else None
                    lua_text = read_lua_from_zip(lua_file, decode=True, depotcache=_dc)
                    if not lua_text:
                        return (False, "Could not find .lua file inside archive")
                    lua_install_file = lua_dest / f"{app_id}.lua"
                    lua_install_file.write_text(lua_text, encoding="utf-8")
                else:
                    lua_text = lua_file.read_text(encoding="utf-8", errors="replace")
                parsed = parse_lua_contents(lua_text, lua_file)
                if not parsed or not parsed.depots:
                    return (False, "Failed to parse Lua — no depot info found")
                _auto_update_was_registered = self._auto_update_was_registered(app_id)

                # ── Steam registration (LumaCore on Windows / SLSSteam on Linux) ──
                # Without these the library card shows "Buy" because Steam never
                # learns about the install. Mirror _run_windows_fastest on win32
                # and process_from_store on linux. LumaCore is Windows-only so
                # the stplug-in copy never runs on Linux (requirement 2.33).
                if sys.platform == "win32":
                    # Calls install_lua_to_steam, ConfigVDFWriter.add_decryption_keys_to_config,
                    # set_stats_and_achievements, app_list_man.add_ids,
                    # ACFWriter.write_acf(parsed), ACFWriter.patch_workshop_acf(parsed),
                    # ensure_library_has_app(steam_path, dest, app_id).
                    try:
                        from sff.steam_tools_compat import install_lua_to_steam
                        install_lua_to_steam(steam_path, app_id, lua_install_file)
                        self._apply_auto_update_default(app_id, _auto_update_was_registered)
                    except Exception as _ile:
                        logger.warning("install_lua_to_steam failed (non-fatal): %s", _ile)

                    try:
                        from sff.lua.writer import ConfigVDFWriter
                        ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)
                    except Exception as _kwe:
                        logger.warning("add_decryption_keys_to_config failed (non-fatal): %s", _kwe)

                    try:
                        from sff.registry_access import set_stats_and_achievements
                        set_stats_and_achievements(app_id)
                    except Exception as _se:
                        logger.warning("set_stats_and_achievements failed (non-fatal): %s", _se)

                    try:
                        if hasattr(self._ui, 'app_list_man') and self._ui.app_list_man:
                            self._ui.app_list_man.add_ids(parsed)
                    except Exception as _aie:
                        logger.warning("app_list_man.add_ids failed (non-fatal): %s", _aie)

                    try:
                        from sff.lua.writer import ACFWriter
                        _acf = ACFWriter(dest)
                        _acf.write_acf(parsed)
                        if hasattr(_acf, 'patch_workshop_acf'):
                            _acf.patch_workshop_acf(parsed)
                    except Exception as _we:
                        logger.warning("ACFWriter.write_acf / patch_workshop_acf failed (non-fatal): %s", _we)

                    try:
                        from sff.storage.vdf import ensure_library_has_app
                        ensure_library_has_app(steam_path, dest, app_id)
                    except Exception as _le:
                        logger.warning("ensure_library_has_app failed (non-fatal): %s", _le)

                elif sys.platform == "linux":
                    # SLSSteam consumes ~/.config/SLSsteam/config.yaml.
                    # Calls sls_man.add_ids(parsed), ACFWriter.write_acf(parsed),
                    # ACFWriter.patch_workshop_acf(parsed),
                    # ensure_library_has_app(steam_path, dest, app_id).
                    # No stplug-in drop on Linux (LumaCore is Windows-only).
                    try:
                        if hasattr(self._ui, 'sls_man') and self._ui.sls_man:
                            self._ui.sls_man.add_ids(parsed)
                    except Exception as _sle:
                        logger.warning("sls_man.add_ids failed (non-fatal): %s", _sle)

                    try:
                        from sff.lua.writer import ACFWriter
                        _acf = ACFWriter(dest)
                        _acf.write_acf(parsed)
                        if hasattr(_acf, 'patch_workshop_acf'):
                            _acf.patch_workshop_acf(parsed)
                    except Exception as _we:
                        logger.warning("ACFWriter.write_acf / patch_workshop_acf failed (non-fatal): %s", _we)

                    try:
                        from sff.storage.vdf import ensure_library_has_app
                        ensure_library_has_app(steam_path, dest, app_id)
                    except Exception as _le:
                        logger.warning("ensure_library_has_app failed (non-fatal): %s", _le)

                if source == "local":
                    if manifest_folder:
                        import shutil as _shutil
                        from sff.utils import manifests_staging_dir
                        _staging = manifests_staging_dir()
                        _depotcache = steam_path / "depotcache"
                        _depotcache.mkdir(parents=True, exist_ok=True)
                        for _mf in _Path(manifest_folder).glob("*.manifest"):
                            _staging.mkdir(parents=True, exist_ok=True)
                            _shutil.copy2(_mf, _staging / _mf.name)
                            _shutil.copy2(_mf, _depotcache / _mf.name)
                    return (True, "Local Lua/manifests imported without Hubcap/Ryuu/OurEveryday or DDMod")

                # Confirm registration before the depot fetch fires.
                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Registered with Steam", "progress": 22
                }))

                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Resolving manifests...", "progress": 25
                }))

                # Build game_data for run_download
                depots_dict = {}
                manifests_dict = {}
                for d in parsed.depots:
                    if d.decryption_key:
                        depots_dict[str(d.depot_id)] = {"key": d.decryption_key}

                _depot_ids_set = set(depots_dict.keys())

                # Step 1: scan ./manifests/ staging for pre-extracted manifest files
                _staging = _Path.cwd() / "manifests"
                if _staging.exists():
                    for _mf in _staging.glob("*.manifest"):
                        _parts = _mf.stem.split("_", 1)
                        if len(_parts) == 2 and _parts[0] in _depot_ids_set:
                            if _parts[0] not in manifests_dict:
                                manifests_dict[_parts[0]] = _parts[1]

                # Step 2: scan user-provided manifest folder
                if manifest_folder:
                    import shutil as _shutil
                    _mf_path = _Path(manifest_folder)
                    if _mf_path.exists():
                        _staging.mkdir(exist_ok=True)
                        for _mf in _mf_path.glob("*.manifest"):
                            _parts = _mf.stem.split("_", 1)
                            if len(_parts) == 2 and _parts[0] in _depot_ids_set:
                                manifests_dict[_parts[0]] = _parts[1]
                                _shutil.copy2(_mf, _staging / _mf.name)

                # Step 3: try Steam App Info for manifest IDs + game_name/installdir/buildid (non-fatal)
                game_name = ""
                installdir = ""
                buildid = "0"
                _provider = None
                _app_info = None
                if steam_path and depots_dict:
                    try:
                        from sff.steam_client import create_provider_for_current_thread
                        from sff.manifest.downloader import ManifestDownloader
                        _provider = create_provider_for_current_thread()
                        _md = ManifestDownloader(provider=_provider, steam_path=steam_path)
                        _manifest_map = _md.get_manifest_ids(parsed, auto=True)
                        for _depot_id, _manifest_id in _manifest_map.items():
                            if _manifest_id and str(_depot_id) not in manifests_dict:
                                manifests_dict[str(_depot_id)] = str(_manifest_id)
                        # Also pull game_name, installdir, buildid from App Info
                        _eff_id = int(parsed.app_id or app_id)
                        _app_info = _provider.get_single_app_info(_eff_id)
                        if _app_info:
                            game_name = _app_info.get("common", {}).get("name", "")
                            installdir = _app_info.get("config", {}).get("installdir", "")
                            try:
                                buildid = str(
                                    _app_info.get("depots", {})
                                    .get("branches", {})
                                    .get("public", {})
                                    .get("buildid", "0")
                                )
                            except Exception:
                                buildid = "0"
                    except Exception as _me:
                        logger.debug("Manifest auto-resolve (Steam provider) failed: %s", _me)

                # Fallback: parse game name from first short Lua comment line
                if not game_name:
                    for _cl in lua_text.splitlines():
                        _cl = _cl.strip()
                        if _cl.startswith("--"):
                            _cand = re.sub(r'^--\s*', '', _cl).strip()
                            if _cand and ':' not in _cand and "'" not in _cand and 'http' not in _cand and 2 < len(_cand) < 60 and not _cand[0].isdigit():
                                game_name = _cand
                                break
                if not installdir:
                    installdir = game_name or f"App_{parsed.app_id or app_id}"

                # Pin info: tell the user if the Lua has setManifestid pins
                if source in ("hubcap", "ryuu"):
                    _pin_map = getattr(parsed, "manifest_overrides", {}) or {}
                    if _pin_map:
                        from sff.storage.settings import get_setting as _gs
                        from sff.structs import Settings as _S
                        if not _gs(_S.MANIFEST_PINS_ASKED):
                            print(
                                f"[!] {len(_pin_map)} pinned manifest version(s) found in this Lua."
                                " To use them, enable 'Use Pinned Manifest Versions from Lua' in Settings."
                            )

                # Step 4: gmrc -> ManifestHub -> GitHub for known manifest IDs
                if manifests_dict and steam_path:
                    try:
                        import shutil as _step4_shutil
                        from sff.manifest.downloader import ManifestDownloader
                        _md2 = ManifestDownloader(provider=_provider, steam_path=steam_path, use_hubcap=False)
                        _staging.mkdir(exist_ok=True)
                        _dc2 = steam_path / "depotcache"
                        _dc2.mkdir(parents=True, exist_ok=True)
                        _eff_app_id = str(parsed.app_id or app_id)
                        _cdn2 = None
                        if _provider:
                            try:
                                _cdn2 = _md2.get_cdn_client()
                            except Exception as _ce:
                                logger.debug("CDN client init failed (non-fatal): %s", _ce)
                        for _depot_id, _manifest_id in list(manifests_dict.items()):
                            _dc_mf = _dc2 / f"{_depot_id}_{_manifest_id}.manifest"
                            _dest_mf = _staging / f"{_depot_id}_{_manifest_id}.manifest"
                            if _dc_mf.exists():
                                if not _dest_mf.exists():
                                    _step4_shutil.copy2(_dc_mf, _dest_mf)
                                continue
                            if _dest_mf.exists():
                                _dc2.mkdir(parents=True, exist_ok=True)
                                _step4_shutil.copy2(_dest_mf, _dc_mf)
                                continue
                            print(f"Fetching manifest for depot {_depot_id} ({_manifest_id})...")
                            if _cdn2:
                                _data = _md2.download_single_manifest(_depot_id, _manifest_id, cdn_client=_cdn2, app_id=_eff_app_id)
                            else:
                                _data = _md2._try_manifesthub_combined(_depot_id, _manifest_id, _eff_app_id)
                            if _data:
                                _written = _md2._write_manifest_to_depotcache(_data, _depot_id, _manifest_id)
                                if _written and not _dest_mf.exists():
                                    _step4_shutil.copy2(_written, _dest_mf)
                            else:
                                logger.debug("All sources failed for manifest depot %s", _depot_id)
                    except Exception as _fe:
                        logger.debug("Manifest fetch failed (non-fatal): %s", _fe)

                game_data = {
                    "appid": parsed.app_id or app_id,
                    "game_name": game_name,
                    "depots": depots_dict,
                    "manifests": manifests_dict,
                    "installdir": installdir,
                    "buildid": buildid,
                }

                selected_depots = list(depots_dict.keys())
                if not selected_depots:
                    return (False, "No depots with decryption keys found in Lua")

                # If no manifests resolved for any selected depot, DDMod will
                # fall back to anonymous CDN fetch and 401. Give the user a
                # specific error instead of the generic "DepotDownloaderMod
                # reported failure" line.
                _depots_without_manifest = [
                    d for d in selected_depots if str(d) not in manifests_dict
                ]
                if len(_depots_without_manifest) == len(selected_depots):
                    return (
                        False,
                        "No manifest IDs available for any depot. "
                        "Drop a folder of .manifest files into the modal, "
                        "pick a manifest source (Hubcap/Ryuu/oureveryday), "
                        "or run Update All Games first.",
                    )

                self.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Running DepotDownloaderMod...", "progress": 35
                }))

                _last_emit = [0.0]
                _PASS_PREFIXES = (
                    "---", "[OK]", "[FAIL]",
                    "Depot ", "Total ", "Error", "Skipping",
                    "WARNING", "Network error", "[Pre-allocation", "[!",
                )

                # DDMod prints lines like "  12.34% Downloaded ..." through
                # the depot loop. Scrape those out and forward as a real
                # progress update to the JS download tracker so the bar
                # actually moves instead of sticking at 35% the whole
                # time. DDMod's own throttled output already caps at
                # ~5 lines/sec via depot_downloader's reader.
                # Map DDMod's 0-100 onto the 35-95 slice the UI uses
                # for "running download" so we don't snap back to 35
                # mid-flight or pre-empt the 95% "Updating tracker" stage.
                _DDMOD_FLOOR = 35.0
                _DDMOD_CEIL = 95.0
                _last_pct = [-1.0]

                def _print_fn(msg):
                    import time as _t
                    clean = _ANSI_RE.sub('', msg).strip()
                    if not clean:
                        return
                    now = _t.monotonic()

                    pct_match = _DDMOD_PCT_RE.match(clean)
                    if pct_match:
                        try:
                            raw = float(pct_match.group(1))
                        except ValueError:
                            raw = -1.0
                        if 0.0 <= raw <= 100.0:
                            mapped = _DDMOD_FLOOR + (raw / 100.0) * (_DDMOD_CEIL - _DDMOD_FLOOR)
                            mapped_int = int(mapped)
                            if mapped_int != int(_last_pct[0]):
                                _last_pct[0] = mapped
                                try:
                                    self.download_progress.emit(json.dumps({
                                        "app_id": app_id,
                                        "status": f"Downloading depot files... {raw:.1f}%",
                                        "progress": mapped_int,
                                    }))
                                except Exception:
                                    pass

                    if not clean.startswith(_PASS_PREFIXES) and now - _last_emit[0] < 0.2:
                        return
                    _last_emit[0] = now
                    print(clean)

                _target_os = (target_os or "").strip().lower()
                if _target_os not in ("windows", "linux", "macos", "all"):
                    _target_os = "linux" if sys.platform.startswith("linux") else "windows"
                selected_depots = filter_depots_by_os(selected_depots, _app_info, print_fn=_print_fn, os_name=_target_os)
                for _sk in [k for k in list(depots_dict.keys()) if k not in selected_depots]:
                    del depots_dict[_sk]

                ok, _size = run_download(game_data, selected_depots, dest, steam_path, print_fn=_print_fn, os_name=_target_os)

                # Write ACF so Steam recognises the install
                try:
                    from sff.linux.acf_writer import create_acf
                    create_acf(
                        game_data=game_data,
                        dest_path=dest,
                        selected_depots=selected_depots,
                        size_on_disk=_size,
                        print_fn=_print_fn,
                    )
                except Exception as _ae:
                    logger.warning("ACF write failed (non-fatal): %s", _ae)

                # Add to recent files
                try:
                    from sff.recent_files import get_recent_files_manager
                    get_recent_files_manager().add(lua_file)
                except Exception:
                    pass

                if ok and _size > 0:
                    return (True, "Download complete")
                if ok and _size <= 0:
                    return (
                        False,
                        "DepotDownloaderMod exited without errors but wrote 0 bytes. "
                        "Manifest setup may be ready, but the game files were not downloaded.",
                    )
                # Build a more specific failure message: did EVERY depot exit
                # non-zero, or just some? Did the install dir end up empty?
                _failed_dir = (
                    dest / "steamapps" / "common" / installdir
                    if installdir else None
                )
                if _failed_dir and not any(_failed_dir.glob("*")):
                    return (
                        False,
                        "DepotDownloaderMod failed for every depot. "
                        "Common causes: anonymous CDN fetch fell through "
                        "(missing manifest pin), Steam blocked the depot, "
                        "or .NET 9 runtime failed to spawn. Check the "
                        "console output above for the per-depot exit code.",
                    )
                return (
                    False,
                    "DepotDownloaderMod completed with errors. "
                    "Some depots downloaded; check the console output for "
                    "which depots exited non-zero before retrying.",
                )

            except Exception as e:
                logger.exception("download_game_ddmod failed: %s", e)
                return (False, str(e))

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg = result
            else:
                ok, msg = False, "Download failed"
            if ok and source in ("hubcap", "ryuu"):
                QTimer.singleShot(1000, self._maybe_auto_contribute_provider)
            self._emit_task_result("download_ddmod", ok, msg, app_id=app_id)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, str, str)
    def import_local_lua(self, app_id, lua_path, manifest_folder=''):
        """Register a local Lua/archive without provider APIs or DDMod."""
        if not app_id or not app_id.strip().isdigit():
            self._emit_task_result("import_local_lua", False, f"Invalid App ID: '{app_id}'", app_id=app_id)
            return

        def _do():
            try:
                from pathlib import Path as _Path
                from sff.lua.manager import parse_lua_contents
                from sff.steam_tools_compat import install_lua_to_steam
                from sff.lua.writer import ACFWriter, ConfigVDFWriter
                from sff.storage.vdf import ensure_library_has_app

                steam_path = self._steam_path
                dest = _Path(self._active_library) if self._active_library else steam_path
                lua_file = _Path(lua_path) if lua_path else None
                if not steam_path or not dest:
                    return (False, "No Steam path/library selected.")
                if not lua_file or not lua_file.exists():
                    return (False, f"Lua file not found: {lua_path}")

                lua_install_file = lua_file
                if lua_file.suffix.lower() in (".zip", ".rar", ".7z"):
                    from sff.zip import read_lua_from_zip
                    lua_text = read_lua_from_zip(lua_file, decode=True, depotcache=steam_path / "depotcache")
                    if not lua_text:
                        return (False, "Could not find .lua file inside archive")
                    saved_dir = _Path.cwd() / "saved_lua"
                    saved_dir.mkdir(parents=True, exist_ok=True)
                    lua_install_file = saved_dir / f"{app_id}.lua"
                    lua_install_file.write_text(lua_text, encoding="utf-8")
                else:
                    lua_text = lua_file.read_text(encoding="utf-8", errors="replace")
                parsed = parse_lua_contents(lua_text, lua_file)
                if not parsed:
                    return (False, "Failed to parse Lua")
                _auto_update_was_registered = self._auto_update_was_registered(app_id)

                if manifest_folder:
                    import shutil as _shutil
                    from sff.utils import manifests_staging_dir
                    staging = manifests_staging_dir()
                    depotcache = steam_path / "depotcache"
                    depotcache.mkdir(parents=True, exist_ok=True)
                    for mf in _Path(manifest_folder).glob("*.manifest"):
                        _shutil.copy2(mf, staging / mf.name)
                        _shutil.copy2(mf, depotcache / mf.name)

                install_lua_to_steam(steam_path, app_id, lua_install_file)
                self._apply_auto_update_default(app_id, _auto_update_was_registered)
                ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)
                try:
                    from sff.registry_access import set_stats_and_achievements
                    set_stats_and_achievements(app_id)
                except Exception as exc:
                    logger.debug("import_local_lua stats setup skipped: %s", exc)
                if hasattr(self._ui, "app_list_man") and self._ui.app_list_man:
                    self._ui.app_list_man.add_ids(parsed)
                acf = ACFWriter(dest)
                acf.write_acf(parsed)
                if hasattr(acf, "patch_workshop_acf"):
                    acf.patch_workshop_acf(parsed)
                ensure_library_has_app(steam_path, dest, app_id)
                return (True, "Local Lua imported without API/DDMod")
            except Exception as exc:
                logger.exception("import_local_lua failed: %s", exc)
                return (False, str(exc))

        def _on_done(result):
            ok, msg = result if isinstance(result, tuple) else (False, "Import failed")
            self._emit_task_result("import_local_lua", ok, msg, app_id=app_id)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(result=str)
    def get_games_file_info(self):
        """Return all_games.txt status as JSON {exists, mtime_str, count}."""
        from sff.utils import root_folder
        from datetime import datetime
        all_games_file = root_folder(outside_internal=True) / "all_games.txt"
        if not all_games_file.exists():
            return json.dumps({"exists": False, "mtime_str": "", "count": 0})
        try:
            mtime = all_games_file.stat().st_mtime
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %I:%M %p")
            count = sum(1 for _ in all_games_file.open(encoding="utf-8", errors="ignore"))
            return json.dumps({"exists": True, "mtime_str": mtime_str, "count": count})
        except Exception as e:
            logger.debug("get_games_file_info failed: %s", e)
            return json.dumps({"exists": True, "mtime_str": "", "count": 0})

    @pyqtSlot()
    def update_games_file(self):
        """Download full Steam app list and write all_games.txt. Emits task_finished('update_games_file')."""
        def _do():
            try:
                from sff.utils import root_folder
                from sff.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
                from sff.storage.settings import get_setting
                from sff.structs import Settings
                import urllib.request as _req
                import json as _json
                all_games_file = root_folder(outside_internal=True) / "all_games.txt"
                api_key = get_setting(Settings.STEAM_WEB_API_KEY)
                if not isinstance(api_key, str) or not api_key.strip():
                    api_key = _DEFAULT_KEY
                params = {"key": api_key, "max_results": "50000", "include_games": "1",
                          "include_dlc": "0", "include_software": _should_show_software(),
                          "include_videos": "0", "include_hardware": "0"}
                games = []
                base_url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
                page = 0
                while True:
                    page += 1
                    print(f"Downloading game list page {page} ({len(games)} games so far)...")
                    query_str = "&".join(f"{k}={v}" for k, v in params.items())
                    url = f"{base_url}?{query_str}"
                    req = _req.Request(url, headers={"User-Agent": "SteaMidra/6.1.0"})
                    with _req.urlopen(req, timeout=30, context=_get_ssl_ctx()) as resp:
                        data = _json.loads(resp.read())
                    apps = data.get("response", {}).get("apps", [])
                    games.extend(apps)
                    more = data.get("response", {}).get("have_more_results")
                    if not more:
                        break
                    last_id = data.get("response", {}).get("last_appid")
                    if last_id:
                        params["last_appid"] = str(last_id)
                    else:
                        break
                print(f"Writing {len(games)} games to all_games.txt...")
                games_str = [
                    x.get("name", "UNKNOWN GAME") + f" [ID={x.get('appid')}]"
                    for x in games
                    if x.get("appid") and x.get("name", "").strip()
                ]
                all_games_file.parent.mkdir(parents=True, exist_ok=True)
                with all_games_file.open("w", encoding="utf-8") as f:
                    f.write("\n".join(games_str))
                print(f"Game list updated: {len(games_str)} games written.")
                return len(games_str)
            except Exception as e:
                logger.exception("update_games_file failed: %s", e)
                return (False, str(e))

        def _on_done(result):
            if isinstance(result, int):
                self._emit_task_result("update_games_file", True, f"Game list updated: {result} games")
            elif isinstance(result, tuple) and not result[0]:
                self._emit_task_result("update_games_file", False, f"Failed: {result[1]}")
            else:
                self._emit_task_result("update_games_file", False, "Failed to update game list")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def update_store_lists(self):
        """Download all store data sources: all_games.txt + games.json + name cache.
        Emits task_finished('store_metadata_refresh')."""
        def _do():
            from sff.game_list_fallback import ensure_loaded as _fallback_loaded
            from sff.utils import root_folder
            from sff.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            import urllib.request as _req
            import json as _json
            ok_steam = False
            ok_json = False
            results = []
            # 1) Download all_games.txt via IStoreService API
            try:
                all_games_file = root_folder(outside_internal=True) / "all_games.txt"
                api_key = get_setting(Settings.STEAM_WEB_API_KEY)
                if not isinstance(api_key, str) or not api_key.strip():
                    api_key = _DEFAULT_KEY
                params = {"key": api_key, "max_results": "50000", "include_games": "1",
                          "include_dlc": "0", "include_software": _should_show_software(),
                          "include_videos": "0", "include_hardware": "0"}
                games = []
                base_url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
                while True:
                    query_str = "&".join(f"{k}={v}" for k, v in params.items())
                    url = f"{base_url}?{query_str}"
                    req = _req.Request(url, headers={"User-Agent": "SteaMidra/6.1.0"})
                    with _req.urlopen(req, timeout=30, context=_get_ssl_ctx()) as resp:
                        data = _json.loads(resp.read())
                    apps = data.get("response", {}).get("apps", [])
                    games.extend(apps)
                    if not data.get("response", {}).get("have_more_results"):
                        break
                    last_id = data.get("response", {}).get("last_appid")
                    if last_id:
                        params["last_appid"] = str(last_id)
                    else:
                        break
                games_str = [
                    x.get("name", "UNKNOWN GAME") + f" [ID={x.get('appid')}]"
                    for x in games if x.get("appid") and x.get("name", "").strip()
                ]
                all_games_file.parent.mkdir(parents=True, exist_ok=True)
                with all_games_file.open("w", encoding="utf-8") as f:
                    f.write("\n".join(games_str))
                ok_steam = True
                results.append(f"all_games.txt: {len(games_str)} games")
                logger.debug("Store list update: all_games.txt written (%d games)", len(games_str))
            except Exception as e:
                logger.warning("Store list update: all_games.txt failed: %s", e)
                results.append(f"all_games.txt failed: {e}")
            # 2) Force-refresh games.json + name cache (games_appid.json, software_appid.json)
            try:
                _fallback_loaded(force=True)
                from sff.game_list_fallback import metadata_counts
                counts = metadata_counts()
                games_count = counts.get("games", 0)
                names_count = counts.get("names", 0)
                dlc_count = counts.get("dlc_names", 0)
                ok_json = bool(games_count or names_count or dlc_count)
                results.append(
                    f"games.json: {games_count} entries, app/software names: {names_count}, DLC names: {dlc_count}"
                )
                logger.debug(
                    "Store list update: JSON sources refreshed (%d games, %d names, %d DLC names)",
                    games_count, names_count, dlc_count,
                )
            except Exception as e:
                logger.warning("Store list update: JSON sources failed: %s", e)
                results.append(f"JSON sources failed: {e}")
            # Also invalidate the Steam applist in-memory cache so next search re-reads
            global _STEAM_APPLIST_CACHE
            _STEAM_APPLIST_CACHE = None
            _STEAM_APPLIST_CACHE_TIME = 0
            return (ok_steam or ok_json, "; ".join(results))

        def _on_done(result):
            if isinstance(result, tuple) and len(result) == 2:
                ok, msg = result
            else:
                ok, msg = True, str(result)
            self._emit_task_result(
                "store_metadata_refresh",
                ok,
                msg or ("Store lists updated" if ok else "Failed to update store lists"),
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, result=str)
    def search_games_file(self, query):
        """Search all_games.txt by name. Returns JSON [{name, appid}, ...] max 200 results.

        Falls back to the Hubcap library when the local catalog returns
        zero hits AND a Hubcap API key is configured. The Hubcap library
        carries delisted titles (San Andreas, LEGO 2K Drive) that the
        Steam IStoreService applist no longer surfaces; users who own
        those titles can still install them, so they are addable from
        the home page filter.
        """
        from sff.utils import root_folder
        all_games_file = root_folder(outside_internal=True) / "all_games.txt"
        if not all_games_file.exists():
            self.update_games_file()
            return json.dumps([{"name": "Game list not found — downloading now. Please search again in a moment.", "appid": "0"}])

        # Cache parsed lines in memory so subsequent searches skip file I/O
        _cache = getattr(self, '_allgames_cache', None)
        if _cache is None:
            _id_re = re.compile(r"\[ID=(\d+)\]$")
            _cache = []
            try:
                with all_games_file.open(encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        m = _id_re.search(line)
                        if m:
                            _cache.append((line[:m.start()].strip(), m.group(1)))
            except Exception:
                return "[]"
            self._allgames_cache = _cache

        try:
            q_norm = _normalize_for_search(query)
            results = []
            for name, appid in _cache:
                if _matches_normalized(q_norm, _normalize_for_search(name)):
                    results.append({"name": name, "appid": appid})
                if len(results) >= 200:
                    break

            # Hubcap fallback for delisted games. The Steam applist drops
            # titles that have been removed from the store (San Andreas,
            # LEGO 2K Drive, etc.) but the games are still installable for
            # owners. Hubcap's library tracks them, so when the local file
            # has nothing and a key is configured, ask Hubcap. The user
            # query is alias-expanded ("gta" -> "grand theft auto", etc)
            # before being sent so abbreviated typing still hits Hubcap's
            # full game names. macOS-only / Linux-only entries are
            # dropped via Steam's appdetails endpoint.
            if not results and query and query.strip():
                try:
                    client = self._get_store_client()
                    if client is not None:
                        seen_ids = set()
                        candidates = []
                        for q in _alias_expanded_queries(query):
                            try:
                                hubcap_result = client.get_library(
                                    limit=200, offset=0,
                                    search=q, sort_by='updated',
                                )
                                for hg in (hubcap_result.games or []):
                                    if not (hg.app_id and hg.name):
                                        continue
                                    if hg.app_id in seen_ids:
                                        continue
                                    seen_ids.add(hg.app_id)
                                    candidates.append(hg)
                            except Exception as e:
                                logger.debug(
                                    "Hubcap /library failed for %r: %s", q, e,
                                )
                            if len(candidates) >= 200:
                                break
                        plat_map = _fetch_steam_platforms(
                            [hg.app_id for hg in candidates]
                        )
                        for hg in candidates:
                            meta = plat_map.get(hg.app_id) or {}
                            tags = meta.get("platforms") or {"_unknown"}
                            store_type = (meta.get("type") or "").lower()
                            parent_appid = meta.get("parent_appid")
                            delisted_blank = bool(meta.get("delisted_blank"))
                            # Structural DLC drops: parent appid set
                            # (and not a re-release), blank delisted
                            # entry, or non-game type.
                            if parent_appid and store_type != "rerelease":
                                continue
                            if delisted_blank:
                                continue
                            if store_type and store_type not in ("game", "demo", "mod", "rerelease"):
                                continue
                            # Drop non-Windows-only entries.
                            if "_unknown" not in tags and "windows" not in tags:
                                continue
                            results.append({
                                "name": str(hg.name),
                                "appid": str(hg.app_id),
                            })
                            if len(results) >= 200:
                                break
                        if results:
                            logger.info(
                                "search_games_file: local catalog miss for %r; "
                                "Hubcap fallback returned %d entries",
                                query, len(results),
                            )
                except Exception as exc:
                    logger.debug("Hubcap fallback in search_games_file failed: %s", exc)

            return json.dumps(results)
        except Exception as e:
            logger.debug("search_games_file failed: %s", e)
            return "[]"

    @pyqtSlot(result=str)
    def get_avatar_base64(self):
        """Read the global GBE avatar from GSE Saves/settings/ and return a base64 data URL.
        Returns empty string if no avatar is set."""
        import base64
        from sff.fix_game.config_generator import _get_gbe_saves_root
        settings_dir = _get_gbe_saves_root() / "settings"
        for ext in (".png", ".jpg", ".jpeg"):
            avatar_file = settings_dir / f"account_avatar{ext}"
            if avatar_file.exists():
                try:
                    data = avatar_file.read_bytes()
                    b64 = base64.b64encode(data).decode("ascii")
                    mime = "image/png" if ext == ".png" else "image/jpeg"
                    return f"data:{mime};base64,{b64}"
                except Exception:
                    pass
        return ""

    @pyqtSlot(str, result=str)
    def set_global_avatar(self, source_path):
        """Copy source_path to GSE Saves/settings/account_avatar.{ext}.
        Removes any existing avatar files with other extensions first.
        Returns 'ok' on success or an error message."""
        import shutil
        from sff.fix_game.config_generator import _get_gbe_saves_root
        src = Path(source_path)
        if not src.exists():
            return f"File not found: {source_path}"
        ext = src.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            return f"Unsupported format '{ext}' — use .png, .jpg, or .jpeg"
        settings_dir = _get_gbe_saves_root() / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        for old_ext in (".png", ".jpg", ".jpeg"):
            old = settings_dir / f"account_avatar{old_ext}"
            if old.exists() and old_ext != ext:
                try:
                    old.unlink()
                except Exception:
                    pass
        dst = settings_dir / f"account_avatar{ext}"
        try:
            shutil.copy2(src, dst)
            return "ok"
        except Exception as e:
            return str(e)

    @pyqtSlot(result=str)
    def _scan_installed_games(self):
        """Walk all Steam libraries and return JSON string of installed games.
        Runs on a background thread -- safe to call from _prefetch_installed_games."""
        if not self._steam_path:
            logger.warning("_scan_installed_games: self._steam_path is None")
            return "[]"
        from sff.storage.vdf import get_steam_libs
        import os
        managed_sources = _collect_steamidra_managed_sources(self._steam_path)

        libs = list(get_steam_libs(self._steam_path))
        if os.name == 'nt':
            from sff.disk_utils import find_steam_libraries_on_disk
            for lib in find_steam_libraries_on_disk():
                if lib not in libs:
                    libs.append(lib)
        games = []
        seen = set()
        skipped_missing_dir = 0
        for lib in libs:
            try:
                steamapps = lib / "steamapps"
                if not steamapps.exists():
                    continue
                for acf in steamapps.glob("appmanifest_*.acf"):
                    try:
                        text = acf.read_text(encoding="utf-8", errors="replace")
                        app_id = ""
                        name = ""
                        installdir = ""
                        for line in text.splitlines():
                            line = line.strip()
                            if '"appid"' in line:
                                app_id = line.split('"')[-2] if '"' in line else ""
                            elif '"name"' in line and not name:
                                name = line.split('"')[-2] if '"' in line else ""
                            elif '"installdir"' in line:
                                installdir = line.split('"')[-2] if '"' in line else ""
                        if not app_id or app_id in seen:
                            continue
                        if installdir:
                            game_path = steamapps / "common" / installdir
                            if not game_path.exists():
                                skipped_missing_dir += 1
                                continue
                        seen.add(app_id)
                        managed = managed_sources.get(app_id) or []
                        games.append({
                            "app_id": int(app_id) if app_id.isdigit() else 0,
                            "name": name or f"App {app_id}",
                            "installed": True,
                            "path": str(steamapps / "common" / installdir) if installdir else "",
                            "steamidra_managed": bool(managed),
                            "steamidra_source": ",".join(sorted(managed)),
                        })
                    except Exception as e:
                        logger.debug("_scan_installed_games: skipped %s: %s", acf.name, e)
                        continue
            except OSError:
                continue
        games.sort(key=lambda g: g.get("name", "").lower())
        if skipped_missing_dir:
            logger.info(
                "_scan_installed_games: %d game(s) skipped because their install folder "
                "is missing on disk (ACF present, <lib>/steamapps/common/<installdir> gone). "
                "Hit Refresh after restoring the folder.",
                skipped_missing_dir)
        return json.dumps(games)

    def _prefetch_installed_games(self):
        """Background-thread prefetch so get_installed_games returns from cache."""
        def _do():
            try:
                payload = self._scan_installed_games()
                import time as _t
                self._installed_games_cache = (_t.monotonic(), payload)
            except Exception:
                logger.debug("_prefetch_installed_games failed", exc_info=True)
        self._run_async(_do)

    def get_installed_games(self):
        """Returns JSON array of installed games from ALL Steam library folders.
        Returns cached data immediately, dispatches background refresh."""
        import time as _t
        _cached = getattr(self, '_installed_games_cache', None)
        if _cached:
            age = _t.monotonic() - _cached[0]
            if age < 3600.0:
                return _cached[1]
            # Stale: return cached immediately, dispatch background refresh
            self._prefetch_installed_games()
            return _cached[1]
        try:
            payload = self._scan_installed_games()
            self._installed_games_cache = (_t.monotonic(), payload)
            return payload
        except Exception:
            logger.exception("get_installed_games: scan failed")
            return "[]"

    @pyqtSlot(result=str)
    def get_fix_game_list(self):
        """Returns JSON list of games available for fixing."""
        return self.get_installed_games()

    @pyqtSlot(str, result=str)
    def extract_vdf_keys(self, vdf_path):
        """Extract depot keys from config.vdf."""
        try:
            from sff.storage.vdf import extract_depot_keys
            keys = extract_depot_keys(vdf_path or None)
            return json.dumps(keys or [])
        except Exception:
            return "[]"

    @pyqtSlot()
    def toggle_music(self):
        """Toggle background music on/off."""
        parent = self.parent()
        if parent and hasattr(parent, '_toggle_mute'):
            parent._toggle_mute()

    @pyqtSlot(result=str)
    def get_gse_identity(self):
        """Returns JSON {name, steam_id} from the GSE Saves global config, or empty object."""
        import configparser
        import os
        try:
            appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            user_ini = Path(appdata) / "GSE Saves" / "settings" / "configs.user.ini"
            if not user_ini.exists():
                return json.dumps({})
            cfg = configparser.ConfigParser()
            cfg.read(str(user_ini), encoding="utf-8")
            return json.dumps({
                "name": cfg.get("user::general", "account_name", fallback="").strip(),
                "steam_id": cfg.get("user::general", "account_steamid", fallback="").strip(),
            })
        except Exception:
            return json.dumps({})

    @pyqtSlot(result=str)
    def get_all_settings(self):
        """Returns JSON object with all current settings for the Settings page."""
        from sff.storage.settings import load_all_settings
        from sff.structs import Settings
        saved = load_all_settings()
        result = {}
        for s in Settings:
            raw = saved.get(s.key_name)
            if raw is None:
                result[s.key_name] = ""
            elif s.hidden:
                result[s.key_name] = "[ENCRYPTED]" if raw else ""
            elif s.value.type == dict:
                result[s.key_name] = ""
            else:
                result[s.key_name] = str(raw)
        return json.dumps(result)

    @pyqtSlot(result=str)
    def get_game_list(self):
        """Returns JSON list of games from all Steam libraries (name + app_id + path).
        Same scan as get_installed_games but always includes path."""
        return self.get_installed_games()

    @pyqtSlot(str)
    def fetch_library_images(self, app_ids_json):
        """Async: fetch canonical image URLs for library games via Steam API.
        Emits task_finished with task='library_images' and images={appid: url}.
        """
        try:
            app_ids = [int(x) for x in json.loads(app_ids_json or '[]') if x]
        except Exception:
            app_ids = []

        def _do():
            cached = {
                int(app_id): url
                for app_id, url in getattr(self, "_library_image_cache", {}).items()
                if str(app_id).isdigit() and url
            }
            missing = [app_id for app_id in app_ids if str(app_id) not in self._library_image_cache]
            if missing:
                fresh, _, _ = _fetch_steam_image_urls(missing)
                for app_id, url in fresh.items():
                    if url:
                        self._library_image_cache[str(app_id)] = url
                        self._library_image_cache.move_to_end(str(app_id))
                        while len(self._library_image_cache) > self._LIBRARY_IMAGE_CACHE_MAX:
                            self._library_image_cache.popitem(last=False)
                cached.update(fresh)
            return cached

        def _on_done(result):
            self.task_finished.emit(json.dumps({
                "task": "library_images",
                "success": True,
                "images": {str(k): v for k, v in result.items()},
            }))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def load_library(self):
        """Async: scan installed games + fetch Steam API image URLs in one pass.
        Emits task_finished with task='library_loaded' and games=[{...}].
        Mirrors search_games so image_url is ready before card rendering.
        """
        def _do():
            games = json.loads(self.get_installed_games())
            if not games:
                return []
            app_ids = [g["app_id"] for g in games if g.get("app_id")]
            cached = getattr(self, "_library_image_cache", {})
            missing = [int(app_id) for app_id in app_ids if str(app_id) not in cached]
            if missing:
                image_urls, _, _ = _fetch_steam_image_urls(missing)
                for img_appid, url in image_urls.items():
                    if url:
                        cached[str(img_appid)] = url
            for g in games:
                g["image_url"] = cached.get(str(g["app_id"]))
            return games

        def _on_done(games):
            self.task_finished.emit(json.dumps({
                "task": "library_loaded",
                "success": True,
                "games": games or [],
            }))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def refresh_library(self):
        self._installed_games_cache = None
        self.load_library()

    @pyqtSlot(str, str, str)
    def delete_game(self, app_id, game_path, mode):
        """Remove a game from the library and optionally delete its files.
        mode='applist' removes the stplug-in Lua only.
        mode='full' also deletes the ACF manifest and the game folder from disk.
        """
        def _do():
            import shutil
            app_id_int = int(app_id) if str(app_id).isdigit() else None
            if app_id_int is None:
                return (False, "Invalid App ID")

            # Lua deletion is the primary remove step in both modes. When
            # LumaCore is loaded, its DirWatch fires on the .lua delete
            # and emits CAppOverview_Change so Steam's library updates
            # live, no restart needed. If LumaCore isn't loaded yet the
            # user has to restart Steam for the game to disappear from
            # the library, which is what bit Svph (delete returned OK
            # but the game stayed in Steam's UI).
            lua_removed = False
            if self._steam_path:
                try:
                    from sff.steam_tools_compat import remove_lua_from_steam
                    remove_lua_from_steam(self._steam_path, app_id_int)
                    lua_removed = True
                except Exception as e:
                    logger.warning("delete_game: stplug-in Lua removal failed: %s", e)

            if mode != "full":
                if lua_removed:
                    return (True, "Removed from library. If the game still shows in Steam, restart Steam (or run Auto LC Setup if you haven't yet).")
                return (True, "Removed from library")

            # mode='full' also wipes the ACF manifest + the game folder.
            files_deleted = False

            if self._steam_path:
                try:
                    from sff.storage.vdf import get_steam_libs
                    for lib in get_steam_libs(self._steam_path):
                        acf = lib / "steamapps" / f"appmanifest_{app_id_int}.acf"
                        if acf.exists():
                            acf.unlink()
                            files_deleted = True
                            break
                except Exception as e:
                    logger.warning("delete_game: ACF removal failed: %s", e)

            if game_path:
                p = Path(game_path)
                if p.exists() and p.is_dir():
                    try:
                        shutil.rmtree(p, ignore_errors=False)
                        files_deleted = True
                    except Exception as e:
                        logger.warning("delete_game: folder removal failed: %s", e)

            if files_deleted:
                return (True, "Game removed and deleted from disk. Restart Steam if it still shows in the library.")
            return (True, "Removed from library (game folder not found or already gone). Restart Steam if it still shows in the library.")

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg = result
                self._emit_task_result("delete_game", ok, msg, app_id=app_id)
            else:
                self._emit_task_result("delete_game", False, "Delete failed", app_id=app_id)

        self._run_async(_do, on_done=_on_done)

    # ── Google Drive auth ─────────────────────────────────────────

    @pyqtSlot()
    def gdrive_authorize(self):
        """Start the Google Drive OAuth flow in a background thread."""
        def _do():
            from sff.google_drive import authorize, is_available
            if not is_available():
                return (False, "Google Drive is not available in this build.")
            log_lines = []
            ok = authorize(log_func=log_lines.append)
            return (ok, "\n".join(log_lines))

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg = result
                if ok:
                    from sff.google_drive import get_service, get_user_email
                    svc = get_service()
                    email = get_user_email(svc) if svc else ""
                    self._emit_task_result("gdrive_authorize", True, msg, email=email)
                else:
                    self._emit_task_result("gdrive_authorize", False, msg)
            else:
                self._emit_task_result("gdrive_authorize", False, "Authorization failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(result=str)
    def gdrive_status(self):
        """Return GDrive connection status as JSON (synchronous)."""
        from sff.google_drive import is_available, is_authenticated, get_service, get_user_email
        if not is_available():
            return json.dumps({"available": False, "connected": False, "email": ""})
        if not is_authenticated():
            return json.dumps({"available": True, "connected": False, "email": ""})
        svc = get_service()
        email = get_user_email(svc) if svc else ""
        return json.dumps({"available": True, "connected": bool(svc), "email": email})

    # ── All Save Locations ────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_custom_save_paths(self):
        """Returns user-defined per-game save paths as JSON {"<app_id>": "<path>"}."""
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            raw = get_setting(Settings.CLOUD_CUSTOM_SAVE_PATHS) or ""
            if not raw:
                return "{}"
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return json.dumps(parsed)
            except Exception:
                pass
            return "{}"
        except Exception as exc:
            logger.warning("get_custom_save_paths failed: %s", exc)
            return "{}"

    @pyqtSlot(str, str, result=str)
    def set_custom_save_path(self, app_id, path):
        """Add / update a custom save path for an app id. Empty path removes."""
        try:
            from sff.storage.settings import get_setting, set_setting
            from sff.structs import Settings
            raw = get_setting(Settings.CLOUD_CUSTOM_SAVE_PATHS) or ""
            mapping: dict = {}
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        mapping = parsed
                except Exception:
                    mapping = {}
            app_id_str = str(app_id or "").strip()
            if not app_id_str:
                return json.dumps({"ok": False, "error": "missing app_id"})
            new_path = (path or "").strip()
            if not new_path:
                mapping.pop(app_id_str, None)
            else:
                mapping[app_id_str] = new_path
            set_setting(Settings.CLOUD_CUSTOM_SAVE_PATHS, json.dumps(mapping))
            return json.dumps({"ok": True, "paths": mapping})
        except Exception as exc:
            logger.warning("set_custom_save_path failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str)
    def scan_all_save_locations(self, config_json):
        """Scan all emu save locations + Steam userdata. Emits task_finished with results list."""
        def _do():
            config = json.loads(config_json)
            steam_path = config.get("steam_path", "").strip()
            steam32_id = str(config.get("steam32_id", "")).strip()
            from sff.cloud_saves import scan_all_save_locations as _scan
            entries = _scan(
                steam_path=steam_path or None,
                steam32_id=steam32_id or None,
            )
            return entries

        def _on_done(entries):
            if entries is None:
                entries = []
            self._emit_task_result("scan_all_save_locations", True, f"Found {len(entries)} save folder(s)", entries=entries)

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def backup_all_save_locations(self, config_json):
        """Backup all (or selected) save location entries using the configured provider."""
        def _do():
            config = json.loads(config_json)
            entries = config.get("entries", [])
            provider = config.get("provider", "local").lower()
            dest_path = config.get("dest_path", "").strip()
            rclone_exe = config.get("rclone_exe", "").strip()
            remote_dest = config.get("remote_dest", "").strip()

            if not entries:
                return (False, "No entries to back up.", [])

            from sff.cloud_saves import (
                backup_save_location_local,
                backup_save_location_rclone,
                backup_save_location_gdrive,
            )

            log_lines = []
            succeeded = 0
            failed = 0
            total = len(entries)
            done = 0

            def _emit_backup_progress(label, s, f):
                self.download_progress.emit(json.dumps({
                    "task": "backup_progress",
                    "done": done, "total": total,
                    "percent": int(done / total * 100) if total > 0 else 0,
                    "current_label": label,
                    "succeeded": s, "failed": f,
                }))

            _emit_backup_progress("Starting...", 0, 0)

            if provider in ("local", "gdrive_sync"):
                if not dest_path:
                    return (False, "Destination folder not set.", [])
                for entry in entries:
                    result = backup_save_location_local(entry, dest_path, log_func=log_lines.append)
                    if result:
                        succeeded += 1
                    else:
                        failed += 1
                    done += 1
                    _emit_backup_progress(entry.get("label", ""), succeeded, failed)

            elif provider == "rclone":
                import threading
                import subprocess
                from concurrent.futures import ThreadPoolExecutor, as_completed
                if not rclone_exe:
                    bundled = WebBridge._get_bundled_tool_path("rclone")
                    rclone_exe = str(bundled) if bundled else ""
                if not rclone_exe or not remote_dest:
                    return (False, "rclone exe or remote destination not set.", [])
                lock = threading.Lock()
                _rclone_exe = rclone_exe
                _remote_dest = remote_dest

                import sys as _sys
                _no_window = {"creationflags": 0x08000000} if _sys.platform == "win32" else {}
                def _backup_one_rclone(entry):
                    thread_log = []
                    ok = backup_save_location_rclone(
                        entry, _rclone_exe, _remote_dest, log_func=thread_log.append
                    )
                    with lock:
                        log_lines.extend(thread_log)
                    return ok

                with ThreadPoolExecutor(max_workers=10) as ex:
                    futures = {ex.submit(_backup_one_rclone, e): e for e in entries}
                    for fut in as_completed(futures):
                        e = futures[fut]
                        try:
                            ok = fut.result()
                        except Exception as exc:
                            ok = False
                            with lock:
                                log_lines.append(f"[FAIL] {e.get('label', '?')}: {exc}")
                        with lock:
                            if ok:
                                succeeded += 1
                            else:
                                failed += 1
                        done += 1
                        _emit_backup_progress(e.get("label", ""), succeeded, failed)

                subprocess.run(
                    [_rclone_exe, "dedupe", "--dedupe-mode", "newest",
                     _remote_dest.rstrip("/") + "/SteaMidraAllSaves"],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=180, **_no_window,
                )

            elif provider == "gdrive_api":
                import threading
                from concurrent.futures import ThreadPoolExecutor, as_completed
                from sff.google_drive import (
                    get_service, get_backup_root, is_authenticated,
                )
                if not is_authenticated():
                    return (False, "Google Drive not connected. Use Connect button first.", [])
                svc = get_service()
                if not svc:
                    return (False, "Could not connect to Google Drive.", [])
                root_id = get_backup_root(svc)
                if not root_id:
                    return (False, "Could not create backup root on Google Drive.", [])
                from pathlib import Path as _Path
                valid_entries = []
                for e in entries:
                    sources = e.get("sources") if isinstance(e.get("sources"), list) else []
                    paths = [s.get("source_path") for s in sources if isinstance(s, dict)] or [e.get("source_path")]
                    if any(p and _Path(p).exists() for p in paths):
                        valid_entries.append(e)
                    else:
                        failed += 1
                        log_lines.append(
                            f"[SKIP] Source not found: {e.get('label', '?')} ({e.get('source_path', '?')})"
                        )

                folder_cache = {}
                lock = threading.Lock()

                def _backup_one_gdrive(entry):
                    thread_log = []
                    thread_svc = get_service()
                    if not thread_svc:
                        with lock:
                            log_lines.append(
                                f"[FAIL] {entry.get('label', '?')}: could not connect to Drive"
                            )
                        return False
                    thread_cache = dict(folder_cache)
                    ok = backup_save_location_gdrive(
                        entry, thread_svc, root_id,
                        log_func=thread_log.append,
                        folder_cache=thread_cache,
                    )
                    with lock:
                        log_lines.extend(thread_log)
                    return ok

                with ThreadPoolExecutor(max_workers=10) as ex:
                    futures = {ex.submit(_backup_one_gdrive, e): e for e in valid_entries}
                    for fut in as_completed(futures):
                        e = futures[fut]
                        try:
                            ok = fut.result()
                        except Exception as exc:
                            ok = False
                            with lock:
                                log_lines.append(f"[FAIL] {e.get('label', '?')}: {exc}")
                        with lock:
                            if ok:
                                succeeded += 1
                            else:
                                failed += 1
                        done += 1
                        _emit_backup_progress(e.get("label", ""), succeeded, failed)
            else:
                return (False, f"Provider '{provider}' not supported for all-saves backup.", [])

            ok = failed == 0
            msg = f"Backup complete: {succeeded} succeeded, {failed} failed"
            return (ok, msg, log_lines, provider, dest_path, rclone_exe, remote_dest)

        def _on_done(result):
            if isinstance(result, tuple) and len(result) >= 3:
                ok, msg, log_lines = result[0], result[1], result[2]
                self._emit_task_result("backup_all_save_locations", ok, msg, log="\n".join(log_lines))
                if ok and len(result) == 7:
                    _prov, _dest, _rclone_exe, _remote_dest = result[3], result[4], result[5], result[6]
                    import json as _json
                    from sff.storage.settings import set_setting as _set
                    from sff.structs import Settings as _S
                    if _prov in ('local', 'gdrive_sync'):
                        _cfg = {'provider': 'local', 'dest_path': _dest}
                    elif _prov == 'rclone':
                        _cfg = {'provider': 'rclone', 'rclone_exe': _rclone_exe, 'remote_dest': _remote_dest}
                    elif _prov == 'gdrive_api':
                        _cfg = {'provider': 'gdrive_api'}
                    else:
                        _cfg = None
                    if _cfg:
                        _set(_S.LAST_BACKUP_PROVIDER_CONFIG, _json.dumps(_cfg))
            else:
                self._emit_task_result("backup_all_save_locations", False, "Backup failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def scan_backup_root(self, config_json):
        """Scan a backup root (local or GDrive) and return location/game tree."""
        def _do():
            config = json.loads(config_json)
            provider = config.get("provider", "local").lower()
            backup_root = config.get("backup_root", "").strip()

            if provider == "gdrive_api":
                from sff.google_drive import get_service, list_backup_locations, is_authenticated
                if not is_authenticated():
                    return (False, "Google Drive not connected.", {})
                svc = get_service()
                if not svc:
                    return (False, "Could not connect to Google Drive.", {})
                locations = list_backup_locations(svc)
                return (True, "", locations)
            elif provider == "rclone":
                rclone_exe = config.get("rclone_exe", "").strip()
                remote_dest = config.get("remote_dest", "").strip()
                if not rclone_exe:
                    bundled = WebBridge._get_bundled_tool_path("rclone")
                    rclone_exe = str(bundled) if bundled else ""
                if not rclone_exe or not remote_dest:
                    return (False, "rclone exe or remote destination not set.", {})
                from sff.cloud_saves import scan_backup_root_rclone
                locations = scan_backup_root_rclone(rclone_exe, remote_dest)
                return (True, "", locations)
            else:
                if not backup_root:
                    return (False, "Backup root folder not set.", {})
                from sff.cloud_saves import scan_backup_root_local
                locations = scan_backup_root_local(backup_root)
                return (True, "", locations)

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg, locations = result
                self._emit_task_result("scan_backup_root", ok, msg, locations=locations)
            else:
                self._emit_task_result("scan_backup_root", False, "Scan failed", locations={})

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def restore_save_location(self, game_entry_json):
        """Restore a single game's saves from backup to its original source_path."""
        def _do():
            game_entry = json.loads(game_entry_json)
            log_lines = []
            from sff.cloud_saves import restore_save_entry
            result = restore_save_entry(game_entry, log_func=log_lines.append)
            if isinstance(result, dict):
                ok = bool(result.get("ok"))
                msg = result.get("message") or ("Restore complete" if ok else "Restore failed")
                return (ok, msg, log_lines, result.get("results", []))
            ok = bool(result)
            msg = "Restore complete" if ok else "Restore failed - check log"
            return (ok, msg, log_lines, [])

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg, log_lines = result[0], result[1], result[2]
                results = result[3] if len(result) > 3 else []
                self._emit_task_result("restore_save_location", ok, msg, log="\n".join(log_lines), results=results)
            else:
                self._emit_task_result("restore_save_location", False, "Restore failed")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(result=str)
    def dump_achievement_diagnostic(self):
        """A16: surface the LumaCore achievement diagnostic ring buffer.

        LumaCore writes <sff_data_dir>/lumacore_diag.txt on detach (and on
        any future menu-triggered dump path). This slot reads the file if
        present and returns its contents, capped to the last 16 KB so the
        Web UI / dialog stays responsive. Returns an empty string when
        the file does not exist yet (LumaCore writes on detach, so a
        running session sees nothing until Steam restarts).
        """
        try:
            from sff.utils import sff_data_dir
            path = sff_data_dir() / "lumacore_diag.txt"
            if not path.exists():
                return ""
            data = path.read_bytes()
            # Trim from the start so the most recent dumps survive.
            tail = data[-16384:] if len(data) > 16384 else data
            return tail.decode("utf-8", errors="replace")
        except Exception as exc:
            logger.exception("dump_achievement_diagnostic failed: %s", exc)
            return ""


def _fetch_steam_platforms(app_ids):
    """Look up Steam metadata for each appid via batched
    `IStoreBrowseService/GetItems/v1` calls.

    Returns a dict mapping appid (int) -> dict with four keys:
      'platforms'       : set of lowercase tags ("windows", "macos",
                          "linux") or `{"_unknown"}` when GetItems
                          returned no platform data
      'type'            : Steam's app type integer mapped to a
                          lowercase string ('game', 'dlc', 'demo',
                          'mod', 'tool', 'video', 'music',
                          'advertising'); '' when GetItems returned
                          no body for the appid
      'parent_appid'    : int when this appid is a DLC of another app
                          (Steam exposes this only for DLCs); None
                          for base games and demos
      'delisted_blank'  : True when GetItems returned the appid as a
                          row with no name and no type. Steam strips
                          all public metadata for fully removed
                          entries; classic delisted GAMES still
                          return name + type=0 (verified for GTA SA
                          classic, Resident Evil HD, Dark Souls PTDE
                          Edition, etc), so this flag is a strong
                          "this is removed-from-store DLC content"
                          signal

    Callers use `parent_appid` and `delisted_blank` as STRUCTURAL DLC
    drop signals — no name-keyword matching required. `platforms` is
    used to drop macOS-only / Linux-only ports.

    Switched from `appdetails` to `GetItems` because appdetails enforces
    a strict ~200 req / 5 min rate limit that returned HTTP 429 mid-flow
    on heavy searches. GetItems batches up to ~50 appids per request
    and has no per-IP rate limit visible.

    Uses the in-process `_STEAM_PLATFORM_CACHE` to avoid refetching
    on repeat searches.
    """
    if not app_ids:
        return {}
    import json as _json
    import urllib.request as _req
    import urllib.parse as _urlparse

    out: dict[int, dict] = {}
    pending: list[int] = []
    for raw in app_ids:
        try:
            aid = int(raw)
        except (TypeError, ValueError):
            continue
        if aid <= 0:
            continue
        cached = _STEAM_PLATFORM_CACHE.get(aid)
        if cached is not None:
            out[aid] = cached
        else:
            pending.append(aid)

    if not pending:
        return out

    # Batch in chunks. 50 per call is conservative; Steam accepts more
    # but the URL grows fast. After two consecutive batch failures we
    # bail and mark everything else unknown so a transient outage
    # doesn't stall the whole search worker.
    chunk_size = 50
    consecutive_failures = 0
    blank_default = {
        "platforms": {"_unknown"},
        "type": "",
        "parent_appid": None,
        "delisted_blank": False,
    }
    for start in range(0, len(pending), chunk_size):
        chunk = pending[start:start + chunk_size]
        if consecutive_failures >= 2:
            for aid in chunk:
                cached = dict(blank_default)
                _platform_cache_put(aid, cached)
                out[aid] = cached
            continue
        try:
            payload = {
                "ids": [{"appid": aid} for aid in chunk],
                "context": {"language": "english", "country_code": "US"},
                "data_request": {
                    "include_assets": False,
                    "include_platforms": True,
                    "include_basic_info": False,
                    "include_release": False,
                },
            }
            url = (
                "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json="
                + _urlparse.quote(_json.dumps(payload, separators=(",", ":")))
            )
            request = _req.Request(url, headers={"User-Agent": "Mozilla/5.0 SteaMidra"})
            with _req.urlopen(request, timeout=8, context=_get_ssl_ctx()) as resp:
                data = _json.loads(resp.read())
            seen: set[int] = set()
            for item in (data.get("response") or {}).get("store_items", []) or []:
                aid = item.get("appid")
                if not isinstance(aid, int):
                    continue
                seen.add(aid)
                name = item.get("name") or ""
                type_int = item.get("type")
                related = item.get("related_items") or {}
                parent_appid = related.get("parent_appid")
                if isinstance(parent_appid, int) and parent_appid <= 0:
                    parent_appid = None

                # Steam strips name + type from fully delisted entries.
                # Classic GAMES that the store hides keep name + type=0
                # (verified on GTA SA classic, Dark Souls PTDE, etc), so
                # an empty body really does mean "this is removed-from-
                # store DLC content".
                delisted_blank = (not name) and (type_int is None)

                plats_raw = item.get("platforms")
                tags: set[str] = set()
                if isinstance(plats_raw, dict):
                    if plats_raw.get("windows"):
                        tags.add("windows")
                    if plats_raw.get("mac"):
                        tags.add("macos")
                    if plats_raw.get("steamos_linux") or plats_raw.get("linux"):
                        tags.add("linux")
                if not tags:
                    tags = {"_unknown"}

                # GetItems uses int type codes. Map to lowercase
                # strings so callers can match on 'dlc' / 'music' /
                # 'video' / 'tool' / 'advertising' / 'rerelease' string
                # forms. `type: 14` with a `parent_appid` set is Steam's
                # re-release marker for Enhanced Edition / Definitive
                # Edition / GOTY / Director's Cut entries that share an
                # appid arrangement with DLC but ship as full games
                # (Metro Exodus EE 1449560, etc). Tag those as
                # "rerelease" so the search filter can keep them.
                type_str = ""
                if isinstance(type_int, int):
                    type_str = {
                        0: "game",
                        2: "dlc",
                        3: "demo",
                        4: "dlc",
                        5: "advertising",
                        6: "mod",
                        7: "tool",
                        9: "video",
                        10: "video",
                        11: "video",
                        12: "video",
                        13: "music",
                        14: "rerelease",
                        15: "video",
                    }.get(type_int, str(type_int))

                cached = {
                    "platforms": tags,
                    "type": type_str,
                    "parent_appid": parent_appid,
                    "delisted_blank": delisted_blank,
                }
                _platform_cache_put(aid, cached)
                out[aid] = cached
            # Anything we asked about that GetItems silently dropped
            # gets the unknown sentinel.
            for aid in chunk:
                if aid not in seen:
                    cached = dict(blank_default)
                    _platform_cache_put(aid, cached)
                    out[aid] = cached
            consecutive_failures = 0
        except Exception as e:
            logger.debug("Steam GetItems lookup failed for chunk starting at %s: %s", chunk[0], e)
            consecutive_failures += 1
            for aid in chunk:
                cached = dict(blank_default)
                _platform_cache_put(aid, cached)
                out[aid] = cached
    return out


def _fetch_steam_image_urls(app_ids):
    """Batch-fetch canonical image URLs via Steam IStoreBrowseService/GetItems/v1.

    Returns (images, types, nsfw_map) where:
      images:   dict mapping appid (int) -> canonical URL string
      types:    dict mapping appid (int) -> Steam app type int
                  (1=game, 2=dlc, 3=demo, 13=music, etc.)
      nsfw_map: dict mapping appid (int) -> bool (True if NSFW content descriptors detected)
    On any network or parse error returns ({}, {}, {}) so callers fall back gracefully.
    """
    if not app_ids:
        return {}, {}, {}
    import json as _json
    import urllib.request as _req
    import urllib.parse as _urlparse
    result = {}
    types = {}
    nsfw_map = {}
    try:
        payload = {
            "ids": [{"appid": aid} for aid in app_ids],
            "context": {"language": "english", "country_code": "US"},
            "data_request": {"include_assets": True, "include_content_descriptors": True},
        }
        url = (
            "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json="
            + _urlparse.quote(_json.dumps(payload, separators=(",", ":")))
        )
        request = _req.Request(url, headers={"User-Agent": "SteaMidra/5.4.0"})
        with _req.urlopen(request, timeout=5, context=_get_ssl_ctx()) as resp:
            data = _json.loads(resp.read())
        _NSFW_CD_IDS = frozenset({1, 2, 3, 4})
        for item in data.get("response", {}).get("store_items", []):
            appid = item.get("appid")
            header = (item.get("assets") or {}).get("header", "")
            if appid and header:
                result[appid] = (
                    f"https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/{header}"
                )
            if appid:
                types[appid] = int(item.get("type") or 1)
                cd_ids = (item.get("content_descriptors") or {}).get("ids") or []
                nsfw_map[appid] = any(cid in _NSFW_CD_IDS for cid in cd_ids)
    except Exception as e:
        logger.debug("Steam image batch fetch failed: %s", e)
    return result, types, nsfw_map


_STEAM_APPLIST_CACHE = None
_STEAM_APPLIST_CACHE_TIME = 0.0

# In-process cache of Steam GetItems metadata for Hubcap-only entries.
# Maps appid (int) -> dict with keys 'platforms' (set of lowercase tags
# or {"_unknown"}), 'type' (str), 'parent_appid' (int or None), and
# 'delisted_blank' (bool — True when GetItems returned the appid with
# no name and no type, the strongest "Steam removed all metadata"
# signal we have). The DLC filter uses parent_appid + delisted_blank
# as structural drop signals; no name keywords involved.
from collections import OrderedDict as _OrderedDict
_STEAM_PLATFORM_CACHE: "_OrderedDict[int, dict]" = _OrderedDict()
_STEAM_PLATFORM_CACHE_MAX = 2000

def _platform_cache_put(aid: int, entry: dict) -> None:
    _STEAM_PLATFORM_CACHE[aid] = entry
    _STEAM_PLATFORM_CACHE.move_to_end(aid)
    while len(_STEAM_PLATFORM_CACHE) > _STEAM_PLATFORM_CACHE_MAX:
        _STEAM_PLATFORM_CACHE.popitem(last=False)

_NONGAME_NAME_KW = ("soundtrack", "art book", "artbook", " ost", "music pack", "digital artbook")

_NON_GAME_TYPES = frozenset({2, 4, 6, 7, 9, 10, 11, 12, 13})


@lru_cache(maxsize=4096)
def _normalize_for_search(text):
    """Strip trademark marks, registered marks, accents, and odd
    punctuation so a user typing 'lego batman' still matches a Steam
    title rendered as 'LEGO® Batman™: Legacy of the Dark Knight'.
    Returns a lowercased ASCII-only blob with whitespace collapsed.
    Empty / non-string inputs return ''.
    """
    if not text or not isinstance(text, str):
        return ""
    # Drop the trademark / registered / copyright / sound-recording
    # marks before NFKD. NFKD turns ™ into the literal letters "TM"
    # (compatibility decomposition), which then sticks to the previous
    # word and breaks the match. Do the same for the ligatures Steam
    # sometimes ships in catalog names.
    for mark in ("\u2122", "\u00ae", "\u00a9", "\u2117", "\u2120"):
        text = text.replace(mark, "")
    decomposed = _ud.normalize("NFKD", text)
    out_chars = []
    for ch in decomposed:
        cat = _ud.category(ch)
        # Drop combining marks (Mn) and bare symbol categories so
        # any leftover decorative glyphs the explicit pass missed
        # don't end up as artifacts.
        if cat.startswith("M") or cat.startswith("S"):
            continue
        # Treat any non-alphanumeric character as a single space so
        # "lego: batman" and "lego batman" land on the same key.
        if not ch.isalnum():
            out_chars.append(" ")
            continue
        out_chars.append(ch.lower())
    collapsed = "".join(out_chars).split()
    return " ".join(collapsed)


# Common franchise / publisher abbreviations users type instead of full names.
# Expansions are alternatives — any of them OR the original token must hit.
_ALIAS_EXPANSIONS = {
    "gta":   ["grand theft auto"],
    "rdr":   ["red dead redemption"],
    "cod":   ["call of duty"],
    "re":    ["resident evil"],
    "tf2":   ["team fortress 2"],
    "csgo":  ["counter strike global offensive", "counter-strike global offensive"],
    "cs2":   ["counter strike 2", "counter-strike 2"],
    "css":   ["counter strike source", "counter-strike source"],
    "cs":    ["counter strike", "counter-strike"],
    "kh":    ["kingdom hearts"],
    "mh":    ["monster hunter"],
    "ff":    ["final fantasy"],
    "ds":    ["dark souls"],
    "ds1":   ["dark souls"],
    "ds2":   ["dark souls 2", "dark souls ii"],
    "ds3":   ["dark souls 3", "dark souls iii"],
    "er":    ["elden ring"],
    "mk":    ["mortal kombat"],
    "ac":    ["assassins creed", "assassin s creed"],
    "btd":   ["bloons td"],
    "tw":    ["total war"],
    "wh":    ["warhammer"],
    "sf":    ["street fighter"],
    "tk":    ["tekken"],
    "p5":    ["persona 5"],
    "p4":    ["persona 4"],
    "p3":    ["persona 3"],
    "lol":   ["league of legends"],
    "pubg":  ["playerunknown s battlegrounds", "playerunknowns battlegrounds"],
    "wow":   ["world of warcraft"],
    "hots":  ["heroes of the storm"],
    "sc2":   ["starcraft 2", "starcraft ii"],
    "d2":    ["diablo 2", "diablo ii", "destiny 2"],
    "d3":    ["diablo 3", "diablo iii"],
    "d4":    ["diablo 4", "diablo iv"],
    "wukong": ["black myth wukong"],
}


def _store_words(text_norm):
    return [w for w in (text_norm or "").split() if w]


def _store_query_has_alias(query_norm):
    if query_norm in _ALIAS_EXPANSIONS:
        return True
    return any(token in _ALIAS_EXPANSIONS for token in _store_words(query_norm))


def _store_short_loose_query(query_norm):
    compact = (query_norm or "").replace(" ", "")
    return len(compact) < 3 and not compact.isdigit() and not _store_query_has_alias(query_norm)


def _store_word_start_match(query_norm, name_norm):
    tokens = _store_words(query_norm)
    if not tokens:
        return True
    words = _store_words(name_norm)
    pos = 0
    for token in tokens:
        found = False
        for idx in range(pos, len(words)):
            if words[idx].startswith(token):
                pos = idx + 1
                found = True
                break
        if not found:
            return False
    return True


def _store_token_match(token, name_norm):
    if len(token) < 3:
        return token in _store_words(name_norm)
    return token in name_norm


def _store_all_tokens_match(query_norm, name_norm):
    tokens = _store_words(query_norm)
    if not tokens:
        return True
    for token in tokens:
        if _store_token_match(token, name_norm):
            continue
        alts = _ALIAS_EXPANSIONS.get(token)
        if alts and any(_store_all_tokens_match(_normalize_for_search(alt), name_norm) for alt in alts):
            continue
        return False
    return True


def _store_alias_score(query_norm, name_norm):
    candidates = []
    seen = set()
    for candidate in _alias_expanded_queries(query_norm):
        cand_norm = _normalize_for_search(candidate)
        if not cand_norm or cand_norm == query_norm or cand_norm in seen:
            continue
        seen.add(cand_norm)
        candidates.append(cand_norm)
    for cand_norm in candidates:
        if name_norm == cand_norm:
            return 0
        if name_norm.startswith(cand_norm):
            return 1
        if _store_word_start_match(cand_norm, name_norm):
            return 2
        if _store_all_tokens_match(cand_norm, name_norm):
            return 3
        if cand_norm in name_norm:
            return 4
    return None


def _store_search_score(query, name, appid=None):
    query_norm = _normalize_for_search(query or "")
    name_norm = _normalize_for_search(name or "")
    appid_text = str(appid or "").strip()
    if not query_norm:
        return (50, name_norm, appid_text)

    compact = query_norm.replace(" ", "")
    if compact.isdigit() and appid_text:
        if appid_text == compact:
            return (0, "", appid_text)
        if len(compact) >= 3 and appid_text.startswith(compact):
            return (3, appid_text, name_norm)

    if name_norm == query_norm:
        return (1, name_norm, appid_text)

    has_alias = _store_query_has_alias(query_norm)
    short_alias = has_alias and len(compact) < 3
    if not short_alias and name_norm.startswith(query_norm):
        return (2, name_norm, appid_text)
    if _store_short_loose_query(query_norm):
        if len(compact) >= 2 and _store_word_start_match(query_norm, name_norm):
            return (4, name_norm, appid_text)
        return (99, name_norm, appid_text)
    if not short_alias and _store_word_start_match(query_norm, name_norm):
        return (4, name_norm, appid_text)

    alias_score = _store_alias_score(query_norm, name_norm)
    if alias_score is not None:
        return (5, alias_score, name_norm, appid_text)

    if short_alias and name_norm.startswith(query_norm):
        return (6, name_norm, appid_text)
    if short_alias and _store_word_start_match(query_norm, name_norm):
        return (7, name_norm, appid_text)
    if _store_all_tokens_match(query_norm, name_norm):
        return (8, name_norm, appid_text)
    if not short_alias and not _store_short_loose_query(query_norm) and query_norm in name_norm:
        return (9, name_norm, appid_text)
    return (99, name_norm, appid_text)


def _matches_normalized(query_norm, name_norm):
    return _store_search_score(query_norm, name_norm)[0] < 99


def _attach_store_request_id(data, request_id):
    if not isinstance(data, dict):
        data = {"games": [], "total": 0}
    if request_id:
        data["request_id"] = str(request_id)
    return data


def _alias_expanded_queries(query):
    """Yield candidate query strings for remote search backends that
    do plain substring matching on game names.

    Hubcap's /library and /search endpoints don't know about
    abbreviations, so a user typing "gta san andreas" never hits a
    title stored as "Grand Theft Auto: San Andreas". For each known
    alias token (gta, re, cod, rdr, kh, er, tf2, cs2, ...) we generate
    one extra query string with that token swapped for each of its
    expansions. Original query is yielded first; expansions follow.
    Duplicates are de-duped. Returns a list, not a generator, so the
    caller can `len()` and reorder freely.
    """
    if not query or not isinstance(query, str):
        return []
    raw = query.strip()
    if not raw:
        return []
    out = [raw]
    seen = {raw.lower()}
    # The alias map is keyed on lowercase tokens. Split on whitespace
    # only, preserving punctuation, so "GTA: San Andreas" still has
    # "gta" as the first token after lowercase.
    tokens = raw.split()
    if not tokens:
        return out
    # Whole-query alias hit ("gta" alone, "wukong" alone, etc).
    full_alts = _ALIAS_EXPANSIONS.get(raw.lower())
    if full_alts:
        for alt in full_alts:
            if alt.lower() not in seen:
                seen.add(alt.lower())
                out.append(alt)
    # Per-token swap. For each tokenN that has an alias, build a new
    # query with tokenN replaced by each of its expansions, leaving
    # the rest of the tokens untouched. Cap the explosion so a query
    # with two aliased tokens doesn't fan out to N*M candidates.
    for i, tok in enumerate(tokens):
        alts = _ALIAS_EXPANSIONS.get(tok.lower())
        if not alts:
            continue
        for alt in alts:
            new_tokens = list(tokens)
            new_tokens[i] = alt
            cand = " ".join(new_tokens)
            key = cand.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)
            if len(out) >= 6:
                return out
    return out


def _load_steam_applist():
    global _STEAM_APPLIST_CACHE, _STEAM_APPLIST_CACHE_TIME
    import time as _time
    import json as _json
    import urllib.request as _req

    _now = _time.time()
    if _STEAM_APPLIST_CACHE is not None and (_now - _STEAM_APPLIST_CACHE_TIME) < 86400:
        return _STEAM_APPLIST_CACHE

    from sff.utils import root_folder
    _all_games_file = root_folder(outside_internal=True) / "all_games.txt"
    _all_games_file.parent.mkdir(parents=True, exist_ok=True)

    _merged: dict[int, dict] = {}

    def _add_apps(apps):
        for a in apps:
            aid = a.get("appid") or a.get("app_id")
            if aid and isinstance(aid, (int, float, str)):
                aid_int = int(aid)
                if aid_int > 0 and aid_int not in _merged:
                    name = str(a.get("name") or f"App {aid_int}").strip()
                    if name:
                        _merged[aid_int] = {"name": name, "appid": aid_int}

    # 1. Local all_games.txt (fast, no network)
    if _all_games_file.is_file() and _all_games_file.stat().st_size > 0:
        try:
            _apps_from_txt = []
            _line_re = re.compile(r'^(.*)\s+\[ID=(\d+)\]$')
            with _all_games_file.open(encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.rstrip()
                    _m = _line_re.match(_line)
                    if _m:
                        _apps_from_txt.append({"name": _m.group(1), "appid": int(_m.group(2))})
            _add_apps(_apps_from_txt)
            logger.debug("Steam applist loaded from all_games.txt: %d apps", len(_apps_from_txt))
        except Exception as _exc:
            logger.debug("all_games.txt load failed: %s", _exc)

    # 2. Steam API (short timeout, best-effort)
    try:
        from sff.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        _api_key = get_setting(Settings.STEAM_WEB_API_KEY)
        if not isinstance(_api_key, str) or not _api_key.strip():
            _api_key = _DEFAULT_KEY
        _params = {"key": _api_key, "max_results": "50000",
                   "include_games": "1", "include_dlc": "0",
                   "include_software": _should_show_software(),
                   "include_videos": "0", "include_hardware": "0"}
        _games = []
        _base = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
        for _ in range(3):
            try:
                _qs = "&".join(f"{k}={v}" for k, v in _params.items())
                _req2 = _req.Request(f"{_base}?{_qs}", headers={"User-Agent": "SteaMidra/6.1.0"})
                with _req.urlopen(_req2, timeout=5, context=_get_ssl_ctx()) as _resp:
                    _data = _json.loads(_resp.read())
                _apps_batch = _data.get("response", {}).get("apps", [])
                _games.extend(_apps_batch)
                if not _data.get("response", {}).get("have_more_results"):
                    break
                _last = _data.get("response", {}).get("last_appid")
                if _last:
                    _params["last_appid"] = str(_last)
                else:
                    break
            except Exception:
                break
        if _games:
            _add_apps(_games)
            logger.debug("Steam API contributed %d apps", len(_games))
    except Exception as _exc:
        logger.debug("Steam API fetch skipped: %s", _exc)

    # 3. GitHub mirrors — load from store_metadata/ cache first,
    #    refresh when older than 6 hours. SFF-main already ships
    #    store_metadata/games.json etc so first-launch is instant.
    _mirror_urls = {
        "games_appid.json": "https://raw.githubusercontent.com/jsnli/steamappidlist/refs/heads/master/data/games_appid.json",
        "software_appid.json": "https://raw.githubusercontent.com/jsnli/steamappidlist/refs/heads/master/data/software_appid.json",
    }
    _mirror_dir = root_folder(outside_internal=True) / "store_metadata"
    _mirror_dir.mkdir(parents=True, exist_ok=True)

    import concurrent.futures as _cf

    def _fetch_github_mirror(filename, url):
        cache_file = _mirror_dir / filename
        # Use cached copy when it's fresh enough (6 hours).
        try:
            if cache_file.is_file():
                _age = _time.time() - cache_file.stat().st_mtime
                if _age < 21600:
                    _payload = _json.loads(cache_file.read_bytes())
                    return _payload
        except Exception:
            pass
        try:
            import httpx as _httpx
            _resp = _httpx.get(url, timeout=20, follow_redirects=True)
            if _resp.status_code != 200:
                return None
            _payload = _resp.json()
            try:
                cache_file.write_bytes(_resp.content)
            except Exception:
                pass
            return _payload
        except Exception:
            return None

    def _add_mirror_payload(payload):
        if isinstance(payload, dict):
            for _key_str, _val_name in payload.items():
                if _key_str.isdigit():
                    _add_apps([{"name": str(_val_name), "appid": int(_key_str)}])
        elif isinstance(payload, list):
            for _entry in payload:
                if isinstance(_entry, dict) and "appid" in _entry:
                    _add_apps([{"name": _entry.get("name", ""), "appid": _entry["appid"]}])

    # Merge games.json if it's already cached (game_list_fallback.py handles its own fetch).
    _gj = _mirror_dir / "games.json"
    if _gj.is_file():
        try:
            _games_payload = _json.loads(_gj.read_bytes())
            _add_mirror_payload(_games_payload)
        except Exception:
            pass

    try:
        with _cf.ThreadPoolExecutor(max_workers=2) as _ex:
            _futures = {_ex.submit(_fetch_github_mirror, fn, u): fn for fn, u in _mirror_urls.items()}
            for _fut in _cf.as_completed(_futures):
                try:
                    _payload = _fut.result()
                    if _payload:
                        _add_mirror_payload(_payload)
                except Exception:
                    pass
    except Exception as _exc:
        logger.debug("GitHub mirror batch failed: %s", _exc)

    # 4. Build the merged list and cache it
    _result = list(_merged.values())
    if _result:
        try:
            _gs = [x.get("name", "UNKNOWN GAME") + f" [ID={x.get('appid')}]" for x in _result]
            _gs.sort()
            with _all_games_file.open("w", encoding="utf-8") as _f:
                _f.write("\n".join(_gs))
        except Exception:
            pass
        _STEAM_APPLIST_CACHE = _result
        _STEAM_APPLIST_CACHE_TIME = _now
        _result.sort(key=lambda x: x.get('appid', 0))
        logger.info("Steam applist built — %s total apps", len(_result))
        return _result

    _STEAM_APPLIST_CACHE = []
    _STEAM_APPLIST_CACHE_TIME = _now
    return []


def _search_steam_catalog(query, offset, per_page, sort_by='updated'):
    """Fallback store search using full Steam public app list when Hubcap is unavailable."""
    apps = _load_steam_applist()
    if not apps:
        return {"games": [], "total": 0, "fallback": True}
    if query:
        # Normalize query and each candidate name so trademark marks,
        # accents, and punctuation don't block hits like
        # "lego batman" → "LEGO® Batman™: Legacy of the Dark Knight".
        q_norm = _normalize_for_search(query)
        if q_norm:
            apps = [
                a for a in apps
                if _store_search_score(q_norm, a.get("name", ""), a.get("appid"))[0] < 99
            ]
    # Relevance boost: exact/prefix/substring matches always land on page 1
    # regardless of sort mode. Within each relevance tier, the user's sort
    # preference is preserved via stable sort (two-pass).
    sb = (sort_by or 'updated').lower()
    if sb == 'name_asc':
        apps.sort(key=lambda a: (a.get('name') or '').lower())
    elif sb == 'name_desc':
        apps.sort(key=lambda a: (a.get('name') or '').lower(), reverse=True)
    elif sb == 'oldest':
        apps.sort(key=lambda a: a.get('appid') or 0)
    elif sb == 'newest':
        apps.sort(key=lambda a: a.get('appid') or 0, reverse=True)
    # 'updated' falls through to natural order.
    if query:
        apps.sort(key=lambda a: _store_search_score(query, a.get("name", ""), a.get("appid")))
    total = len(apps)
    # When a text query is present, fetch enough candidates so the
    # relevance sort at the end actually puts exact/prefix matches
    # on the first page. Without this, a game at position 25 in the
    # update-date sort ("Witch It") never surfaces on page 1.
    fetch_count = 200 if query else per_page
    page_apps = apps[offset: offset + fetch_count]
    # Image metadata only for the actual page window.
    actual_page = page_apps[0: per_page]
    app_ids = [a["appid"] for a in actual_page if a.get("appid")]
    image_urls, type_map, nsfw_map = _fetch_steam_image_urls(app_ids)
    games = []
    for a in actual_page:
        appid = a.get("appid", 0)
        if type_map.get(appid) in _NON_GAME_TYPES:
            continue
        name_lc = a.get("name", f"App {appid}").lower()
        if any(kw in name_lc for kw in _NONGAME_NAME_KW):
            continue
        row = {
            "app_id": appid,
            "name": a.get("name", f"App {appid}"),
            "last_updated": "",
            "status": "",
            "size": 0,
            "image_url": image_urls.get(appid),
            "nsfw": bool(nsfw_map.get(appid, False)),
        }
        enrich_game_dict(row)
        games.append(row)
    return {"games": games, "total": total, "fallback": True}


def _format_size(size_bytes):
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
