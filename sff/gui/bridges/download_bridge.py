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
Download-domain bridge functions extracted from web_bridge.py.

All functions accept ``bridge`` as their first argument (the WebBridge instance).
Convert ``self.xxx`` → ``bridge.xxx`` when adapting from the original class methods.

Shared helpers (kept in web_bridge.py): _run_async, _emit_task_result, _maybe_auto_contribute_provider.
"""

import concurrent.futures as _concurrent
import io
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time as _time
from pathlib import Path

from PyQt6.QtCore import QTimer
from sff.linux.acf_writer import create_acf

logger = logging.getLogger(__name__)

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_DDMOD_PCT_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%\s*")


# ── Private helpers used ONLY by download-domain methods ──────────────

def _bridge_auto_update_was_registered(bridge, app_id) -> bool:
    try:
        from sff.game.auto_update_defaults import steam_game_has_pins

        return steam_game_has_pins(bridge._steam_path, app_id)
    except Exception:
        return False


def _bridge_apply_auto_update_default(bridge, app_id, was_registered=False):
    if sys.platform != "win32":
        return
    try:
        from sff.game.auto_update_defaults import apply_new_game_update_default

        result = apply_new_game_update_default(
            bridge._steam_path,
            app_id,
            was_registered=bool(was_registered),
            log=lambda msg: logger.info(msg),
        )
        if result.get("applied"):
            bridge._installed_games_cache = None
    except Exception as exc:
        logger.debug("auto-update default skipped for %s: %s", app_id, exc)


def _bridge_track_download(bridge, app_id, game_name, success):
    try:
        if not game_name or game_name == f"App {app_id}":
            from sff.game_list_fallback import search_name_fallback
            fallback_name = search_name_fallback(app_id)
            if fallback_name:
                game_name = fallback_name
        if hasattr(bridge._ui, 'download_manager') and bridge._ui.download_manager:
            dl_id = bridge._ui.download_manager.track_external(
                app_id=str(app_id),
                game_name=str(game_name),
            )
            bridge._ui.download_manager.complete_external(dl_id, success=success)
    except Exception:
        pass


def _bridge_unlock_steam_readonly(bridge):
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
        if bridge._steam_path:
            _unlock(bridge._steam_path)
        for lib in get_steam_libs(bridge._steam_path) if bridge._steam_path else []:
            _unlock(lib)
    except Exception:
        pass


def _bridge_show_linux_fastest_workflow_notice(bridge, app_id):
    if getattr(bridge, "_linux_fastest_notice_shown", False):
        return
    bridge._linux_fastest_notice_shown = True
    bridge.download_progress.emit(json.dumps({
        "app_id": app_id,
        "status": (
            "ACF and library entry written. Open Steam, find the game, "
            "click Update — SLSSteam pulls the content directly."
        ),
        "progress": -1,
        "info": True,
    }))


# ── Public download-domain functions (were @pyqtSlot methods) ────────

def _bridge_download_game_fastest(bridge, app_id):
    """Platform-aware fastest download (auto-selects source).
    Windows: prompt-free 11-step pipeline mirroring process_lua_full().
    Linux: auto-selects latest manifests, wraps process_from_store().
    Emits download_progress + task_finished signals."""
    if not app_id or not app_id.strip().isdigit():
        bridge._emit_task_result("download_fastest", False, f"Invalid App ID: '{app_id}'")
        return
    def _do():
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Starting", "progress": 0
        }))

        if sys.platform == "win32":
            return _bridge_run_windows_fastest(bridge, app_id)
        else:
            return _bridge_run_linux_fastest(bridge, app_id)

    def _on_done(result):
        success = result is True
        if success:
            QTimer.singleShot(1000, bridge._maybe_auto_contribute_provider)
        bridge._emit_task_result(
            "download_fastest",
            success,
            f"Download {'completed' if success else 'failed'} for App {app_id}",
            app_id=app_id,
        )

    bridge._run_async(_do, on_done=_on_done)


def _bridge_download_game_with_source(bridge, app_id, source, request_update='0', lua_path='', manifest_folder='', branch='', file_type=''):
    """Fastest download with explicit source choice ('hubcap', 'oureveryday', 'ryuu', or 'local').
    Emits download_progress + task_finished signals.
    When source='local', lua_path is required (path to .lua/.zip/.rar/.7z),
    manifest_folder is optional (path to folder with .manifest files)."""
    if not app_id or not app_id.strip().isdigit():
        bridge._emit_task_result("download_fastest", False, f"Invalid App ID: '{app_id}'")
        return
    def _do():
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Starting", "progress": 0
        }))
        # Local source: bypass all API calls, import directly
        if source == "local":
            return _bridge_run_local_import(bridge, app_id, lua_path, manifest_folder)
        if sys.platform == "win32":
            return _bridge_run_windows_fastest(bridge, app_id, source=source, request_update=(request_update == '1'), branch=branch, file_type=file_type)
        else:
            return _bridge_run_linux_fastest(bridge, app_id)

    def _on_done(result):
        success = result is True
        bridge._emit_task_result(
            "download_fastest",
            success,
            f"Download {'completed' if success else 'failed'} for App {app_id}",
            app_id=app_id,
            is_windows=sys.platform == "win32",
        )

    bridge._run_async(_do, on_done=_on_done)


# ── Internal pipeline helpers ─────────────────────────────────────────

def _bridge_run_local_import(bridge, app_id, lua_path, manifest_folder=''):
    """Import a local Lua/archive without any provider API calls.
    Extracts lua + manifests, installs to Steam, writes ACF, registers library entry."""
    try:
        from pathlib import Path as _Path
        from sff.lua.manager import parse_lua_contents
        from sff.steam_tools_compat import install_lua_to_steam
        from sff.lua.writer import ACFWriter, ConfigVDFWriter
        from sff.core.storage.vdf import ensure_library_has_app
        from sff.zip import read_lua_from_zip

        steam_path = bridge._steam_path
        dest = _Path(bridge._active_library) if bridge._active_library else steam_path
        lua_file = _Path(lua_path) if lua_path else None
        if not steam_path or not dest:
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Error: No Steam path/library selected", "progress": 0
            }))
            return False
        if not lua_file or not lua_file.exists():
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id, "status": f"Error: Lua file not found: {lua_path}", "progress": 0
            }))
            return False

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Extracting local Lua...", "progress": 10
        }))

        lua_install_file = lua_file
        if lua_file.suffix.lower() in (".zip", ".rar", ".7z"):
            _dc = (steam_path / "depotcache") if steam_path else None
            lua_text = read_lua_from_zip(lua_file, decode=True, depotcache=_dc)
            if not lua_text:
                bridge.download_progress.emit(json.dumps({
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
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Error: Failed to parse Lua", "progress": 0
            }))
            return False
        _auto_update_was_registered = _bridge_auto_update_was_registered(bridge, app_id)

        # Copy manifests from manifest_folder if provided
        if manifest_folder:
            import shutil as _shutil
            from sff.core.utils import manifests_staging_dir
            staging = manifests_staging_dir()
            depotcache = steam_path / "depotcache"
            depotcache.mkdir(parents=True, exist_ok=True)
            mf_path = _Path(manifest_folder)
            if mf_path.exists() and mf_path.is_dir():
                bridge.download_progress.emit(json.dumps({
                    "app_id": app_id, "status": "Staging manifests...", "progress": 20
                }))
                for mf in mf_path.glob("*.manifest"):
                    _shutil.copy2(mf, staging / mf.name)
                    _shutil.copy2(mf, depotcache / mf.name)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Installing Lua to Steam", "progress": 30
        }))
        install_lua_to_steam(steam_path, app_id, lua_install_file)
        _bridge_apply_auto_update_default(bridge, app_id, _auto_update_was_registered)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Writing decryption keys", "progress": 40
        }))
        ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Setting up achievements", "progress": 50
        }))
        try:
            from sff.registry_access import set_stats_and_achievements
            set_stats_and_achievements(app_id)
        except Exception as exc:
            logger.debug("local import stats setup skipped: %s", exc)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Registering app ID", "progress": 60
        }))
        if hasattr(bridge._ui, "app_list_man") and bridge._ui.app_list_man:
            bridge._ui.app_list_man.add_ids(parsed)
        elif sys.platform == "linux":
            if hasattr(bridge._ui, "sls_man") and bridge._ui.sls_man:
                bridge._ui.sls_man.add_ids(parsed)
                try:
                    from sff.linux.slssteam import detect_steam_type, patch_slssteam_config
                    patch_slssteam_config(detect_steam_type(), lambda _: None)
                except Exception:
                    pass

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Writing ACF", "progress": 70
        }))
        acf = ACFWriter(dest)
        acf.write_acf(parsed)
        if hasattr(acf, "patch_workshop_acf"):
            acf.patch_workshop_acf(parsed)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Registering library entry", "progress": 80
        }))
        ensure_library_has_app(steam_path, dest, app_id)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Complete", "progress": 100
        }))
        return True
    except Exception as exc:
        logger.exception("Local import failed: %s", exc)
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": f"Error: {exc}", "progress": 0
        }))
        return False


def _bridge_run_windows_fastest(bridge, app_id, source='', request_update=False, branch='', file_type=''):
    """Prompt-free 11-step pipeline for Windows."""
    try:
        from sff.lua.choices import download_lua_direct
        from sff.lua.manager import parse_lua_contents
        from sff.lua.writer import ACFWriter, ConfigVDFWriter
        from sff.steam_tools_compat import install_lua_to_steam
        from sff.core.storage.vdf import ensure_library_has_app
        from sff.registry_access import set_stats_and_achievements
        from sff.core.structs import LuaEndpoint

        steam_path = bridge._steam_path
        lib_path = Path(bridge._active_library) if bridge._active_library else steam_path

        # Step 1: download lua
        bridge.download_progress.emit(json.dumps({
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
            selected_source = LuaEndpoint.HUBCAP if bridge._api_key else LuaEndpoint.OUREVERYDAY
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
            bridge.download_progress.emit(json.dumps({
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
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Parsing Lua", "progress": 20
        }))
        lua_contents = lua_path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_lua_contents(lua_contents, lua_path)
        if not parsed:
            return False
        _auto_update_was_registered = _bridge_auto_update_was_registered(bridge, app_id)

        # Step 3: set stats and achievements (Windows only)
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Setting up achievements", "progress": 30
        }))
        try:
            set_stats_and_achievements(app_id)
        except Exception as e:
            logger.warning("set_stats_and_achievements failed: %s", e)

        # Step 4: register app ID for injection
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Registering app ID", "progress": 40
        }))
        if hasattr(bridge._ui, 'app_list_man') and bridge._ui.app_list_man:
            try:
                bridge._ui.app_list_man.add_ids(parsed)
            except Exception as e:
                logger.warning("add_ids failed: %s", e)

        # Step 5: write decryption keys
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Writing decryption keys", "progress": 50
        }))
        config_writer = ConfigVDFWriter(steam_path)
        try:
            config_writer.add_decryption_keys_to_config(parsed)
        except Exception as e:
            logger.warning("add_decryption_keys failed: %s", e)

        # Step 6: backup & install lua to Steam plugin dir
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Installing Lua to Steam", "progress": 60
        }))
        try:
            install_lua_to_steam(steam_path, app_id, lua_path)
            _bridge_apply_auto_update_default(bridge, app_id, _auto_update_was_registered)
        except Exception as e:
            logger.warning("install_lua_to_steam failed: %s", e)

        # Step 7: write ACF + patch workshop ACF
        bridge.download_progress.emit(json.dumps({
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
        bridge.download_progress.emit(json.dumps({
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
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Updating download tracker", "progress": 95
        }))
        if hasattr(bridge._ui, 'download_manager') and bridge._ui.download_manager:
            try:
                dl_id = bridge._ui.download_manager.track_external(
                    app_id=app_id,
                    game_name=parsed.name if hasattr(parsed, 'name') else f"App {app_id}",
                )
                bridge._ui.download_manager.complete_external(dl_id, success=True)
            except Exception as e:
                logger.warning("download tracking failed: %s", e)

        # Step 11: done
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Complete", "progress": 100
        }))
        return True

    except Exception as e:
        logger.exception("Windows fastest download failed: %s", e)
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": f"Error: {e}", "progress": 0
        }))
        return False


def _bridge_run_linux_fastest(bridge, app_id):
    """Wraps process_from_store; distinguishes real, partial, and no-sls runs."""
    # Refuse to run when SLSSteam is not initialized; the old code returned
    # silently and the UI rendered 100% complete despite no work happening.
    sls_man = getattr(bridge._ui, "sls_man", None)
    if sls_man is None:
        bridge.download_progress.emit(json.dumps({
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

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Downloading via DepotDownloader", "progress": 30
        }))

        from pathlib import Path as _Path
        lib_override = _Path(bridge._active_library) if bridge._active_library else bridge._steam_path
        result = bridge._ui.process_from_store(
            app_id=app_id,
            manifest_override=manifest_override,
            use_hubcap=bool(bridge._api_key),
            lib_path=lib_override,
        )

        # process_from_store on Linux + sls_man writes ACF and the library
        # entry, then returns LOOP_NO_PROMPT without running DepotDownloader.
        # Surface a partial-success status, nudge Steam, and skip the bogus
        # Complete/100 emit instead of pretending the download finished.
        if result is MainReturnCode.LOOP_NO_PROMPT:
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id,
                "status": "ACF written, starting DDMod download...",
                "progress": 50,
            }))
            return _bridge_run_linux_ddmod_fallback(bridge, app_id, manifest_override, lib_override)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Complete", "progress": 100
        }))
        return True

    except Exception as e:
        logger.exception("Linux fastest download failed: %s", e)
        return False


def _bridge_run_linux_ddmod_fallback(bridge, app_id, manifest_override, lib_path):
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

        bridge.download_progress.emit(json.dumps({
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
            bridge.download_progress.emit(json.dumps({
                "app_id": str(app_id), "status": "Complete", "progress": 100
            }))
            return True
        return False
    except Exception:
        logger.exception("Linux DDMod fallback failed for app %s", app_id)
        return False


# ── DLC download ──────────────────────────────────────────────────────

def _bridge_download_dlc_oureveryday(bridge, dlc_appid, parent_appid):
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
        bridge._emit_task_result("download_dlc", False, f"Invalid DLC App ID: '{dlc_appid}'")
        return
    if not parent_appid or not parent_appid.strip().isdigit():
        bridge._emit_task_result("download_dlc", False, f"Invalid parent App ID: '{parent_appid}'")
        return

    def _do():
        import json as _json
        from pathlib import Path as _Path
        try:
            from sff.network.steam_client import create_provider_for_current_thread
            from sff.manifest.downloader import ManifestDownloader
        except Exception as e:
            logger.exception("download_dlc_oureveryday: import failed: %s", e)
            return (False, f"Internal error: {e}")

        steam_path = bridge._steam_path
        if not steam_path:
            return (False, "Steam path not configured")

        bridge.download_progress.emit(_json.dumps({
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
                from sff.network.steam_client import create_provider_for_current_thread as _mk
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
            bridge.download_progress.emit(_json.dumps({
                "app_id": dlc_appid, "status": "Loading depot keys", "progress": 25
            }))
            try:
                local_db = _Path(__file__).parent.parent.parent / "lua" / "fallback_depotkeys.json"
                if local_db.exists():
                    keys_dict = _json.loads(local_db.read_text(encoding="utf-8"))
                    if keys_dict:
                        _flat = {}
                        for _dk, _dv in keys_dict.items():
                            if isinstance(_dv, dict):
                                _flat[str(_dk)] = str(_dv.get("key", "") or "")
                            else:
                                _flat[str(_dk)] = str(_dv or "")
                        keys_dict = _flat
            except Exception as e:
                logger.debug("download_dlc_oureveryday: key db load failed: %s", e)

        cdn = None
        downloader = None
        saved = 0
        new_lines = []
        if dlc_depots:
            # Step 3: fetch manifests through the standard cascade
            bridge.download_progress.emit(_json.dumps({
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
            bridge.download_progress.emit(_json.dumps({
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
        bridge.download_progress.emit(_json.dumps({
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
        game_installdir = None
        game_library = None
        try:
            from sff.core.storage.vdf import get_steam_libs as _gsl, vdf_load as _vl, vdf_dump as _vd
            _libs = _gsl(steam_path) if steam_path else []
            for _lib in _libs:
                _acf = _Path(_lib) / "steamapps" / f"appmanifest_{parent_appid}.acf"
                if not _acf.exists():
                    continue
                _data = _vl(_acf)
                _state = _data.get("AppState", {})
                if not isinstance(_state, dict):
                    break
                game_installdir = str(_state.get("installdir", ""))
                game_library = _lib
                _installed = _state.setdefault("InstalledDepots", {})
                _changed = False
                for _did, _gid in dlc_depots:
                    _ds = str(_did)
                    _gs = str(_gid) if _gid else "0"
                    _entry = _installed.get(_ds)
                    if isinstance(_entry, dict):
                        if _entry.get("manifest", "0") != _gs:
                            _entry["manifest"] = _gs
                            _changed = True
                        if not _entry.get("dlcappid"):
                            _entry["dlcappid"] = str(dlc_appid)
                            _changed = True
                    else:
                        _installed[_ds] = {"manifest": _gs, "size": "0", "dlcappid": str(dlc_appid)}
                        _changed = True
                if _changed:
                    _state["InstalledDepots"] = _installed
                    _state.pop("MountedDepots", None)
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

        # Step 6: download actual DLC depot files so the content
        # exists on disk (not just manifest + ACF entries with 0 MB).
        dlc_downloaded = 0
        if dlc_depots and game_installdir and game_library and saved > 0:
            game_dir = _Path(game_library) / "steamapps" / "common" / game_installdir
            bridge.download_progress.emit(_json.dumps({
                "app_id": dlc_appid, "status": "Downloading DLC files", "progress": 65
            }))
            for _did, _gid in dlc_depots:
                _key = keys_dict.get(_did)
                if not _key or not _gid:
                    continue
                try:
                    from sff.downloads.native_downloader import download_depot as _ndl
                    _mf = _Path(steam_path) / "depotcache" / f"{_did}_{_gid}.manifest"
                    if not _mf.exists():
                        _mf = _Path(steam_path) / "config" / "depotcache" / f"{_did}_{_gid}.manifest"
                    _ok, _sz = _ndl(
                        parent_appid, _did, _gid, _key, game_dir,
                        print_fn=lambda m: logger.debug("  [DLC ndl] %s", m),
                        os_filter=("linux" if sys.platform.startswith("linux") else "windows"),
                        steam_path=steam_path,
                        manifest_path=_mf if _mf.exists() else None,
                    )
                    if _ok:
                        dlc_downloaded += 1
                        logger.debug("download_dlc_oureveryday: DLC depot %s downloaded (%s bytes)", _did, _sz)
                except ImportError:
                    logger.debug("download_dlc_oureveryday: native downloader not available, skipping depot download")
                    break
                except Exception as _e:
                    logger.debug("download_dlc_oureveryday: DLC depot %s download failed: %s", _did, _e)

        # Register DLC in SLSsteam on Linux so it shows in Steam properties
        if sys.platform == "linux":
            try:
                if hasattr(bridge._ui, "sls_man") and bridge._ui.sls_man:
                    bridge._ui.sls_man.add_ids([int(dlc_appid)])
            except Exception as e:
                logger.warning("download_dlc_oureveryday: SLSsteam DLC registration failed: %s", e)

        bridge.download_progress.emit(_json.dumps({
            "app_id": dlc_appid, "status": "Complete", "progress": 100
        }))
        if dlc_depots:
            _extras = f", {dlc_downloaded} depot(s) downloaded" if dlc_downloaded else ""
            msg = (
                f"DLC {dlc_appid} added to {parent_appid}.lua "
                f"({saved} manifest(s) saved, {appended} key line(s) appended, "
                f"ACF patched with {len(dlc_depots)} DLC depot(s){_extras})"
            )
        else:
            state = "already present" if appended == 0 else "appid line appended"
            msg = f"DLC {dlc_appid} added to {parent_appid}.lua ({state}; no separate depots)"
        return (True, msg)

    def _on_done(result):
        if isinstance(result, tuple):
            ok, msg = result
            bridge._emit_task_result("download_dlc", ok, msg, dlc_app_id=dlc_appid, parent_app_id=parent_appid)
        else:
            bridge._emit_task_result("download_dlc", False, "DLC download failed", dlc_app_id=dlc_appid, parent_app_id=parent_appid)

    bridge._run_async(_do, on_done=_on_done)


# ── Version download ──────────────────────────────────────────────────

def _bridge_download_game_version(bridge, app_id, manifest_override_json, source='oureveryday'):
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

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Starting version download", "progress": 10
        }))

        from pathlib import Path as _Path
        from sff.core.structs import LuaEndpoint
        lib_override = _Path(bridge._active_library) if bridge._active_library else bridge._steam_path
        src_map = {"hubcap": LuaEndpoint.HUBCAP, "ryuu": LuaEndpoint.RYUU, "oureveryday": LuaEndpoint.OUREVERYDAY, "depotbox": LuaEndpoint.DEPOTBOX}
        selected = src_map.get(source, LuaEndpoint.HUBCAP if bridge._api_key else LuaEndpoint.OUREVERYDAY)
        try:
            bridge._ui.process_from_store(
                app_id=app_id,
                manifest_override=manifest_override,
                use_hubcap=(selected == LuaEndpoint.HUBCAP),
                lib_path=lib_override,
            )
        except Exception:
            logger.exception("download_game_version: process_from_store failed for %s", app_id)
            return False

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Complete", "progress": 100
        }))
        return True

    def _on_done(result):
        success = result is True
        bridge._emit_task_result(
            "download_version",
            success,
            f"Version download {'completed' if success else 'failed'} for App {app_id}",
            app_id=app_id,
        )

    def _on_error(error_msg):
        bridge._emit_task_result(
            "download_version", False, error_msg, app_id=app_id
        )

    bridge._run_async(_do, on_done=_on_done, on_error=_on_error)


def _bridge_download_game_version_native(bridge, app_id, manifest_override_json, source='oureveryday'):
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

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Starting Steam Native download", "progress": 5
        }))

        from sff.lua.choices import download_lua_direct
        from sff.lua.manager import parse_lua_contents, write_manifest_pins_to_lua
        from sff.steam_tools_compat import install_lua_to_steam
        from sff.lua.writer import ACFWriter, ConfigVDFWriter
        from sff.core.structs import LuaEndpoint

        steam_path = bridge._steam_path
        lib_override = Path(bridge._active_library) if bridge._active_library else steam_path

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Downloading Lua", "progress": 10
        }))

        saved_lua_root = Path.cwd() / "saved_lua"
        saved_lua_root.mkdir(exist_ok=True)
        src_map = {"hubcap": LuaEndpoint.HUBCAP, "ryuu": LuaEndpoint.RYUU, "oureveryday": LuaEndpoint.OUREVERYDAY, "depotbox": LuaEndpoint.DEPOTBOX}
        selected_source = src_map.get(source, LuaEndpoint.HUBCAP if bridge._api_key else LuaEndpoint.OUREVERYDAY)
        lua_path = download_lua_direct(
            dest=saved_lua_root, app_id=app_id,
            source=selected_source, steam_path=steam_path,
        )
        if not lua_path:
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Lua download failed. Try a different source.",
                "progress": 0, "error": True,
            }))
            return False

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Pinning manifests in Lua", "progress": 30
        }))
        pinned = write_manifest_pins_to_lua(lua_path, manifest_override)
        if not pinned:
            logger.warning("download_game_version_native: no manifests pinned for %s", app_id)
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id,
                "status": "No manifest pins were written. ACF was not created.",
                "progress": 0,
                "error": True,
            }))
            return False

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Installing Lua to Steam", "progress": 50
        }))
        _auto_update_was_registered = _bridge_auto_update_was_registered(bridge, app_id)
        install_lua_to_steam(steam_path, app_id, lua_path)
        _bridge_apply_auto_update_default(bridge, app_id, _auto_update_was_registered)

        parsed = parse_lua_contents(
            lua_path.read_text(encoding="utf-8", errors="replace"), lua_path
        )
        if not parsed:
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id,
                "status": "Lua parse failed after pinning. ACF was not created.",
                "progress": 0,
                "error": True,
            }))
            return False

        config_writer = ConfigVDFWriter(steam_path)
        config_writer.add_decryption_keys_to_config(parsed)

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Writing ACF", "progress": 70
        }))
        buildid = "0"
        try:
            from sff.network.steam_client import create_provider_for_current_thread
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

        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Complete — Steam will download the game", "progress": 100
        }))
        return True

    def _on_done(result):
        success = result is True
        bridge._emit_task_result(
            "download_version_native",
            success,
            f"Steam Native download {'completed' if success else 'failed'} for App {app_id}",
            app_id=app_id,
        )

    def _on_error(error_msg):
        bridge._emit_task_result(
            "download_version_native", False, error_msg, app_id=app_id
        )

    bridge._run_async(_do, on_done=_on_done, on_error=_on_error)


# ── DDMod download ────────────────────────────────────────────────────

def _bridge_download_game_ddmod(bridge, app_id, source, lua_path, manifest_folder='', target_os='', branch='', file_type=''):
    """Download a game using DepotDownloaderMod.
    source: 'hubcap' | 'oureveryday' | 'ryuu' | 'local'
    lua_path: used when source == 'local'
    Emits download_progress + task_finished signals."""
    if not app_id or not app_id.strip().isdigit():
        bridge._emit_task_result("download_ddmod", False, f"Invalid App ID: '{app_id}'")
        return
    def _do():
        bridge.download_progress.emit(json.dumps({
            "app_id": app_id, "status": "Starting DDMod download", "progress": 0
        }))
        _bridge_unlock_steam_readonly(bridge)
        log_stream = None
        old_stdout = None
        old_stderr = None
        try:
            import io
            import sys
            from pathlib import Path as _Path
            from sff.lua.endpoints import get_hubcap, get_oureverday, get_ryuu, get_depotbox
            from sff.lua.manager import parse_lua_contents
            from sff.downloads.depot_downloader import run_download, filter_depots_by_os

            class LoggerStream(io.StringIO):
                def __init__(self, logger_func):
                    super().__init__()
                    self.logger_func = logger_func
                    self._line_buffer = ""
                def write(self, string):
                    self._line_buffer += string
                    if "\n" in self._line_buffer:
                        lines = self._line_buffer.split("\n")
                        self._line_buffer = lines.pop()
                        for line in lines:
                            if line.strip():
                                self.logger_func(line)
                    return len(string)
                def flush(self):
                    if self._line_buffer.strip():
                        self.logger_func(self._line_buffer)
                        self._line_buffer = ""

            log_stream = LoggerStream(logger.debug)
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = log_stream
            sys.stderr = log_stream

            steam_path = bridge._steam_path
            dest = _Path(bridge._active_library) if bridge._active_library else steam_path
            if dest is None:
                return (False, "No Steam library selected. Please select a download location.")
            # If user didn't pick a library, auto-resolve to the one where
            # an existing ACF lives. If they DID pick one, respect it.
            if not bridge._active_library:
                try:
                    from sff.core.storage.vdf import get_steam_libs
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

            bridge.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Fetching Lua file...", "progress": 5
            }))

            if source == "local":
                lua_file = _Path(lua_path) if lua_path else None
                if not lua_file or not lua_file.exists():
                    return (False, f"Lua file not found: {lua_path}")
            elif source == "hubcap":
                lua_file = get_hubcap(lua_dest, app_id, depotcache=(steam_path / "depotcache") if steam_path else None, hubcap_key=bridge._api_key)
            elif source == "oureveryday":
                lua_file = get_oureverday(lua_dest, app_id)
            elif source == "ryuu":
                lua_file = get_ryuu(lua_dest, app_id, request_update=False, branch=branch, file_type=file_type, depotcache=(steam_path / "depotcache") if steam_path else None)
            elif source == "depotbox":
                lua_file = get_depotbox(lua_dest, app_id)
            else:
                return (False, f"Unknown source: {source}")

            if not lua_file or not lua_file.exists():
                return (False, f"Failed to obtain Lua file from source '{source}'")

            bridge.download_progress.emit(json.dumps({
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
            _auto_update_was_registered = _bridge_auto_update_was_registered(bridge, app_id)

            # ── Steam registration (LumaCore on Windows / SLSSteam on Linux) ──
            # Without these the library card shows "Buy" because Steam never
            # learns about the install. Mirror _run_windows_fastest on win32
            # and process_from_store on linux. LumaCore is Windows-only so
            # the stplug-in copy never runs on Linux (requirement 2.33).
            # Kill Steam before writing config files — Steam locks
            # config.vdf while running, which blocks depot key writes and
            # causes "Content Still Encrypted" on launch.
            try:
                from sff.core.processes import SteamProcess, is_proc_running
                _sp = SteamProcess(steam_path)
                if is_proc_running(_sp.exe_name):
                    _sp.kill()
                    import time as _t3
                    _w = 0
                    while is_proc_running(_sp.exe_name) and _w < 20:
                        _t3.sleep(0.5); _w += 0.5
            except Exception:
                pass

            if sys.platform == "win32":
                # Calls install_lua_to_steam, ConfigVDFWriter.add_decryption_keys_to_config,
                # set_stats_and_achievements, app_list_man.add_ids,
                # ACFWriter.write_acf(parsed), ACFWriter.patch_workshop_acf(parsed),
                # ensure_library_has_app(steam_path, dest, app_id).
                try:
                    from sff.steam_tools_compat import install_lua_to_steam
                    install_lua_to_steam(steam_path, app_id, lua_install_file)
                    _bridge_apply_auto_update_default(bridge, app_id, _auto_update_was_registered)
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
                    if hasattr(bridge._ui, 'app_list_man') and bridge._ui.app_list_man:
                        bridge._ui.app_list_man.add_ids(parsed)
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
                    from sff.core.storage.vdf import ensure_library_has_app
                    ensure_library_has_app(steam_path, dest, app_id)
                except Exception as _le:
                    logger.warning("ensure_library_has_app failed (non-fatal): %s", _le)

            elif sys.platform == "linux":
                # SLSSteam consumes ~/.config/SLSsteam/config.yaml.
                try:
                    if hasattr(bridge._ui, 'sls_man') and bridge._ui.sls_man:
                        bridge._ui.sls_man.add_ids(parsed)
                except Exception as _sle:
                    logger.warning("sls_man.add_ids failed (non-fatal): %s", _sle)

                # Ensure PlayNotOwnedGames is enabled so SLSsteam grants
                # ownership and Steam shows "Play" instead of "Purchase".
                try:
                    from sff.linux.slssteam import detect_steam_type, patch_slssteam_config
                    patch_slssteam_config(detect_steam_type(), lambda _: None)
                except Exception as _pnog:
                    pass

                try:
                    from sff.lua.writer import ConfigVDFWriter as _CVF2
                    _CVF2(steam_path).add_decryption_keys_to_config(parsed)
                except Exception as _kwe2:
                    logger.warning("add_decryption_keys_to_config failed (non-fatal): %s", _kwe2)

                try:
                    from sff.core.storage.vdf import ensure_library_has_app
                    ensure_library_has_app(steam_path, dest, app_id)
                except Exception as _le:
                    logger.warning("ensure_library_has_app failed (non-fatal): %s", _le)

            if source == "local":
                if manifest_folder:
                    import shutil as _shutil
                    from sff.core.utils import manifests_staging_dir
                    _staging = manifests_staging_dir()
                    _depotcache = steam_path / "depotcache"
                    _depotcache.mkdir(parents=True, exist_ok=True)
                    for _mf in _Path(manifest_folder).glob("*.manifest"):
                        _staging.mkdir(parents=True, exist_ok=True)
                        _shutil.copy2(_mf, _staging / _mf.name)
                        _shutil.copy2(_mf, _depotcache / _mf.name)
                return (True, "Local Lua/manifests imported without Hubcap/Ryuu/OurEveryday or DDMod")

            # Confirm registration before the depot fetch fires.
            bridge.download_progress.emit(json.dumps({
                "app_id": app_id, "status": "Registered with Steam", "progress": 22
            }))

            bridge.download_progress.emit(json.dumps({
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
                    from sff.network.steam_client import create_provider_for_current_thread
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
                    from sff.core.storage.settings import get_setting as _gs
                    from sff.core.structs import Settings as _S
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
            bridge._current_game_data = game_data

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

            bridge.download_progress.emit(json.dumps({
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
            # download completion shows 100% in the ui now
            _DDMOD_CEIL = 100.0
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
                                bridge.download_progress.emit(json.dumps({
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
                    steam_path=steam_path,
                )
                logger.info("ACF write completed successfully")
            except Exception as _ae:
                logger.warning("ACF write failed (non-fatal): %s", _ae)

            # Move manifests to library depotcache so Steam can validate for downloaded depots.
            try:
                from sff.downloads.depot_downloader import move_manifests_to_depotcache
                filtered = [str(depot_id) for depot_id in selected_depots]
                move_manifests_to_depotcache(steam_path, manifests_dict, filtered_depot_ids=filtered)
            except Exception as _me:
                logger.debug("Manifest move skipped: %s", _me)

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
        finally:
            if log_stream is not None:
                log_stream.flush()
            if old_stdout is not None:
                sys.stdout = old_stdout
            if old_stderr is not None:
                sys.stderr = old_stderr

    def _on_done(result):
        if isinstance(result, tuple):
            ok, msg = result[0], result[1]
        else:
            ok, msg = False, "Download failed"
        if ok and source in ("hubcap", "ryuu"):
            QTimer.singleShot(1000, bridge._maybe_auto_contribute_provider)
        game_data = getattr(bridge, '_current_game_data', None)
        if isinstance(result, tuple) and result[0]:
            game_name = game_data.get("game_name", f"App {app_id}") if game_data else f"App {app_id}"
            _bridge_track_download(bridge, app_id, game_name, ok)
        bridge._emit_task_result("download_ddmod", ok, msg, app_id=app_id,
                               is_windows=sys.platform == "win32")

    bridge._run_async(_do, on_done=_on_done)


# ── Local Lua import (no providers) ───────────────────────────────────

def _bridge_import_local_lua(bridge, app_id, lua_path, manifest_folder=''):
    """Register a local Lua/archive without provider APIs or DDMod."""
    if not app_id or not app_id.strip().isdigit():
        bridge._emit_task_result("import_local_lua", False, f"Invalid App ID: '{app_id}'", app_id=app_id)
        return

    def _do():
        try:
            from pathlib import Path as _Path
            from sff.lua.manager import parse_lua_contents
            from sff.steam_tools_compat import install_lua_to_steam
            from sff.lua.writer import ACFWriter, ConfigVDFWriter
            from sff.core.storage.vdf import ensure_library_has_app

            steam_path = bridge._steam_path
            dest = _Path(bridge._active_library) if bridge._active_library else steam_path
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
            _auto_update_was_registered = _bridge_auto_update_was_registered(bridge, app_id)

            if manifest_folder:
                import shutil as _shutil
                from sff.core.utils import manifests_staging_dir
                staging = manifests_staging_dir()
                depotcache = steam_path / "depotcache"
                depotcache.mkdir(parents=True, exist_ok=True)
                for mf in _Path(manifest_folder).glob("*.manifest"):
                    _shutil.copy2(mf, staging / mf.name)
                    _shutil.copy2(mf, depotcache / mf.name)

            install_lua_to_steam(steam_path, app_id, lua_install_file)
            _bridge_apply_auto_update_default(bridge, app_id, _auto_update_was_registered)
            ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)
            try:
                from sff.registry_access import set_stats_and_achievements
                set_stats_and_achievements(app_id)
            except Exception as exc:
                logger.debug("import_local_lua stats setup skipped: %s", exc)
            if hasattr(bridge._ui, "app_list_man") and bridge._ui.app_list_man:
                bridge._ui.app_list_man.add_ids(parsed)
            elif sys.platform == "linux":
                if hasattr(bridge._ui, "sls_man") and bridge._ui.sls_man:
                    bridge._ui.sls_man.add_ids(parsed)
                    try:
                        from sff.linux.slssteam import detect_steam_type, patch_slssteam_config
                        patch_slssteam_config(detect_steam_type(), lambda _: None)
                    except Exception:
                        pass
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
        bridge._emit_task_result("import_local_lua", ok, msg, app_id=app_id)

    bridge._run_async(_do, on_done=_on_done)


# ── Shared helpers (kept in web_bridge.py) ─────────────────────────────
# _run_async         — used by 51+ methods across ALL domains
# _emit_task_result  — used by every async method
# _maybe_auto_contribute_provider — used by __init__ (timer) + download methods
