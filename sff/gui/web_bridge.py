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
import urllib
import urllib.request as _req
import urllib.parse as _urlparse
import urllib.error as _urlerror

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_DDMOD_PCT_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%\s")
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)



from sff.gui.bridges.cloudsaves_bridge import (
    _bridge_backup_all_save_locations,
    _bridge_backup_cloud_save,
    _bridge_gdrive_authorize,
    _bridge_gdrive_status,
    _bridge_get_custom_save_paths,
    _bridge_rclone_backup_save,
    _bridge_rclone_list_remotes,
    _bridge_rclone_open_config,
    _bridge_rclone_test_remote,
    _bridge_restore_cloud_save,
    _bridge_restore_save_location,
    _bridge_scan_all_save_locations,
    _bridge_scan_backup_root,
    _bridge_scan_cloud_games,
    _bridge_set_custom_save_path
)
from sff.gui.bridges.download_bridge import (
    _bridge_apply_auto_update_default,
    _bridge_auto_update_was_registered,
    _bridge_download_dlc_oureveryday,
    _bridge_download_game_ddmod,
    _bridge_download_game_fastest,
    _bridge_download_game_version,
    _bridge_download_game_version_native,
    _bridge_download_game_with_source,
    _bridge_import_local_lua,
    _bridge_run_linux_ddmod_fallback,
    _bridge_run_linux_fastest,
    _bridge_run_local_import,
    _bridge_run_windows_fastest,
    _bridge_show_linux_fastest_workflow_notice,
    _bridge_track_download,
    _bridge_unlock_steam_readonly
)
from sff.gui.bridges.game_bridge import (
    _bridge_extract_vdf_keys,
    _bridge_fix_game,
    _bridge_generate_gbe_token,
    _bridge_revert_game,
    _bridge_run_game_action,
    _bridge_run_game_action_outside,
    _bridge_validate_game_files
)
from sff.gui.bridges.misc_bridge import (
    _bridge__scan_installed_games,
    _bridge_app_update_check,
    _bridge_browse_custom_background_file,
    _bridge_browse_ddmod_download_folder,
    _bridge_browse_game_folder,
    _bridge_browse_image_file,
    _bridge_browse_steam_path,
    _bridge_cancel_bulk_import,
    _bridge_check_game_update,
    _bridge_clear_custom_background,
    _bridge_copy_to_clipboard,
    _bridge_delete_game,
    _bridge_dlc_check_get_list,
    _bridge_dump_achievement_diagnostic,
    _bridge_enqueue_dropped_blobs,
    _bridge_enqueue_dropped_files,
    _bridge_export_settings_file,
    _bridge_fetch_depot_history,
    _bridge_fetch_library_images,
    _bridge_fix_slssteam_hash,
    _bridge_get_all_settings,
    _bridge_get_app_version,
    _bridge_get_applist_games,
    _bridge_get_avatar_base64,
    _bridge_get_bundled_tool_path,
    _bridge_get_disk_usage,
    _bridge_get_fix_game_list,
    _bridge_get_game_branches,
    _bridge_get_game_list,
    _bridge_get_game_update_override,
    _bridge_get_game_update_state,
    _bridge_get_games_file_info,
    _bridge_get_gse_identity,
    _bridge_get_launch_option_status,
    _bridge_get_platform,
    _bridge_get_provider_cache_status,
    _bridge_get_recent_lua_files,
    _bridge_get_setting,
    _bridge_get_steam_libraries,
    _bridge_get_storage_paths,
    _bridge_get_stored_api_key,
    _bridge_get_webui_translations,
    _bridge_import_depot_manifest_html,
    _bridge_import_settings_file,
    _bridge_install_lumacore,
    _bridge_launch_game,
    _bridge_let_updates_add_game,
    _bridge_let_updates_apply,
    _bridge_let_updates_list_games,
    _bridge_let_updates_set_helper,
    _bridge_linux_setup_now,
    _bridge_load_library,
    _bridge_lumacore_check_update,
    _bridge_lumacore_deactivate,
    _bridge_lure_fix_acf,
    _bridge_open_archive_dialog,
    _bridge_open_exe_file_dialog,
    _bridge_open_file_dialog,
    _bridge_open_folder_scan,
    _bridge_open_log_window,
    _bridge_open_lua_file_dialog,
    _bridge_open_manifest_folder_dialog,
    _bridge_open_url,
    _bridge_provider_contribute_preview,
    _bridge_provider_contribute_submit,
    _bridge_provider_reset_submitted,
    _bridge_provider_update_now,
    _bridge_refresh_game_branches,
    _bridge_refresh_library,
    _bridge_restart_steam,
    _bridge_run_bulk_import,
    _bridge_ryuu_request_branch,
    _bridge_save_ryuu_key,
    _bridge_set_active_library,
    _bridge_set_custom_background,
    _bridge_set_game_update_check,
    _bridge_set_game_update_override,
    _bridge_set_global_avatar,
    _bridge_set_setting,
    _bridge_signal_ready,
    _bridge_steam_updates_get_state,
    _bridge_steam_updates_set_state,
    _bridge_test_ryuu_api_key,
    _bridge_test_ryuu_key,
    _bridge_toggle_music,
    _bridge_toggle_online_fix,
    _bridge_toggle_ui,
    _bridge_update_games_file,
    _bridge_window_close,
    _bridge_window_is_maximized,
    _bridge_window_maximize,
    _bridge_window_minimize
)
from sff.gui.bridges.store_bridge import (
    _bridge_connect_store,
    _bridge_refresh_store_metadata,
    _bridge_search_games,
    _bridge_search_games_file,
    _bridge_store_disconnect,
    _bridge_update_store_lists,
    _bridge_warm_store_metadata
)
# Bridge module imports — thin delegates to domain-specific bridge files

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
        except BaseException as e:
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                raise
            logger.exception("Worker error: %s", e)
            self.error.emit(str(e))


