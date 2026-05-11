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
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)


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


class WebBridge(QObject):
    """QObject subclass registered via QWebChannel.
    JS accesses this as ``channel.objects.bridge``.
    """

    # --- Signals (Python → JS) ---
    search_results = pyqtSignal(str)
    depot_history_results = pyqtSignal(str)
    download_progress = pyqtSignal(str)
    task_finished = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self, ui, steam_path, parent=None):
        super().__init__(parent)
        self._ui = ui
        self._steam_path = Path(steam_path) if steam_path else None
        self._active_library = None
        self._api_key = None
        self._store_client = None
        self._workers = []  # prevent GC of running workers

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
            if on_done:
                on_done(result)

        def _on_error(msg):
            thread.quit()
            thread.wait()
            if worker in self._workers:
                self._workers.remove(worker)
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
        thread.start()

    def _emit_task_result(self, task_name, success, message="", **extra):
        data = {"task": task_name, "success": success, "message": message}
        data.update(extra)
        self.task_finished.emit(json.dumps(data))

    def _get_store_client(self):
        if self._store_client is None and self._api_key:
            from sff.store_browser import StoreApiClient
            self._store_client = StoreApiClient(self._api_key)
        return self._store_client

    # ── ASYNC slots — dispatch to QThread ────────────────────────

    @pyqtSlot(str, int, int, str)
    def search_games(self, query, offset, per_page, sort_by='updated'):
        """Search the Hubcap store. Falls back to Steam catalog on failure. Emits search_results signal."""
        def _do():
            client = self._get_store_client()
            if client:
                try:
                    if query:
                        # Fetch large batch via /library?search= for client-side pagination
                        all_games = client.get_library(limit=200, offset=0, search=query).games
                        q_words = query.lower().split()
                        # Name keyword + word filter (all query words must appear in name)
                        filtered = []
                        for g in all_games:
                            name_lc = g.name.lower()
                            if any(kw in name_lc for kw in _NONGAME_NAME_KW):
                                continue
                            if q_words and not all(w in name_lc for w in q_words):
                                continue
                            filtered.append(g)
                        # Fetch images + types for ALL filtered items before pagination
                        all_ids = [g.app_id for g in filtered]
                        image_urls, type_map = _fetch_steam_image_urls(all_ids)
                        # Type filter — must happen before total so pagination is accurate
                        final = [g for g in filtered if type_map.get(g.app_id) not in _NON_GAME_TYPES]
                        total = len(final)
                        page_games = final[offset: offset + per_page]
                        games = [{
                            "app_id": g.app_id,
                            "name": g.name,
                            "last_updated": g.last_updated,
                            "status": g.status,
                            "size": g.size,
                            "image_url": image_urls.get(g.app_id),
                        } for g in page_games]
                        return {"games": games, "total": total, "fallback": False}
                    else:
                        # Browse: /library endpoint with server-side pagination
                        result = client.get_library(limit=per_page, offset=offset, sort_by=sort_by or 'updated')
                        app_ids = [g.app_id for g in result.games]
                        image_urls, type_map = _fetch_steam_image_urls(app_ids)
                        games = []
                        for g in result.games:
                            if type_map.get(g.app_id) in _NON_GAME_TYPES:
                                continue
                            name_lc = g.name.lower()
                            if any(kw in name_lc for kw in _NONGAME_NAME_KW):
                                continue
                            games.append({
                                "app_id": g.app_id,
                                "name": g.name,
                                "last_updated": g.last_updated,
                                "status": g.status,
                                "size": g.size,
                                "image_url": image_urls.get(g.app_id),
                            })
                        return {"games": games, "total": result.total, "fallback": False}
                except Exception as e:
                    logger.warning("Hubcap search failed, falling back to Steam catalog: %s", e)
            return _search_steam_catalog(query, offset, per_page)

        def _on_done(data):
            if data:
                self.search_results.emit(json.dumps(data))
            else:
                self.search_results.emit(json.dumps({"games": [], "total": 0, "fallback": True}))

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
            self._emit_task_result(
                "download_fastest",
                success,
                f"Download {'completed' if success else 'failed'} for App {app_id}",
                app_id=app_id,
            )

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, str, str)
    def download_game_with_source(self, app_id, source, request_update='0'):
        """Fastest download with explicit source choice ('hubcap' or 'oureveryday').
        Emits download_progress + task_finished signals."""
        def _do():
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Starting", "progress": 0
            }))
            if sys.platform == "win32":
                return self._run_windows_fastest(app_id, source=source, request_update=(request_update == '1'))
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

    def _run_windows_fastest(self, app_id, source='', request_update=False):
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
            lua_path = download_lua_direct(
                dest=steam_path / "config",
                app_id=app_id,
                source=selected_source,
                steam_path=steam_path,
                request_update=request_update,
            )
            if not lua_path:
                return False

            saved_lua = Path.cwd() / "saved_lua"
            saved_lua.mkdir(exist_ok=True)
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

            # Step 3: set stats and achievements (Windows only)
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Setting up achievements", "progress": 30
            }))
            try:
                set_stats_and_achievements(app_id)
            except Exception as e:
                logger.warning("set_stats_and_achievements failed: %s", e)

            # Step 4: add to AppList
            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Adding to AppList", "progress": 40
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
        """Auto-selects latest manifests, wraps process_from_store()."""
        try:
            from sff.manifest.depot_history import get_depots_for_app

            # Auto-select latest manifest for each depot
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

            self._ui.process_from_store(
                app_id=app_id,
                manifest_override=manifest_override,
                use_hubcap=bool(self._api_key),
            )

            self.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Complete", "progress": 100
            }))
            return True

        except Exception as e:
            logger.exception("Linux fastest download failed: %s", e)
            return False

    @pyqtSlot(str, str)
    def download_game_version(self, app_id, manifest_override_json):
        """Download specific version via process_from_store().
        Emits download_progress + task_finished signals."""
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

            if self._active_library:
                # Pre-set library to avoid prompt
                pass  # gui_prompts.py will handle if needed

            self._ui.process_from_store(
                app_id=app_id,
                manifest_override=manifest_override,
                use_hubcap=bool(self._api_key),
            )

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

        self._run_async(_do, on_done=_on_done)

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
                parent._run_steam_auto_with_acf(acf)
            return

        def _do():
            from sff.structs import MainMenu

            # Non-game-specific actions — call ui methods directly
            non_game_actions = {
                "download_games": lambda: self._ui.process_lua_full(),
                "download_manifests": lambda: self._ui.process_lua_minimal(),
                "recent_lua": lambda: self._ui.recent_files_menu(),
                "update_manifests": lambda: self._ui.update_all_manifests(),
                "applist_menu": lambda: self._ui.applist_menu(),
                "offline_fix": lambda: self._ui.offline_fix_menu(),
                "remove_game": lambda: self._ui.remove_game_menu(),
                "context_menu": lambda: self._ui.manage_context_menu(),
                "check_updates": lambda: self._ui.check_updates(self._ui.os_type),
                "scan_library": lambda: self._ui.scan_library_menu(),
                "analytics": lambda: self._ui.analytics_dashboard_menu(),
            }

            if action in non_game_actions:
                try:
                    non_game_actions[action]()
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
                self._ui.run_game_action_with_selection(menu_choice, acf)
                return None
            except Exception as e:
                return str(e)

        def _on_done(error_msg):
            if error_msg:
                self._emit_task_result(action, False, str(error_msg))
            else:
                self._emit_task_result(action, True, f"Action '{action}' completed")

        self._run_async(_do, on_done=_on_done)

    def _resolve_acf(self, app_id):
        """Find ACFInfo for a given app_id by scanning Steam libraries."""
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
                from sff.gui.fix_game_tab import FixGameService
                FixGameService.revert(game_path)
                return True
            except Exception as e:
                return str(e)

        def _on_done(result):
            if result is True:
                self._emit_task_result("revert_game", True, "Changes reverted")
            else:
                self._emit_task_result("revert_game", False, str(result))

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
        """
        from sff.utils import root_folder
        ext = ".exe" if sys.platform == "win32" else ""
        rel = Path("third_party") / tool / f"{tool}{ext}"
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
                    capture_output=True, text=True, timeout=300, **_no_win,
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
                    capture_output=True, text=True, timeout=15, **_no_win,
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
                    capture_output=True, text=True, timeout=20, **_no_win,
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
                out_dir = Path.cwd() / "downloaded_files" / "workshop" / item_id
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
                from sff.lua.manager import LuaManager, LuaChoice
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
                    return {
                        "found": True,
                        "up_to_date": False,
                        "installed_buildid": installed_buildid,
                        "cm_buildid": cm_buildid,
                        "error": f"No saved .lua for App ID {app_id} — run Download Games first",
                    }

                parsed_lua = lua_manager.fetch_lua(LuaChoice.ADD_LUA, saved_lua_path)
                if parsed_lua is None:
                    return {
                        "found": True,
                        "up_to_date": False,
                        "error": "Failed to parse saved .lua file",
                    }

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

                return {
                    "found": True,
                    "up_to_date": False,
                    "updated": True,
                    "installed_buildid": installed_buildid,
                    "cm_buildid": cm_buildid,
                    "manifests_updated": len(new_manifest_map),
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
                msg = f"Updated to build {result.get('cm_buildid', '')}"
            elif result.get("error"):
                msg = result["error"]
            self._emit_task_result("update_check", success, msg, **{
                k: v for k, v in result.items() if k not in ("error",)
            })

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
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
            self._emit_task_result("lure_fix", bool(result.get("success")), msg, **{
                k: v for k, v in result.items() if k != "error"
            })

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def restart_steam(self):
        """Restart or launch Steam."""
        def _do():
            if sys.platform == "win32":
                import time
                import subprocess
                from sff.processes import SteamProcess, is_proc_running

                if not self._steam_path:
                    return (False, "Steam path not set")

                applist_folder = None
                if hasattr(self._ui, 'app_list_man') and self._ui.app_list_man:
                    applist_folder = self._ui.app_list_man.applist_folder
                if not applist_folder:
                    return (False, "AppList folder not found")

                steam_proc = SteamProcess(self._steam_path, applist_folder)

                # Kill Steam if running
                if is_proc_running(steam_proc.exe_name):
                    print("Killing Steam...", end="", flush=True)
                    steam_proc.kill()
                    max_wait = 10
                    waited = 0
                    while is_proc_running(steam_proc.exe_name) and waited < max_wait:
                        time.sleep(0.5)
                        waited += 0.5
                    if is_proc_running(steam_proc.exe_name):
                        return (False, "Steam did not close in time — try again")
                    print(" Done!")

                # Find injector: prefer DLLInjector.exe, fallback to steam.exe
                injector = steam_proc.injector_dir / "DLLInjector.exe"
                if not injector.exists():
                    injector = self._steam_path / "steam.exe"
                if not injector.exists():
                    return (False, "DLLInjector.exe and steam.exe not found")

                print(f"Launching {injector.name}...")
                try:
                    import ctypes as _ctypes
                    already_admin = bool(_ctypes.windll.shell32.IsUserAnAdmin())
                    if already_admin:
                        subprocess.Popen([str(injector)], cwd=str(self._steam_path))
                        return (True, "Steam launched successfully")
                    # Not admin — request UAC elevation via ShellExecuteW runas
                    ret = _ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", str(injector), None, str(self._steam_path), 1)
                    if ret > 32:
                        return (True, "Steam launched successfully")
                    # Elevation declined/failed — try without elevation as fallback
                    subprocess.Popen([str(injector)], cwd=str(self._steam_path))
                    return (True, "Steam launched (elevation skipped)")
                except Exception as e:
                    return (False, f"Failed to launch: {e}")

            else:
                from sff.linux.steam_process import kill_steam, start_steam
                kill_steam()
                result = start_steam()
                if result == "SUCCESS":
                    return (True, "Steam restarted")
                return (False, f"Steam start failed: {result}")

        def _on_done(result):
            if isinstance(result, tuple):
                success, msg = result
            else:
                success, msg = bool(result), "Steam restarted" if result else "Failed to restart Steam"
            self._emit_task_result("restart_steam", success, msg)

        self._run_async(_do, on_done=_on_done)

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
    def run_game_action_outside(self, game_path, app_id, action):
        """Run a game action against a folder outside the Steam library.
        Builds ACFInfo from the explicit path instead of scanning steamapps."""
        from pathlib import Path as _Path
        from sff.game_specific import ACFInfo

        p = _Path(game_path)
        if not p.is_dir():
            self._emit_task_result(action, False, f"Folder not found: {game_path}")
            return

        acf = ACFInfo(app_id or "0", p)

        if action == "steam_auto":
            from sff.steamauto import get_steamauto_cli_path
            if get_steamauto_cli_path() is None:
                self._emit_task_result("steam_auto", False, "SteamAutoCrack CLI not found")
                return
            parent = self.parent()
            if parent and hasattr(parent, '_run_steam_auto_with_acf'):
                parent._run_steam_auto_with_acf(acf)
            return

        def _do():
            from sff.structs import MainMenu
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
            try:
                self._ui.run_game_action_with_selection(menu_choice, acf)
                return None
            except Exception as e:
                return str(e)

        def _on_done(error_msg):
            if error_msg:
                self._emit_task_result(action, False, str(error_msg))
            else:
                self._emit_task_result(action, True, f"Action '{action}' completed")

        self._run_async(_do, on_done=_on_done)

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
    def auto_gl_setup_action(self, config_json):
        """Extract and configure GreenLuma from a ZIP or RAR archive.
        config_json: {method: 'A'|'B', archive_path: str, steam_exe: str}
        Emits task_finished with task='auto_gl_setup'."""
        def _do():
            import json as _json
            cfg = _json.loads(config_json)
            method = cfg.get("method", "A")
            archive_path = cfg.get("archive_path", "").strip()
            steam_exe = cfg.get("steam_exe", "").strip()
            if not archive_path:
                return (False, "No archive selected.", "")
            if not steam_exe:
                steam_exe = r"C:\Program Files (x86)\Steam\steam.exe"
            from sff.greenluma_setup import auto_gl_setup
            result = auto_gl_setup(method=method, archive_path=archive_path, steam_exe_path=steam_exe)
            return (result["ok"], result["message"], result.get("applist_path", ""))

        def _on_done(result):
            if isinstance(result, tuple) and len(result) >= 2:
                ok, msg = result[0], result[1]
                applist_path = result[2] if len(result) > 2 else ""
                if ok and applist_path:
                    try:
                        from sff.storage.settings import set_setting
                        from sff.structs import Settings
                        set_setting(Settings.APPLIST_FOLDER, applist_path)
                    except Exception:
                        pass
                import json as _json
                self.task_finished.emit(_json.dumps({
                    "task": "auto_gl_setup",
                    "success": bool(ok),
                    "message": msg,
                    "applist_path": applist_path,
                }))
            else:
                import json as _json
                self.task_finished.emit(_json.dumps({"task": "auto_gl_setup", "success": False, "message": "Setup failed"}))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def connect_store(self, api_key):
        """Validates and stores Hubcap API key."""
        from sff.store_browser import StoreApiClient
        self._api_key = api_key
        self._store_client = StoreApiClient(api_key)
        # Save to settings
        from sff.storage.settings import set_setting
        from sff.structs import Settings
        set_setting(Settings.HUBCAP_KEY, api_key)

    @pyqtSlot(result=str)
    def get_stored_api_key(self):
        """Returns saved API key from settings (may be empty)."""
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        key = get_setting(Settings.HUBCAP_KEY)
        if key:
            self._api_key = key
        return key or ""

    @pyqtSlot(result=str)
    def list_profiles(self):
        """Returns JSON array of profile names."""
        from sff.app_injector.applist_profiles import list_profiles
        return json.dumps(list_profiles())

    @pyqtSlot(str)
    def switch_profile(self, name):
        """Switch to a named AppList profile."""
        def _do():
            from sff.app_injector.applist_profiles import switch_profile
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            from pathlib import Path
            if hasattr(self._ui, 'app_list_man') and self._ui.app_list_man:
                folder = self._ui.app_list_man.applist_folder
            else:
                saved = get_setting(Settings.APPLIST_FOLDER)
                if not saved:
                    return False
                folder = Path(saved)
            success, count = switch_profile(name, folder)
            return success

        def _on_done(result):
            self._emit_task_result("switch_profile", bool(result), f"Switched to '{name}'")

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str)
    def save_profile(self, name):
        """Save current AppList as a profile."""
        from sff.app_injector.applist_profiles import save_profile
        if hasattr(self._ui, 'app_list_man') and self._ui.app_list_man:
            ids = [x.app_id for x in self._ui.app_list_man.get_local_ids(sort=True)]
            save_profile(name, ids)

    @pyqtSlot(str)
    def delete_profile(self, name):
        """Delete a profile."""
        from sff.app_injector.applist_profiles import delete_profile
        delete_profile(name)

    @pyqtSlot(str, str)
    def rename_profile(self, old_name, new_name):
        """Rename a profile."""
        from sff.app_injector.applist_profiles import rename_profile
        rename_profile(old_name, new_name)

    @pyqtSlot(str)
    def open_url(self, url):
        """Open a URL in the system default browser."""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))

    @pyqtSlot()
    def clear_applist(self):
        """Delete all numbered .txt files from the GreenLuma AppList folder."""
        def _do():
            if not hasattr(self._ui, 'app_list_man') or not self._ui.app_list_man:
                return -1
            folder = Path(self._ui.app_list_man.applist_folder)
            count = 0
            for f in folder.glob("*.txt"):
                if f.stem.isdigit():
                    f.unlink(missing_ok=True)
                    count += 1
            return count

        def _on_done(count):
            if count == -1:
                self.task_finished.emit(json.dumps({
                    "task": "applist_cleared", "success": False,
                    "message": "AppList manager not available", "count": 0,
                }))
            else:
                self.task_finished.emit(json.dumps({
                    "task": "applist_cleared", "success": True,
                    "message": f"Cleared {count} IDs from AppList", "count": count,
                }))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot()
    def rebuild_applist_from_installed(self):
        """Clear AppList and repopulate with only currently installed Steam games."""
        def _do():
            if not hasattr(self._ui, 'app_list_man') or not self._ui.app_list_man:
                return {"success": False, "message": "AppList manager not available", "count": 0}
            folder = Path(self._ui.app_list_man.applist_folder)
            for f in folder.glob("*.txt"):
                if f.stem.isdigit():
                    f.unlink(missing_ok=True)
            games = json.loads(self.get_installed_games())
            app_ids = [g["app_id"] for g in games if g.get("app_id")]
            for i, app_id in enumerate(app_ids):
                (folder / f"{i}.txt").write_text(str(app_id), encoding="utf-8")
            return {"success": True, "count": len(app_ids)}

        def _on_done(result):
            self.task_finished.emit(json.dumps({
                "task": "applist_rebuilt",
                "success": result.get("success", False),
                "message": result.get("message", f"Rebuilt AppList with {result.get('count', 0)} installed games"),
                "count": result.get("count", 0),
            }))

        self._run_async(_do, on_done=_on_done)

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
                _set(s, value)
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
            "Select GreenLuma Archive",
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
    def get_installed_games(self):
        """Returns JSON array of installed games from ALL Steam library folders."""
        try:
            if not self._steam_path:
                return "[]"
            from sff.storage.vdf import get_steam_libs
            import os
            libs = list(get_steam_libs(self._steam_path))
            # Also scan common Windows drive paths
            if os.name == 'nt':
                from string import ascii_uppercase
                for drive_letter in ascii_uppercase:
                    drive = Path(f"{drive_letter}:/")
                    if not drive.exists():
                        continue
                    for subdir in ("SteamLibrary", "Steam", "Program Files (x86)/Steam",
                                   "Program Files/Steam", "Games/Steam"):
                        candidate = drive / subdir
                        steamapps = candidate / "steamapps"
                        if steamapps.exists() and candidate not in libs:
                            libs.append(candidate)
            games = []
            seen = set()
            for lib in libs:
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
                        # Skip if game folder doesn't exist
                        if installdir:
                            game_path = steamapps / "common" / installdir
                            if not game_path.exists():
                                continue
                        seen.add(app_id)
                        games.append({
                            "app_id": int(app_id) if app_id.isdigit() else 0,
                            "name": name or f"App {app_id}",
                            "installed": True,
                            "path": str(steamapps / "common" / installdir) if installdir else "",
                        })
                    except Exception:
                        continue
            games.sort(key=lambda g: g.get("name", "").lower())
            return json.dumps(games)
        except Exception:
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
            image_urls, _ = _fetch_steam_image_urls(app_ids)
            return image_urls

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
            image_urls, _ = _fetch_steam_image_urls(app_ids)
            for g in games:
                g["image_url"] = image_urls.get(g["app_id"])
            return games

        def _on_done(games):
            self.task_finished.emit(json.dumps({
                "task": "library_loaded",
                "success": True,
                "games": games or [],
            }))

        self._run_async(_do, on_done=_on_done)

    @pyqtSlot(str, str, str)
    def delete_game(self, app_id, game_path, mode):
        """Remove a game from the AppList and optionally delete its files.
        mode='applist' removes from AppList folder + all profiles only.
        mode='full' also deletes the ACF manifest and the game folder from disk.
        """
        def _do():
            import shutil
            app_id_int = int(app_id) if str(app_id).isdigit() else None
            if app_id_int is None:
                return (False, "Invalid App ID")

            removed_from_applist = False

            # --- Remove from AppList folder ---
            if hasattr(self._ui, 'app_list_man') and self._ui.app_list_man:
                folder = Path(self._ui.app_list_man.applist_folder)
                for f in list(folder.glob("*.txt")):
                    if not f.stem.isdigit():
                        continue
                    try:
                        if f.read_text(encoding="utf-8").strip() == str(app_id_int):
                            f.unlink()
                            removed_from_applist = True
                            break
                    except OSError:
                        pass
                if removed_from_applist:
                    remaining = sorted(
                        [f for f in folder.glob("*.txt") if f.stem.isdigit()],
                        key=lambda f: int(f.stem),
                    )
                    for i, f in enumerate(remaining):
                        target = folder / f"{i}.txt"
                        if f != target:
                            f.rename(target)

            # --- Remove from all saved profiles ---
            try:
                from sff.app_injector.applist_profiles import list_profiles, load_profile, save_profile
                for profile_name in list_profiles():
                    ids = load_profile(profile_name)
                    if ids and app_id_int in ids:
                        save_profile(profile_name, [i for i in ids if i != app_id_int])
            except Exception as e:
                logger.warning("delete_game: profile update failed: %s", e)

            if mode != "full":
                return (True, "Removed from AppList")

            # --- Delete game files (mode='full') ---
            files_deleted = False

            # Delete the ACF manifest
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

            # Delete the game folder
            if game_path:
                p = Path(game_path)
                if p.exists() and p.is_dir():
                    try:
                        shutil.rmtree(p, ignore_errors=False)
                        files_deleted = True
                    except Exception as e:
                        logger.warning("delete_game: folder removal failed: %s", e)

            if files_deleted:
                return (True, "Game removed from AppList and deleted from disk")
            return (True, "Removed from AppList (game folder not found or already gone)")

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
                unique_locations = list({e["location"] for e in entries})
                for _loc in unique_locations:
                    subprocess.run(
                        [_rclone_exe, "mkdir",
                         _remote_dest.rstrip("/") + f"/SteaMidraAllSaves/{_loc}"],
                        capture_output=True, timeout=30, **_no_window,
                    )

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
                    capture_output=True, timeout=180, **_no_window,
                )

            elif provider == "gdrive_api":
                import threading
                from concurrent.futures import ThreadPoolExecutor, as_completed
                from sff.google_drive import (
                    get_service, get_backup_root, is_authenticated, get_or_create_folder,
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
                    if _Path(e["source_path"]).exists():
                        valid_entries.append(e)
                    else:
                        failed += 1
                        log_lines.append(
                            f"[SKIP] Source not found: {e.get('label', '?')} ({e.get('source_path', '?')})"
                        )

                folder_cache = {}
                for loc in {e["location"] for e in valid_entries}:
                    loc_id = get_or_create_folder(svc, loc, root_id)
                    if loc_id:
                        folder_cache[(loc, root_id)] = loc_id
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
            ok = restore_save_entry(game_entry, log_func=log_lines.append)
            msg = "Restore complete" if ok else "Restore failed — check log"
            return (ok, msg, log_lines)

        def _on_done(result):
            if isinstance(result, tuple):
                ok, msg, log_lines = result
                self._emit_task_result("restore_save_location", ok, msg, log="\n".join(log_lines))
            else:
                self._emit_task_result("restore_save_location", False, "Restore failed")

        self._run_async(_do, on_done=_on_done)


def _fetch_steam_image_urls(app_ids):
    """Batch-fetch canonical image URLs via Steam IStoreBrowseService/GetItems/v1.

    Returns (images, types) where:
      images: dict mapping appid (int) -> canonical URL string
      types:  dict mapping appid (int) -> Steam app type int
                (1=game, 2=dlc, 3=demo, 13=music, etc.)
    On any network or parse error returns ({}, {}) so callers fall back gracefully.
    """
    if not app_ids:
        return {}, {}
    import json as _json
    import urllib.request as _req
    import urllib.parse as _urlparse
    result = {}
    types = {}
    try:
        payload = {
            "ids": [{"appid": aid} for aid in app_ids],
            "context": {"language": "english", "country_code": "US"},
            "data_request": {"include_assets": True},
        }
        url = (
            "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json="
            + _urlparse.quote(_json.dumps(payload, separators=(",", ":")))
        )
        request = _req.Request(url, headers={"User-Agent": "SteaMidra/5.4.0"})
        with _req.urlopen(request, timeout=5) as resp:
            data = _json.loads(resp.read())
        for item in data.get("response", {}).get("store_items", []):
            appid = item.get("appid")
            header = (item.get("assets") or {}).get("header", "")
            if appid and header:
                result[appid] = (
                    f"https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/{header}"
                )
            if appid:
                types[appid] = int(item.get("type") or 1)
    except Exception as e:
        logger.debug("Steam image batch fetch failed: %s", e)
    return result, types


_STEAM_APPLIST_CACHE = None
_STEAM_APPLIST_CACHE_TIME = 0.0

_NONGAME_NAME_KW = ("soundtrack", "art book", "artbook", " ost", "music pack", "digital artbook")

_NON_GAME_TYPES = frozenset({2, 4, 6, 7, 9, 10, 11, 12, 13, 14})


def _load_steam_applist():
    """Download and cache the full Steam app list (ISteamApps/GetAppList/v2). Refreshes every 24h."""
    global _STEAM_APPLIST_CACHE, _STEAM_APPLIST_CACHE_TIME
    import time
    import urllib.request as _req
    import json as _json
    now = time.time()
    if _STEAM_APPLIST_CACHE is not None and (now - _STEAM_APPLIST_CACHE_TIME) < 86400:
        return _STEAM_APPLIST_CACHE
    try:
        url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/?format=json"
        req = _req.Request(url, headers={"User-Agent": "SteaMidra/5.4.0"})
        with _req.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        apps = data.get("applist", {}).get("apps", [])
        if apps:
            _STEAM_APPLIST_CACHE = apps
            _STEAM_APPLIST_CACHE_TIME = now
            logger.debug("Steam applist loaded: %d apps", len(apps))
            return apps
    except Exception as e:
        logger.debug("Steam applist fetch failed: %s", e)
    return _STEAM_APPLIST_CACHE or []


def _search_steam_catalog(query, offset, per_page):
    """Fallback store search using full Steam public app list when Hubcap is unavailable."""
    apps = _load_steam_applist()
    if not apps:
        return {"games": [], "total": 0, "fallback": True}
    if query:
        q = query.lower()
        apps = [a for a in apps if q in a.get("name", "").lower()]
    total = len(apps)
    page_apps = apps[offset: offset + per_page]
    app_ids = [a["appid"] for a in page_apps if a.get("appid")]
    image_urls, type_map = _fetch_steam_image_urls(app_ids)
    games = []
    for a in page_apps:
        appid = a.get("appid", 0)
        if type_map.get(appid) in _NON_GAME_TYPES:
            continue
        name_lc = a.get("name", f"App {appid}").lower()
        if any(kw in name_lc for kw in _NONGAME_NAME_KW):
            continue
        games.append({
            "app_id": appid,
            "name": a.get("name", f"App {appid}"),
            "last_updated": "",
            "status": "",
            "size": 0,
            "image_url": image_urls.get(appid),
        })
    return {"games": games, "total": total, "fallback": True}


def _format_size(size_bytes):
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