def _should_show_software() -> str:
    """Return ``"1"`` when STORE_SHOW_SOFTWARE is ON, ``"0"`` when OFF.

    A17 widens the Store list filter to ``{game, application}``. Default
    is ON: missing / empty / True / "True" all resolve to ``"1"``. Only
    an explicit ``False`` / ``"False"`` clamps the list back to games.
    Both Store list callsites in this module share this single helper.
    """
    try:
        from sff.core.storage.settings import get_setting as _get
        from sff.core.structs import Settings
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
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings
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
        from sff.core.utils import root_folder
        saved_lua_root = root_folder(outside_internal=True) / "saved_lua"
    _scan_lua_root(Path(saved_lua_root), "saved_lua")
    cwd_saved = Path.cwd() / "saved_lua"
    if cwd_saved != Path(saved_lua_root).resolve() and cwd_saved.exists():
        _scan_lua_root(cwd_saved, "saved_lua")
    if steam_path:
        _scan_lua_root(Path(steam_path) / "config" / "stplug-in", "stplug-in")
    return {appid: sorted(sources) for appid, sources in managed_sources.items()}


_CRACK_BUILDID_CACHE: dict[str, str] | None = None
_CRACK_BUILDID_TIME = 0.0
_CRACK_BUILDID_FETCHING = False


def _prefetch_crack_buildids():
    global _CRACK_BUILDID_CACHE, _CRACK_BUILDID_TIME, _CRACK_BUILDID_FETCHING
    import time as _t
    if _CRACK_BUILDID_CACHE is not None and (_t.time() - _CRACK_BUILDID_TIME) < 3600:
        return
    if _CRACK_BUILDID_FETCHING:
        return
    _CRACK_BUILDID_FETCHING = True
    try:
        import httpx
        resp = httpx.get(
            "https://raw.githubusercontent.com/KoriaPolis/CrakFiles/main/crackfiles.json",
            follow_redirects=True, timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            out = {}
            for g in data:
                name = str(g.get("name", "") or "").strip().lower()
                bid = str(g.get("buildid", "") or "").strip()
                if name and bid:
                    out[name] = bid
            _CRACK_BUILDID_CACHE = out
            _CRACK_BUILDID_TIME = _t.time()
    except Exception:
        pass
    finally:
        _CRACK_BUILDID_FETCHING = False


def _get_crack_buildid_map() -> dict[str, str]:
    """Return cached crack buildid map. Never blocks — returns empty if not ready."""
    return _CRACK_BUILDID_CACHE or {}


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
        self._hubcap_unavailable = self._is_hubcap_disabled()
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
        # Provider enrichment can perform dozens of Steam app-info requests.
        # Let the user interact with the app first instead of competing with
        # the initial Store/Library render immediately after startup.
        QTimer.singleShot(120_000, self._maybe_auto_contribute_provider)
        self._provider_cache_refreshing = False
        self._provider_cache_timer = QTimer(self)
        self._provider_cache_timer.setInterval(10 * 60 * 1000)
        self._provider_cache_timer.timeout.connect(self._maybe_auto_refresh_provider_cache)
        self._provider_cache_timer.start()
        # Network prefetches must never run on Qt's GUI thread.  The old
        # singleShot called the HTTP function directly and could stall every
        # paint/input event for the full request timeout.
        QTimer.singleShot(5000, lambda: self._run_async(_prefetch_crack_buildids))
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

        self._store_metadata_warming = False
        self._store_search_in_flight = False
        self._pending_store_search = None

        # Preload disk-cached fallback data after the first frame.  Parsing
        # games.json can involve tens of MB, so it belongs on a worker too.
        self._preload_all_store_data()

    def _preload_all_store_data(self):
        """Warm store metadata off the GUI thread, once per process window."""
        def _start():
            # If the Store is already searching, that worker will populate the
            # same caches. Do not create a second parser/network contender.
            if self._store_metadata_warming or self._store_search_in_flight:
                return
            self._store_metadata_warming = True

            def _do():
                from sff.game_list_fallback import ensure_loaded_cached
                return ensure_loaded_cached()

            def _done(_result):
                self._store_metadata_warming = False
                logger.debug("Preload: cached store metadata warmed")

            def _error(message):
                self._store_metadata_warming = False
                logger.debug("Preload: store data preload failed: %s", message)

            self._run_async(_do, on_done=_done, on_error=_error)

        QTimer.singleShot(3500, _start)

    # ── helpers ──────────────────────────────────────────────────

    def _run_async(self, func, *args, on_done=None, on_error=None, **kwargs):
        """Spawn a disposable QThread worker without blocking the GUI.

        Cleanup used to call ``thread.wait()`` from the result callback and
        retained both QObject instances indefinitely on some error paths.
        Qt's normal quit/deleteLater lifecycle is non-blocking and makes each
        task collectible as soon as its event loop exits.
        """
        thread = QThread()
        worker = _Worker(func, *args, **kwargs)
        worker.moveToThread(thread)

        def _forget_refs():
            try:
                self._workers.remove(worker)
            except ValueError:
                pass
            try:
                self._threads.remove(thread)
            except ValueError:
                pass

        def _on_done(result):
            if on_done:
                on_done(result)

        def _on_error(msg):
            if on_error:
                on_error(msg)
            else:
                self.task_finished.emit(json.dumps({
                    "task": "unknown", "success": False, "message": msg
                }))

        worker.finished.connect(_on_done)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(_on_error)
        worker.error.connect(thread.quit)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(_forget_refs)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)
        self._workers.append(worker)
        self._threads.append(thread)
        thread.start()
        return thread

    def _emit_task_result(self, task_name, success, message="", **extra):
        data = {"task": task_name, "success": success, "message": message}
        data.update(extra)
        self.task_finished.emit(json.dumps(data))

    def _track_download(self, app_id, game_name, success):
        try:
            if not game_name or game_name == f"App {app_id}":
                from sff.game_list_fallback import search_name_fallback
                fallback_name = search_name_fallback(app_id)
                if fallback_name:
                    game_name = fallback_name
            if hasattr(self._ui, 'download_manager') and self._ui.download_manager:
                dl_id = self._ui.download_manager.track_external(
                    app_id=str(app_id),
                    game_name=str(game_name),
                )
                self._ui.download_manager.complete_external(dl_id, success=success)
        except Exception:
            pass

    def _unlock_steam_readonly(self):
        if sys.platform != "win32":
            return
        try:
            from sff.core.storage.vdf import get_steam_libs
            def _unlock(folder):
                try:
                    import subprocess
                    subprocess.run(["attrib", "-r", str(folder)],
                                   capture_output=True, timeout=5, shell=True)
                except Exception:
                    pass
            if self._steam_path:
                _unlock(self._steam_path)
            for lib in get_steam_libs(self._steam_path) if self._steam_path else []:
                _unlock(lib)
        except Exception:
            pass

    @pyqtSlot()
    def signal_ready(self):
        return _bridge_signal_ready(self)
    @pyqtSlot()
    def window_minimize(self):
        return _bridge_window_minimize(self)
    @pyqtSlot()
    def window_maximize(self):
        return _bridge_window_maximize(self)
    @pyqtSlot(result=str)
    def window_is_maximized(self):
        return _bridge_window_is_maximized(self)
    @pyqtSlot()
    def window_close(self):
        return _bridge_window_close(self)
    @pyqtSlot()
    def toggle_ui(self):
        return _bridge_toggle_ui(self)
    def _maybe_auto_contribute_provider(self):
        try:
            from sff.core.storage.settings import get_setting
            from sff.core.structs import Settings
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
        except Exception:
            return

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

    @pyqtSlot(str)
    def validate_game_files(self, app_id):
        return _bridge_validate_game_files(self, app_id)
    def _auto_update_was_registered(self, app_id) -> bool:
        try:
            from sff.game.auto_update_defaults import steam_game_has_pins

            return steam_game_has_pins(self._steam_path, app_id)
        except Exception:
            return False

    def _apply_auto_update_default(self, app_id, was_registered=False):
        if sys.platform != "win32":
            return
        try:
            from sff.game.auto_update_defaults import apply_new_game_update_default

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

    def _is_hubcap_disabled(self):
        try:
            from sff.core.storage.settings import get_setting
            from sff.core.structs import Settings
            return get_setting(Settings.HUBCAP_DISABLED) is True
        except Exception:
            return False

    def _get_store_client(self):
        if self._store_client is None and not self._hubcap_unavailable:
            if not self._api_key:
                try:
                    from sff.core.storage.settings import get_setting
                    from sff.core.structs import Settings
                    key = get_setting(Settings.HUBCAP_KEY)
                    if key and isinstance(key, str) and key.strip():
                        self._api_key = key.strip()
                except Exception:
                    pass
            if self._api_key:
                from sff.network.store_browser import StoreApiClient
                self._store_client = StoreApiClient(self._api_key)
        return self._store_client if not self._hubcap_unavailable else None

    def _check_hubcap_key(self):
        if not self._hubcap_unavailable:
            return
        try:
            from sff.core.storage.settings import get_setting
            from sff.core.structs import Settings
            key = get_setting(Settings.HUBCAP_KEY)
            if key and isinstance(key, str) and key.strip():
                self._api_key = key.strip()
                self._store_client = None
                self._hubcap_unavailable = False
                logger.debug("Hubcap key detected, re-enabling store client")
        except Exception:
            pass

    # ── ASYNC slots — dispatch to QThread ────────────────────────

    @pyqtSlot()
    def refresh_store_metadata(self):
        return _bridge_refresh_store_metadata(self)
    @pyqtSlot()
    def warm_store_metadata(self):
        return _bridge_warm_store_metadata(self)
    @pyqtSlot(str, int, int, str, str)
    @pyqtSlot(str, int, int, str, str, str)
    def search_games(self, query, offset, per_page, sort_by='updated', tag='', request_id=''):
        return _bridge_search_games(self, query, offset, per_page, sort_by, tag, request_id)
    @pyqtSlot(str, bool)
    def fetch_depot_history(self, app_id, force_refresh):
        return _bridge_fetch_depot_history(self, app_id, force_refresh)
    @pyqtSlot(str)
    def download_game_fastest(self, app_id):
        return _bridge_download_game_fastest(self, app_id)
    @pyqtSlot(str, str, str, str, str, str, str)
    @pyqtSlot(str, str, str, str, str, str)
    @pyqtSlot(str, str, str, str, str)
    @pyqtSlot(str, str, str, str)
    @pyqtSlot(str, str, str)
    def download_game_with_source(self, app_id, source, request_update='0', lua_path='', manifest_folder='', branch='', file_type=''):
        return _bridge_download_game_with_source(self, app_id, source, request_update, lua_path, manifest_folder, branch, file_type)
    def _run_local_import(self, app_id, lua_path, manifest_folder=''):
        """Import a local Lua/archive without any provider API calls.
        Extracts lua + manifests, installs to Steam, writes ACF, registers library entry."""
        try:
            from pathlib import Path as _Path
            from sff.lua.manager import parse_lua_contents
            from sff.steam_tools_compat import install_lua_to_steam
            from sff.lua.writer import ACFWriter, ConfigVDFWriter
            from sff.core.storage.vdf import ensure_library_has_app
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
                from sff.core.utils import manifests_staging_dir
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
            elif sys.platform == "linux":
                if hasattr(self._ui, "sls_man") and self._ui.sls_man:
                    self._ui.sls_man.add_ids(parsed)
                    try:
                        from sff.linux.slssteam import detect_steam_type, patch_slssteam_config
                        patch_slssteam_config(detect_steam_type(), lambda _: None)
                    except Exception:
                        pass

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
            from sff.core.storage.vdf import ensure_library_has_app
            from sff.registry_access import set_stats_and_achievements
            from sff.core.structs import LuaEndpoint

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
            elif source == "depotbox":
                selected_source = LuaEndpoint.DEPOTBOX
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

            # Step 9: skip manifest download — Lua + depotcache already seeded.
            # ManifestDownloader would trigger a 20-45s steam_client login that
            # freezes the UI. The acf_writer + ensure_library_has_app above
            # already registered everything Steam needs.

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
            from sff.core.structs import MainReturnCode

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
            from sff.downloads.depot_downloader import get_ddmod_dll, run_download
            from sff.downloads.dotnet_utils import ensure_dotnet_9, find_dotnet
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
                try:
                    from sff.linux.slssteam import detect_steam_type, patch_slssteam_config
                    patch_slssteam_config(detect_steam_type(), lambda _: None)
                except Exception:
                    pass
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
        return _bridge_download_dlc_oureveryday(self, dlc_appid, parent_appid)
    @pyqtSlot(str, str, str)
    def download_game_version(self, app_id, manifest_override_json, source='oureveryday'):
        return _bridge_download_game_version(self, app_id, manifest_override_json, source)
    @pyqtSlot(str, str, str)
    def download_game_version_native(self, app_id, manifest_override_json, source='oureveryday'):
        return _bridge_download_game_version_native(self, app_id, manifest_override_json, source)
    @pyqtSlot(str)
    def dlc_check_get_list(self, app_id):
        return _bridge_dlc_check_get_list(self, app_id)
    @pyqtSlot(str, str)
    def run_game_action(self, app_id, action):
        return _bridge_run_game_action(self, app_id, action)
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
            from sff.game.game_specific import ACFInfo
            from sff.core.storage.vdf import get_steam_libs, vdf_load
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
        return _bridge_fix_game(self, config_json)
    @pyqtSlot(str)
    def revert_game(self, game_path):
        return _bridge_revert_game(self, game_path)
    @pyqtSlot(str)
    def generate_gbe_token(self, config_json):
        return _bridge_generate_gbe_token(self, config_json)
    @pyqtSlot(str, str)
    def scan_cloud_games(self, steam_path, steam32_id):
        return _bridge_scan_cloud_games(self, steam_path, steam32_id)
    @pyqtSlot(str)
    def backup_cloud_save(self, config_json):
        return _bridge_backup_cloud_save(self, config_json)
    @pyqtSlot(str)
    def restore_cloud_save(self, config_json):
        return _bridge_restore_cloud_save(self, config_json)
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
        from sff.core.utils import root_folder
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
        return _bridge_rclone_backup_save(self, config_json)
    @pyqtSlot(str)
    def rclone_list_remotes(self, rclone_exe_json):
        return _bridge_rclone_list_remotes(self, rclone_exe_json)
    @pyqtSlot(str)
    def rclone_test_remote(self, config_json):
        return _bridge_rclone_test_remote(self, config_json)
    @pyqtSlot(str)
    def rclone_open_config(self, rclone_exe_json):
        return _bridge_rclone_open_config(self, rclone_exe_json)
    @pyqtSlot(str)
    def open_workshop(self, app_id):
        """Workshop browser removed."""
        self._emit_task_result("workshop", False, "Workshop Browser has been removed.")

    @pyqtSlot(str)
    def download_workshop_item(self, params_json):
        """Workshop item download removed."""
        self._emit_task_result("workshop_download", False, "Workshop item download has been removed.")

    @pyqtSlot(str)
    def workshop_auto_import(self, app_id):
        """Workshop auto-import removed."""
        self._emit_task_result("workshop_auto_import", False, "Workshop auto-import has been removed.")

    @pyqtSlot(str)
    def workshop_bypass_download(self, params_json):
        """Workshop bypass download removed."""
        self._emit_task_result("workshop_bypass", False, "Workshop bypass download has been removed.")

    @pyqtSlot(str)
    def check_game_update(self, app_id):
        return _bridge_check_game_update(self, app_id)
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
            from sff.core.storage.settings import get_setting
            from sff.core.structs import Settings
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
        return _bridge_set_game_update_override(self, app_id, enabled)
    @pyqtSlot(result=str)
    def let_updates_list_games(self):
        return _bridge_let_updates_list_games(self)
    @pyqtSlot(bool, result=str)
    def let_updates_set_helper(self, enabled):
        return _bridge_let_updates_set_helper(self, enabled)
    @pyqtSlot(str, result=str)
    def let_updates_apply(self, payload_json):
        return _bridge_let_updates_apply(self, payload_json)
    @pyqtSlot(str, result=str)
    def let_updates_add_game(self, app_id):
        return _bridge_let_updates_add_game(self, app_id)
    @pyqtSlot(str, result=bool)
    def get_game_update_override(self, app_id):
        return _bridge_get_game_update_override(self, app_id)
    @pyqtSlot(str, bool)
    def set_game_update_check(self, app_id, enabled):
        return _bridge_set_game_update_check(self, app_id, enabled)
    @pyqtSlot(str, result=str)
    def get_game_update_state(self, app_id):
        return _bridge_get_game_update_state(self, app_id)
    @pyqtSlot(str, result=str)
    def get_game_branches(self, app_id):
        return _bridge_get_game_branches(self, app_id)
    @pyqtSlot(str, result=str)
    def refresh_game_branches(self, app_id):
        return _bridge_refresh_game_branches(self, app_id)
    def _fetch_branches(self, app_id, force_refresh=False):
        try:
            from sff.network.steam_client import create_provider_for_current_thread
            if force_refresh:
                from sff.core.cache import get_cache
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
        return _bridge_ryuu_request_branch(self, app_id, branch)
    @pyqtSlot(str)
    def lure_fix_acf(self, app_id):
        return _bridge_lure_fix_acf(self, app_id)
    @pyqtSlot()
    def restart_steam(self):
        return _bridge_restart_steam(self)
    @pyqtSlot()
    def open_log_window(self):
        return _bridge_open_log_window(self)
    @pyqtSlot(str)
    def copy_to_clipboard(self, text):
        return _bridge_copy_to_clipboard(self, text)
    @pyqtSlot(result=str)
    def browse_game_folder(self):
        return _bridge_browse_game_folder(self)
    @pyqtSlot(str, str, str)
    @pyqtSlot(str, str, str, str)
    def run_game_action_outside(self, game_path, game_name_or_app_id, app_id_or_action, action=None):
        return _bridge_run_game_action_outside(self, game_path, game_name_or_app_id, app_id_or_action, action)
    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def install_lumacore(self, steam_path_str, variant=""):
        return _bridge_install_lumacore(self, steam_path_str, variant)
    @pyqtSlot(result=str)
    def steam_updates_get_state(self):
        return _bridge_steam_updates_get_state(self)
    @pyqtSlot(str, result=str)
    def steam_updates_set_state(self, action):
        return _bridge_steam_updates_set_state(self, action)
    @pyqtSlot(str, result=str)
    def lumacore_check_update(self, _arg=""):
        return _bridge_lumacore_check_update(self, _arg)
    @pyqtSlot()
    def lumacore_deactivate(self):
        return _bridge_lumacore_deactivate(self)
    @pyqtSlot(str)
    def toggle_online_fix(self, app_id):
        return _bridge_toggle_online_fix(self, app_id)
    @pyqtSlot(str, result=str)
    def get_launch_option_status(self, app_id):
        return _bridge_get_launch_option_status(self, app_id)
    @pyqtSlot(result=str)
    def get_applist_games(self):
        return _bridge_get_applist_games(self)
    @pyqtSlot(result=str)
    def get_platform(self):
        return _bridge_get_platform(self)
    @pyqtSlot(result=str)
    def get_app_version(self):
        return _bridge_get_app_version(self)
    @pyqtSlot(str, result=str)
    def app_update_check(self, _arg=""):
        return _bridge_app_update_check(self, _arg)
    @pyqtSlot(str, result=str)
    def get_disk_usage(self, path):
        return _bridge_get_disk_usage(self, path)
    @pyqtSlot(str)
    def connect_store(self, api_key):
        return _bridge_connect_store(self, api_key)
    @pyqtSlot()
    def store_disconnect(self):
        return _bridge_store_disconnect(self)
    @pyqtSlot(str)
    def save_ryuu_key(self, key):
        return _bridge_save_ryuu_key(self, key)
    @pyqtSlot()
    def test_ryuu_key(self):
        return _bridge_test_ryuu_key(self)
    @pyqtSlot()
    def test_ryuu_api_key(self):
        return _bridge_test_ryuu_api_key(self)
    @pyqtSlot(result=str)
    def get_stored_api_key(self):
        return _bridge_get_stored_api_key(self)
    @pyqtSlot(str)
    def open_url(self, url):
        return _bridge_open_url(self, url)
    @pyqtSlot(str)
    def launch_game(self, app_id):
        return _bridge_launch_game(self, app_id)
    @pyqtSlot(str, str)
    def set_setting(self, key, value):
        return _bridge_set_setting(self, key, value)
    @pyqtSlot(str, result=str)
    def get_setting(self, key):
        return _bridge_get_setting(self, key)
    @pyqtSlot(result=str)
    def provider_contribute_preview(self):
        return _bridge_provider_contribute_preview(self)
    @pyqtSlot(str)
    def provider_contribute_submit(self, mode="manual"):
        return _bridge_provider_contribute_submit(self, mode)
    @pyqtSlot()
    def provider_reset_submitted(self):
        return _bridge_provider_reset_submitted(self)
    @pyqtSlot()
    def provider_update_now(self):
        return _bridge_provider_update_now(self)
    @pyqtSlot(result=str)
    def get_provider_cache_status(self):
        return _bridge_get_provider_cache_status(self)
    @pyqtSlot()
    def linux_setup_now(self):
        return _bridge_linux_setup_now(self)
    @pyqtSlot()
    def fix_slssteam_hash(self):
        return _bridge_fix_slssteam_hash(self)
    @pyqtSlot(str, result=str)
    def get_webui_translations(self, lang):
        return _bridge_get_webui_translations(self, lang)
    @pyqtSlot(result=str)
    def get_steam_libraries(self):
        return _bridge_get_steam_libraries(self)
    @pyqtSlot(str)
    def set_active_library(self, path):
        return _bridge_set_active_library(self, path)
    @pyqtSlot(result=str)
    def browse_ddmod_download_folder(self):
        return _bridge_browse_ddmod_download_folder(self)
    @pyqtSlot(str, result=str)
    def browse_steam_path(self, _unused=""):
        return _bridge_browse_steam_path(self, _unused)
    @pyqtSlot(result=str)
    def open_file_dialog(self):
        return _bridge_open_file_dialog(self)
    @pyqtSlot(result=str)
    def open_archive_dialog(self):
        return _bridge_open_archive_dialog(self)
    @pyqtSlot(result=str)
    def open_exe_file_dialog(self):
        return _bridge_open_exe_file_dialog(self)
    @pyqtSlot(result=str)
    def browse_image_file(self):
        return _bridge_browse_image_file(self)
    @pyqtSlot(result=str)
    def browse_custom_background_file(self):
        return _bridge_browse_custom_background_file(self)
    @pyqtSlot(result=str)
    def export_settings_file(self):
        return _bridge_export_settings_file(self)
    @pyqtSlot(result=str)
    def import_settings_file(self):
        return _bridge_import_settings_file(self)
    @pyqtSlot(result=str)
    def import_depot_manifest_html(self):
        return _bridge_import_depot_manifest_html(self)
    @pyqtSlot(str, result=str)
    def set_custom_background(self, source_path):
        return _bridge_set_custom_background(self, source_path)
    @pyqtSlot(result=str)
    def clear_custom_background(self):
        return _bridge_clear_custom_background(self)
    @pyqtSlot(result=str)
    def open_lua_file_dialog(self):
        return _bridge_open_lua_file_dialog(self)
    @pyqtSlot(result=str)
    def open_manifest_folder_dialog(self):
        return _bridge_open_manifest_folder_dialog(self)
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
        return _bridge_open_folder_scan(self)
    @pyqtSlot(str)
    def enqueue_dropped_files(self, files_json):
        return _bridge_enqueue_dropped_files(self, files_json)
    @pyqtSlot(str)
    def enqueue_dropped_blobs(self, blobs_json):
        return _bridge_enqueue_dropped_blobs(self, blobs_json)
    @pyqtSlot()
    def run_bulk_import(self):
        return _bridge_run_bulk_import(self)
    @pyqtSlot()
    def cancel_bulk_import(self):
        return _bridge_cancel_bulk_import(self)
    def _maybe_drain_queue(self, queue):
        """Honor BULK_IMPORT_MODE: drain immediately when set to
        `process_immediately` (the default), or wait for an explicit
        `run_bulk_import` call when set to `collect_then_confirm`.
        """
        try:
            from sff.core.storage.settings import get_setting
            from sff.core.structs import Settings as _Settings

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
        return _bridge_get_recent_lua_files(self)
    @pyqtSlot(str, str, str, str, str)
    @pyqtSlot(str, str, str, str, str, str, str)
    def download_game_ddmod(self, app_id, source, lua_path, manifest_folder='', target_os='', branch='', file_type=''):
        return _bridge_download_game_ddmod(self, app_id, source, lua_path, manifest_folder, target_os, branch, file_type)
    @pyqtSlot(str, str, str)
    def import_local_lua(self, app_id, lua_path, manifest_folder=''):
        return _bridge_import_local_lua(self, app_id, lua_path, manifest_folder)
    @pyqtSlot(result=str)
    def get_games_file_info(self):
        return _bridge_get_games_file_info(self)
    @pyqtSlot(result=str)
    def get_storage_paths(self):
        return _bridge_get_storage_paths(self)
    @pyqtSlot()
    def update_games_file(self):
        return _bridge_update_games_file(self)
    @pyqtSlot()
    def update_store_lists(self):
        return _bridge_update_store_lists(self)
    @pyqtSlot(str, result=str)
    def search_games_file(self, query):
        return _bridge_search_games_file(self, query)
    @pyqtSlot(result=str)
    def get_avatar_base64(self):
        return _bridge_get_avatar_base64(self)
    @pyqtSlot(str, result=str)
    def set_global_avatar(self, source_path):
        return _bridge_set_global_avatar(self, source_path)
    @pyqtSlot(result=str)
    def _scan_installed_games(self):
        return _bridge__scan_installed_games(self)
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
        return _bridge_get_fix_game_list(self)
    @pyqtSlot(str, result=str)
    def extract_vdf_keys(self, vdf_path):
        return _bridge_extract_vdf_keys(self, vdf_path)
    @pyqtSlot()
    def toggle_music(self):
        return _bridge_toggle_music(self)
    @pyqtSlot(result=str)
    def get_gse_identity(self):
        return _bridge_get_gse_identity(self)
    @pyqtSlot(result=str)
    def get_all_settings(self):
        return _bridge_get_all_settings(self)
    @pyqtSlot(result=str)
    def get_game_list(self):
        return _bridge_get_game_list(self)
    @pyqtSlot(str)
    def fetch_library_images(self, app_ids_json):
        return _bridge_fetch_library_images(self, app_ids_json)
    @pyqtSlot()
    def load_library(self):
        return _bridge_load_library(self)
    @pyqtSlot()
    def refresh_library(self):
        return _bridge_refresh_library(self)
    @pyqtSlot(str, str, str)
    def delete_game(self, app_id, game_path, mode):
        return _bridge_delete_game(self, app_id, game_path, mode)
    @pyqtSlot()
    def gdrive_authorize(self):
        return _bridge_gdrive_authorize(self)
    @pyqtSlot(result=str)
    def gdrive_status(self):
        return _bridge_gdrive_status(self)
    @pyqtSlot(result=str)
    def get_custom_save_paths(self):
        return _bridge_get_custom_save_paths(self)
    @pyqtSlot(str, str, result=str)
    def set_custom_save_path(self, app_id, path):
        return _bridge_set_custom_save_path(self, app_id, path)
    @pyqtSlot(str)
    def scan_all_save_locations(self, config_json):
        return _bridge_scan_all_save_locations(self, config_json)
    @pyqtSlot(str)
    def backup_all_save_locations(self, config_json):
        return _bridge_backup_all_save_locations(self, config_json)
    @pyqtSlot(str)
    def scan_backup_root(self, config_json):
        return _bridge_scan_backup_root(self, config_json)
    @pyqtSlot(str)
    def restore_save_location(self, game_entry_json):
        return _bridge_restore_save_location(self, game_entry_json)
    @pyqtSlot(result=str)
    def dump_achievement_diagnostic(self):
        return _bridge_dump_achievement_diagnostic(self)
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


def _store_all_tokens_match(query_norm, name_norm, _depth=0):
    if _depth > 5:
        return False
    tokens = _store_words(query_norm)
    if not tokens:
        return True
    for token in tokens:
        if _store_token_match(token, name_norm):
            continue
        alts = _ALIAS_EXPANSIONS.get(token)
        if alts and any(_store_all_tokens_match(_normalize_for_search(alt), name_norm, _depth + 1) for alt in alts):
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
    import threading as _thr

    _now = _time.time()
    if _STEAM_APPLIST_CACHE is not None and (_now - _STEAM_APPLIST_CACHE_TIME) < 86400:
        return _STEAM_APPLIST_CACHE

    _lock = getattr(_load_steam_applist, '_lock', None)
    if _lock is None:
        _lock = _thr.Lock()
        _load_steam_applist._lock = _lock

    with _lock:
        if _STEAM_APPLIST_CACHE is not None and (_time.time() - _STEAM_APPLIST_CACHE_TIME) < 86400:
            return _STEAM_APPLIST_CACHE
        if getattr(_load_steam_applist, '_building', False):
            while getattr(_load_steam_applist, '_building', False):
                _lock.release()
                _time.sleep(0.05)
                _lock.acquire()
            if _STEAM_APPLIST_CACHE is not None and (_time.time() - _STEAM_APPLIST_CACHE_TIME) < 86400:
                return _STEAM_APPLIST_CACHE
        _load_steam_applist._building = True

    from sff.core.utils import root_folder

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
        from sff.core.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings
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
        _load_steam_applist._building = False
        return _result

    _STEAM_APPLIST_CACHE = []
    _STEAM_APPLIST_CACHE_TIME = _now
    _load_steam_applist._building = False
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
