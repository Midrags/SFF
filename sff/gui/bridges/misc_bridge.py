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
Miscellaneous bridge functions extracted from web_bridge.py.

Each ``_bridge_*`` function takes a ``WebBridge`` instance as its first
parameter (named ``bridge``) in place of ``self``.
"""

import base64
import concurrent.futures as _concurrent
import datetime
import json
import logging
import os
import platform
import queue
import re
import shutil
import string
import subprocess
import sys
import time
import urllib.error as _urlerror
import urllib.parse as _urlparse
import urllib.request as _req
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)

def _bridge_signal_ready(bridge):
    parent = bridge.parent()
    if parent and hasattr(parent, "dismiss_splash"):
        parent.dismiss_splash()

def _bridge_window_minimize(bridge):
    parent = bridge.parent()
    if parent:
        parent.showMinimized()

def _bridge_window_maximize(bridge):
    parent = bridge.parent()
    if parent:
        if parent.windowState() & Qt.WindowState.WindowMaximized:
            parent.showNormal()
        else:
            parent.showMaximized()

def _bridge_window_is_maximized(bridge):
    parent = bridge.parent()
    if parent:
        return json.dumps({"maximized": bool(parent.windowState() & Qt.WindowState.WindowMaximized)})
    return json.dumps({"maximized": False})

def _bridge_window_close(bridge):
    parent = bridge.parent()
    if parent:
        parent.close()

def _bridge_toggle_ui(bridge):
    parent = bridge.parent()
    if parent and hasattr(parent, "_toggle_web_ui"):
        parent._toggle_web_ui()

def _bridge_fetch_depot_history(bridge, app_id, force_refresh):
    """Fetch depot/manifest history for a game. Emits depot_history_results."""
    def _progress(msg):
        bridge.download_progress.emit(json.dumps({
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
            if len(result) >= 200:
                break
        return result

    def _on_done(data):
        bridge.depot_history_results.emit(json.dumps(data or []))

    bridge._run_async(_do, on_done=_on_done)

def _bridge_dlc_check_get_list(bridge, app_id):
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
        bridge._emit_task_result("dlc_check", False, "Invalid app ID",
                               app_id=str(app_id), dlcs=[])
        return

    def _do():
        base_id = int(app_id)
        local_ids: set = set()
        try:
            if bridge._ui:
                inj = getattr(bridge._ui, 'app_list_man', None) or getattr(bridge._ui, 'sls_man', None)
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
            if bridge._steam_path:
                lua_path = _Path(bridge._steam_path) / "config" / "stplug-in" / f"{base_id}.lua"
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
            from sff.core.storage.vdf import get_steam_libs as _gsl
            libs = _gsl(bridge._steam_path) if bridge._steam_path else []
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
            if bridge._ui and getattr(bridge._ui, 'provider', None):
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FT
                base_info = None
                # SteamClient pins gevents hub to the OS thread that
                # constructed it. bridge._ui.provider was built on the
                # GUI thread (or whichever thread first touched the
                # ui), so calling its methods from a ThreadPoolExecutor
                # worker fires "would block forever". Build a
                # throwaway provider inside the executor instead.
                def _fetch_base_info():
                    from sff.network.steam_client import create_provider_for_current_thread as _mk
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
                    from sff.core.utils import enter_path
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
                cache_obj = getattr(bridge._ui, 'app_info_cache', None) if bridge._ui else None
                if cache_obj is not None:
                    cached = None
                    try:
                        cached = cache_obj.get(base_id)
                    except Exception:
                        cached = None
                    if cached:
                        from sff.core.utils import enter_path
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
                from sff.network.steam_store import get_dlc_list_from_store
                result = get_dlc_list_from_store(base_id)
                if result:
                    base_name = result[0] or base_name
                    dlc_ids = list(result[1] or [])
            except Exception as e:
                logger.debug("dlc_check_get_list: Store API path failed: %s", e)

        if not dlc_ids:
            bridge._emit_task_result(
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
        from sff.network.steam_store import get_dlc_names_from_store
        try:
            names_map = get_dlc_names_from_store(dlc_ids) or {}
        except Exception as e:
            logger.debug("dlc_check_get_list: name fetch failed: %s", e)
            names_map = {}

        # Decryption keys live in <steam>/config/config.vdf.
        try:
            from sff.lua.writer import ConfigVDFWriter
            cfg = ConfigVDFWriter(bridge._steam_path) if bridge._steam_path else None
            key_map = cfg.ids_in_config(dlc_ids) if cfg else {}
        except Exception as e:
            logger.debug("dlc_check_get_list: key map failed: %s", e)
            key_map = {}

        # depotcache scan: filenames look like '<depotid>_<gid>.manifest'.
        # if any depot the dlc owns lands here, count it as on-disk. cheap,
        # one stat per directory entry.
        depotcache_ids: set = set()
        try:
            if bridge._steam_path:
                from pathlib import Path as _P2
                candidates = [
                    _P2(bridge._steam_path) / "depotcache",
                    _P2(bridge._steam_path) / "config" / "depotcache",
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

        bridge._emit_task_result(
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
        bridge._emit_task_result("dlc_check", False, str(msg),
                               app_id=str(app_id), dlcs=[])

    bridge._run_async(_do, on_error=_on_error)

def _bridge_get_bundled_tool_path(bridge, tool_name: str) -> str:
    """Return the absolute path to a bundled tool executable, or empty string."""
    p = bridge._get_bundled_tool_path(tool_name)
    return str(p) if p else ""

def _bridge_check_game_update(bridge, app_id):
    """Compare installed ACF buildid against Steam CM public buildid.
    If Steam CM is newer: download updated manifests and patch the ACF.
    Emits task_finished with task='update_check'."""
    def _do():
        try:
            from pathlib import Path as _Path
            from sff.core.storage.vdf import get_steam_libs, vdf_load
            from sff.lua.writer import ACFWriter
            from sff.manifest.downloader import ManifestDownloader
            from sff.lua.manager import LuaManager, LuaChoice, write_manifest_pins_to_lua
            from sff.network.steam_client import create_provider_for_current_thread
            from sff.core.storage.settings import get_setting
            from sff.core.structs import OSType, Settings
            from sff.steam_tools_compat import install_lua_to_steam

            steam_libs = get_steam_libs(bridge._steam_path) if bridge._steam_path else []
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

            install_lua_to_steam(bridge._steam_path, str(parsed_lua.app_id), saved_lua_path)

            downloader = ManifestDownloader(provider, bridge._steam_path)
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
                    install_lua_to_steam(bridge._steam_path, str(parsed_lua.app_id), saved_lua_path)

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
            bridge._record_update_state(str(app_id), result)
        except Exception as cache_err:
            logger.debug("update-state cache write failed: %s", cache_err)
        # Strip keys that collide with _emit_task_result's positional params,
        # otherwise we get TypeError: got multiple values for 'success'/'message'/'task'.
        extras = {
            k: v for k, v in result.items()
            if k not in ("error", "success", "message", "task")
        }
        bridge._emit_task_result("update_check", success, msg, **extras)

    bridge._run_async(_do, on_done=_on_done)

# ── 6.2.5: per-game and global update-available toggle ───────

def _bridge_set_game_update_override(bridge, app_id, enabled):
    """Toggle the per-game LetUpdate override.

    On True: write `<steam>/config/stplug-in/<appid>/00_LetUpdate_override.lua`
    and stamp Settings.GAME_UPDATE_OVERRIDE so the next session knows.
    On False: remove the override file (and any legacy variants) and
    clear the setting key.

    Returns a JSON string `{"ok": bool, "enabled": bool, "msg": str}`.
    """
    try:
        from sff.game.let_update_override import set_enabled as _set_lc
        ok = _set_lc(bridge._steam_path, str(app_id), bool(enabled))
        return json.dumps({
            "ok": bool(ok),
            "enabled": bool(enabled),
            "msg": "" if ok else "Override write failed; check debug.log",
        })
    except Exception as e:
        logger.exception("set_game_update_override failed: %s", e)
        return json.dumps({"ok": False, "enabled": False, "msg": str(e)})

def _bridge_let_updates_list_games(bridge):
    """Return stplug-in Lua files that have manifest pins.

    Checked in the UI means Steam is allowed to auto-update that game,
    implemented by commenting every setManifestid line in that Lua.
    """
    try:
        from sff.lua.update_pins import discover_games, helper_status

        games = discover_games(bridge._steam_path)
        return json.dumps({
            "ok": True,
            "steam_path": str(bridge._steam_path or ""),
            "games": games,
            "count": len(games),
            "helper": helper_status(bridge._steam_path),
        })
    except Exception as e:
        logger.exception("let_updates_list_games failed: %s", e)
        return json.dumps({"ok": False, "error": str(e), "games": []})

def _bridge_let_updates_set_helper(bridge, enabled):
    """Create or remove the global 00_LetUpdate_override.lua helper."""
    try:
        from sff.lua.update_pins import set_helper_enabled

        return json.dumps(set_helper_enabled(bridge._steam_path, bool(enabled)))
    except Exception as e:
        logger.exception("let_updates_set_helper failed: %s", e)
        return json.dumps({"ok": False, "error": str(e), "enabled": False})

def _bridge_let_updates_apply(bridge, payload_json):
    """Apply the per-game Steam auto-update selection."""
    try:
        from sff.lua.update_pins import apply_selection_json

        return apply_selection_json(bridge._steam_path, payload_json or "{}")
    except Exception as e:
        logger.exception("let_updates_apply failed: %s", e)
        return json.dumps({"ok": False, "error": str(e), "games": []})

def _bridge_let_updates_add_game(bridge, app_id):
    """Add a single game to the auto-update list without wiping existing selections."""
    try:
        from sff.lua.update_pins import discover_games, apply_selection
        games = discover_games(bridge._steam_path)
        allow = set()
        for g in games:
            if g.get("allow_update"):
                allow.add(str(g.get("app_id", "")))
        allow.add(str(app_id))
        result = apply_selection(bridge._steam_path, list(allow))
        return json.dumps(result)
    except Exception as e:
        logger.exception("let_updates_add_game failed: %s", e)
        return json.dumps({"ok": False, "error": str(e)})

def _bridge_get_game_update_override(bridge, app_id):
    """Return whether 00_LetUpdate_override.lua is active for this app."""
    try:
        from sff.game.let_update_override import is_enabled as _is_lc
        return bool(_is_lc(str(app_id)))
    except Exception:
        return False

def _bridge_set_game_update_check(bridge, app_id, enabled):
    """Persist the per-app update-check override.

    Stores a JSON map under Settings.UPDATE_CHECK_OVERRIDES so the
    periodic timer and the badge UI both observe the same gate.
    """
    try:
        from sff.core.storage.settings import get_setting, set_setting
        from sff.core.structs import Settings
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
        entry = bridge._update_state_cache.get(str(app_id))
        if entry is not None:
            entry["enabled"] = bool(enabled)
        logger.info(
            "set_game_update_check: app_id=%s enabled=%s", app_id, enabled,
        )
    except Exception as e:
        logger.exception("set_game_update_check failed: %s", e)

def _bridge_get_game_update_state(bridge, app_id):
    """Return the cached update state for an app as a JSON string.

    Fields: enabled, up_to_date, installed_buildid, cm_buildid,
    checked_at. Missing entries return a default with enabled
    resolved against the global gate plus per-app override.
    """
    try:
        key = str(app_id)
        cached = bridge._update_state_cache.get(key)
        if cached is None:
            state = {
                "enabled": bridge._app_update_check_enabled(key),
                "up_to_date": None,
                "installed_buildid": None,
                "cm_buildid": None,
                "checked_at": 0,
            }
        else:
            state = dict(cached)
            state["enabled"] = bridge._app_update_check_enabled(key)
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

def _bridge_get_game_branches(bridge, app_id):
    """Return JSON array of available branches from Steam appinfo.
    Tries fresh fetch first, falls back to cache if Steam CM is down."""
    return bridge._fetch_branches(app_id, force_refresh=False)

def _bridge_refresh_game_branches(bridge, app_id):
    """Force-refresh branches from Steam, ignoring cache."""
    return bridge._fetch_branches(app_id, force_refresh=True)

def _bridge_ryuu_request_branch(bridge, app_id, branch):
    """Request a specific branch from Ryuu using the premium API key. Runs async."""
    from sff.core.storage.settings import get_setting
    from sff.core.structs import Settings
    api_key = (get_setting(Settings.RYUU_API_KEY) or "").strip()
    if not api_key:
        bridge._emit_task_result("ryuu_request_branch", False,
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
        bridge._emit_task_result("ryuu_request_branch", bool(result.get("ok")),
            result.get("message") or result.get("error") or "",
            **{k: v for k, v in result.items() if k != "ok"})
    bridge._run_async(_do, on_done=_on_done)

def _bridge_lure_fix_acf(bridge, app_id):
    """Patch the game's ACF with the latest Steam CM manifest IDs and buildid.
    No files are downloaded — pure ACF update to suppress Steam's update prompt.
    Emits task_finished with task='lure_fix'."""
    def _do():
        try:
            from pathlib import Path as _Path
            from sff.core.storage.vdf import get_steam_libs, vdf_load, vdf_dump
            from sff.lua.writer import ACFWriter
            from sff.network.steam_client import create_provider_for_current_thread

            steam_libs = get_steam_libs(bridge._steam_path) if bridge._steam_path else []
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
            state["TargetBuildID"] = cm_buildid
            state["DownloadType"] = "0"
            state["UpdateResult"] = "0"
            state["ScheduledAutoUpdate"] = "0"
            state["BytesToDownload"] = "0"
            state["BytesDownloaded"] = "0"
            state["BytesToStage"] = "0"
            state["BytesStaged"] = "0"
            state["AutoUpdateBehavior"] = "0"
            # Update SizeOnDisk from actual files if possible
            try:
                installdir = state.get("installdir", "")
                if installdir and lib_path:
                    common = lib_path / "steamapps" / "common" / installdir
                    if common.exists():
                        total = sum(
                            f.stat().st_size for f in common.rglob("*")
                            if f.is_file()
                        )
                        state["SizeOnDisk"] = str(total)
            except Exception:
                pass
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
        bridge._emit_task_result("lure_fix", bool(result.get("success")), msg, **extras)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_restart_steam(bridge):
    """Restart or launch Steam."""
    def _do():
        if sys.platform == "win32":
            import time
            from sff.core.processes import (
                SteamProcess,
                is_proc_running,
                launch_steam_unelevated,
            )

            if not bridge._steam_path:
                return (False, "Steam path not set")

            steam_proc = SteamProcess(bridge._steam_path)

            if is_proc_running(steam_proc.exe_name):
                bridge.download_progress.emit(json.dumps({
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

            bridge.download_progress.emit(json.dumps({
                "status": "Starting Steam", "progress": 60, "restart": True
            }))
            injector = bridge._steam_path / "steam.exe"
            ok, msg = launch_steam_unelevated(injector, bridge._steam_path)
            return (ok, msg)

        else:
            from sff.linux.steam_process import kill_steam, start_steam
            kill_steam()
            result = start_steam(steam_path=bridge._steam_path)
            if result == "SUCCESS":
                return (True, "Steam restarted")
            return (False, f"Steam start failed: {result}")

    def _on_done(result):
        if isinstance(result, tuple):
            success, msg = result
        else:
            success, msg = bool(result), "Steam restarted" if result else "Failed to restart Steam"
        bridge._emit_task_result("restart_steam", success, msg)

    def _on_error(error_msg):
        bridge._emit_task_result("restart_steam", False, error_msg)

    bridge._run_async(_do, on_done=_on_done, on_error=_on_error)

def _bridge_open_log_window(bridge):
    """Opens the existing GlobalLogWindow as a standalone native window."""
    parent = bridge.parent()
    if hasattr(parent, '_log_window'):
        parent._log_window.show()
        parent._log_window.raise_()
        parent._log_window.activateWindow()

def _bridge_copy_to_clipboard(bridge, text):
    """Copy text to system clipboard via Qt (works in QWebEngine)."""
    from PyQt6.QtWidgets import QApplication
    QApplication.clipboard().setText(text)

def _bridge_browse_game_folder(bridge):
    """Open a native folder-picker dialog and return the selected path (or '')."""
    from PyQt6.QtWidgets import QFileDialog
    path = QFileDialog.getExistingDirectory(bridge.parent(), "Select game folder")
    return path or ""

def _bridge_install_lumacore(bridge, steam_path_str, variant=""):
    """Copy LumaCore DLLs into the Steam folder and clean up legacy injection files.

    *variant* picks the build flavour ('release' default or 'debug').
    The Auto LC Setup modal radio buttons send 'debug' when the user
    wants the verbose-logging build for support sessions.
    """
    def _do():
        from pathlib import Path
        from sff.lumacore.lumacore_setup import install_lumacore
        steam_path = Path(steam_path_str) if steam_path_str else bridge._ui.steam_path
        def _progress(msg):
            bridge.lc_progress.emit(msg)
        picked = (variant or "release").strip().lower()
        if picked not in ("release", "debug"):
            picked = "release"
        success, message = install_lumacore(steam_path, _progress, variant=picked)
        return success, message

    def _on_done(result):
        success, message = result if isinstance(result, tuple) else (False, str(result))
        bridge._emit_task_result("auto_lc_setup", success, message)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_steam_updates_get_state(bridge):
    """Return 'blocked', 'unblocked', or 'unknown' based on the
    BootStrapperInhibitAll line in <steam>/steam.cfg.

    - blocked   : steam.cfg exists AND the line is set to Enable/true/1
    - unblocked : steam.cfg exists AND the line is set to False/0/no
    - unknown   : file missing OR no BootStrapperInhibitAll line found
    """
    try:
        steam_path = bridge._steam_path
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

def _bridge_steam_updates_set_state(bridge, action):
    """Write or update the BootStrapperInhibitAll line in
    <steam>/steam.cfg based on `action`.

    action = 'block'   sets BootStrapperInhibitAll=Enable
    action = 'unblock' sets BootStrapperInhibitAll=False

    Preserves any other lines already in steam.cfg. Creates the file
    when it doesn't exist. Returns the new state ('blocked', 'unblocked')
    on success, or an error message string on failure.
    """
    try:
        steam_path = bridge._steam_path
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

def _bridge_lumacore_check_update(bridge, _arg=""):
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
        from sff.lumacore.lumacore_setup import check_for_lumacore_update
        force = (str(_arg).strip().lower() == "force")
        data = check_for_lumacore_update(bridge._steam_path, force=force)
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

def _bridge_lumacore_deactivate(bridge):
    """Close Steam, remove LumaCore + dwmapi + lcoverlay DLLs, clear the
    installed-version cache. Emits lc_progress for each step and
    task_finished{auto_lc_deactivate} when done.
    """
    def _do():
        from sff.lumacore.lumacore_setup import deactivate_lumacore
        def _progress(msg):
            bridge.lc_progress.emit(msg)
        success, message = deactivate_lumacore(bridge._steam_path, _progress)
        return success, message

    def _on_done(result):
        success, message = result if isinstance(result, tuple) else (False, str(result))
        bridge._emit_task_result("auto_lc_deactivate", success, message)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_toggle_online_fix(bridge, app_id):
    """Toggle the LC Online Fix launch option for app_id in localconfig.vdf.

    Steam is automatically closed first when running, otherwise it would
    clobber the localconfig.vdf write on next shutdown.
    """
    def _do():
        from sff.game.launch_options import toggle_online_fix
        from sff.core.processes import SteamProcess, is_proc_running
        import time

        if sys.platform == "win32" and is_proc_running("steam.exe"):
            print("Closing Steam before toggling LC Online Fix...", flush=True)
            steam_proc = SteamProcess(bridge._steam_path) if bridge._steam_path else None
            if steam_proc:
                steam_proc.kill()
                waited = 0.0
                while is_proc_running("steam.exe") and waited < 10.0:
                    time.sleep(0.5)
                    waited += 0.5
                if is_proc_running("steam.exe"):
                    return False, "Steam did not close in time. Close it manually and try again."
                print("Steam closed.", flush=True)

        success, message = toggle_online_fix(bridge._ui.steam_path, app_id)
        return success, message

    def _on_done(result):
        success, message = result if isinstance(result, tuple) else (False, str(result))
        bridge._emit_task_result("lc_online_fix", success, message)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_get_launch_option_status(bridge, app_id):
    """Return a human-readable string describing the current LC Online Fix state for app_id."""
    try:
        from sff.game.launch_options import online_fix_enabled
        enabled = online_fix_enabled(bridge._ui.steam_path, app_id)
        return "LC Online Fix: enabled" if enabled else "LC Online Fix: disabled"
    except Exception as exc:
        return f"Error: {exc}"

# ── SYNC slots — fast, no I/O ────────────────────────────────

def _bridge_get_applist_games(bridge):
    """Returns JSON list of {app_id, name} for installed Steam games with saved .lua files."""
    try:
        from pathlib import Path as _Path
        saved_lua = _Path().cwd() / "saved_lua"
        saved_ids = {p.stem for p in saved_lua.glob("*.lua")} if saved_lua.exists() else set()
        installed = json.loads(bridge.get_installed_games())
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

def _bridge_get_platform(bridge):
    """Returns 'win32' or 'linux'."""
    return sys.platform

def _bridge_get_app_version(bridge):
    """Returns the current SteaMidra version string."""
    from sff.core.strings import VERSION
    return VERSION

def _bridge_app_update_check(bridge, _arg=""):
    """Return the current GitHub update status for the Settings button."""
    try:
        from sff.core.strings import VERSION
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

def _bridge_get_disk_usage(bridge, path):
    """Return disk usage JSON {total, used, free} for the given path."""
    import shutil
    import json as _json
    try:
        usage = shutil.disk_usage(path)
        return _json.dumps({"total": usage.total, "used": usage.used, "free": usage.free})
    except Exception:
        return _json.dumps({"error": True})

def _bridge_save_ryuu_key(bridge, key):
    """Save Ryuu API key to settings."""
    from sff.core.storage.settings import set_setting as _set
    from sff.core.structs import Settings
    try:
        _set(Settings.RYUU_KEY, key.strip())
        bridge.task_finished.emit(json.dumps({"task": "ryuu_key_saved", "success": True}))
    except Exception as e:
        logger.warning("Failed to save Ryuu key: %s", e)
        bridge._emit_task_result("ryuu_key_saved", False, f"Failed to save key: {e}")

def _bridge_test_ryuu_key(bridge):
    """Probe the Ryuu test/refresh endpoint with appid=440 to verify the saved key.

    Emits ``task_finished`` with task=``test_ryuu_key`` and a payload
    shaped like ``{ok: True}``, ``{ok: False, reason: 'appid not in db'}``,
    or ``{ok: False, status: <code>, body: <truncated_body>}``. When no
    key is configured we return ``{ok: False, reason: 'no_api_key'}``
    without firing any HTTP request — never send an empty ``auth_code``.
    """
    from sff.core.storage.settings import get_setting
    from sff.core.structs import Settings

    key = (get_setting(Settings.RYUU_KEY) or "").strip()
    if not key:
        bridge._emit_task_result(
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
        bridge._emit_task_result(
            "test_ryuu_key",
            bool(result.get("ok")),
            "",
            **{k: v for k, v in result.items() if k != "ok"},
            ok=bool(result.get("ok")),
        )

    bridge._run_async(_do, on_done=_on_done)

def _bridge_test_ryuu_api_key(bridge):
    """Test the premium Ryuu API key (X-Auth-Key header) against the requestupdate endpoint."""
    from sff.core.storage.settings import get_setting
    from sff.core.structs import Settings
    key = (get_setting(Settings.RYUU_API_KEY) or "").strip()
    if not key:
        bridge._emit_task_result("test_ryuu_api_key", False, "", ok=False, reason="no_api_key")
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
        bridge._emit_task_result("test_ryuu_api_key", bool(result.get("ok")), "",
            **{k: v for k, v in result.items() if k != "ok"}, ok=bool(result.get("ok")))
    bridge._run_async(_do, on_done=_on_done)

def _bridge_get_stored_api_key(bridge):
    """Returns saved API key from settings (may be empty)."""
    from sff.core.storage.settings import get_setting
    from sff.core.structs import Settings
    key = get_setting(Settings.HUBCAP_KEY)
    if key:
        bridge._api_key = key
    return key or ""

def _bridge_open_url(bridge, url):
    """Open a URL in the system default browser."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(url))

def _bridge_launch_game(bridge, app_id):
    app_id = str(app_id or "").strip()
    if not app_id.isdigit():
        bridge._emit_task_result("launch_game", False, f"Invalid App ID: {app_id!r}", app_id=app_id)
        return
    try:
        acf = bridge._resolve_acf(app_id)
        game_dir = Path(getattr(acf, "path", "") or "")
        if not game_dir.exists():
            raise FileNotFoundError("Installed game folder not found")

        # On Linux, always use Steam to launch — properly handles both
        # native ELF binaries and Proton/Wine .exe games with correct
        # compatibility tool settings.
        if sys.platform != "win32":
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            ok = QDesktopServices.openUrl(QUrl(f"steam://run/{app_id}"))
            bridge._emit_task_result(
                "launch_game",
                bool(ok),
                "Launch sent to Steam" if ok else "Could not launch game",
                app_id=app_id,
            )
            return

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
        bridge._emit_task_result("launch_game", True, f"Launched {exe.name}", app_id=app_id, path=str(exe))
    except Exception as exc:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        ok = QDesktopServices.openUrl(QUrl(f"steam://run/{app_id}"))
        bridge._emit_task_result(
            "launch_game",
            bool(ok),
            "Executable launch failed, sent launch to Steam" if ok else f"Could not launch game: {exc}",
            app_id=app_id,
        )

def _bridge_set_setting(bridge, key, value):
    """Set a setting by key name, then apply it live (same as classic UI)."""
    from sff.core.storage.settings import set_setting as _set
    from sff.core.structs import Settings
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
                    from sff.gui.bridges import store_bridge as _sb
                    _sb._STEAM_APPLIST_CACHE = None
                    _sb._STEAM_APPLIST_CACHE_TIME = 0.0
                    # Defence-in-depth: drop the Store grid cache so
                    # list_games rebuilds with the fresh toggle on
                    # the next round trip.
                    try:
                        from sff import store_browser as _sb
                        _sb._cached_grid = None
                    except Exception:
                        pass
                    from sff.core.utils import root_folder
                    _all_games = root_folder(outside_internal=True) / "all_games.txt"
                    if _all_games.exists():
                        _all_games.unlink()
                except Exception as _e:
                    logger.debug("store_show_software cache flush failed: %s", _e)
            # Apply live so changes take effect immediately
            parent = bridge.parent()
            if parent and hasattr(parent, '_apply_setting_live'):
                try:
                    parent._apply_setting_live(s)
                except Exception as e:
                    logger.warning("_apply_setting_live(%s) failed: %s", key, e)
            return

def _bridge_get_setting(bridge, key):
    """Get a setting by key name."""
    from sff.core.storage.settings import get_setting as _get
    from sff.core.structs import Settings
    for s in Settings:
        if s.key_name == key or s.name.lower() == key.lower():
            val = _get(s)
            return str(val) if val is not None else ""
    return ""

def _bridge_provider_contribute_preview(bridge):
    """Return a privacy-safe count of keys that would be submitted."""
    try:
        from sff.lua.provider import collect_submit_candidates

        data = collect_submit_candidates(bridge._steam_path)
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

def _bridge_provider_contribute_submit(bridge, mode="manual"):
    """Submit clean provider keys in the background."""
    def _do():
        from sff.lua.provider import (
            collect_submit_candidates,
            enrich_submit_items_with_steam_appinfo,
            mark_contributor_run,
            submit_items,
        )
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings

        data = collect_submit_candidates(bridge._steam_path)
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
        bridge._emit_task_result(
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

    bridge._run_async(_do, on_done=_on_done)

def _bridge_provider_reset_submitted(bridge):
    """Clear the submitted-keys tracking so all keys can be resubmitted."""
    try:
        from sff.lua.provider import reset_contributor_state
        reset_contributor_state()
        bridge._emit_task_result("provider_reset", True, "Submitted keys tracking has been reset. All keys can now be resubmitted.")
    except Exception as e:
        bridge._emit_task_result("provider_reset", False, str(e))

def _bridge_provider_update_now(bridge):
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
        bridge._emit_task_result("provider_update", ok, msg, **result)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_get_provider_cache_status(bridge):
    try:
        from sff.lua.provider import provider_file_candidates, provider_update_state

        data = provider_update_state()
        # This slot is called synchronously by QWebChannel.  Loading the
        # provider here used to parse, validate and sort a ~65 MB JSON file on
        # Qt's GUI thread merely to display an entry count.  Opening Store then
        # looked completely frozen for several seconds.  A stat is enough for
        # the status badge; the provider itself is only loaded by operations
        # that actually need its keys.
        candidates = [path for path in provider_file_candidates() if path.exists()]
        data["available"] = bool(candidates)
        data["size_bytes"] = max((path.stat().st_size for path in candidates), default=0)
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

def _bridge_linux_setup_now(bridge):
    """Rerun Linux SLSsteam and .NET setup."""
    def _do():
        if not sys.platform.startswith("linux"):
            return (False, "Linux setup is only available on Linux.")
        log_lines: list[str] = []
        try:
            from pathlib import Path as _Path
            from sff.linux.slssteam import detect_steam_type, install_from_github, setup_via_headcrab
            from sff.downloads.dotnet_utils import ensure_dotnet_9

            bridge.download_progress.emit(json.dumps({"status": "Detecting Steam installation...", "progress": 5}))
            if detect_steam_type() == "flatpak":
                steam_path = _Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam"
            else:
                steam_path = _Path.home() / ".steam" / "steam"
            bridge.download_progress.emit(json.dumps({"status": "Running headcrab setup...", "progress": 20}))
            ok = setup_via_headcrab(steam_path, log_lines.append)
            if not ok:
                bridge.download_progress.emit(json.dumps({"status": "headcrab failed, installing SLSsteam directly...", "progress": 50}))
                log_lines.append("headcrab failed, falling back to direct SLSsteam install...")
                install_from_github(steam_path, log_lines.append)
            bridge.download_progress.emit(json.dumps({"status": "Migrating existing games...", "progress": 70}))
            # Migrate any existing games from ACCELA or other tools
            try:
                from sff.linux.slssteam import migrate_existing_games
                migrated = migrate_existing_games(log_lines.append)
                if migrated:
                    log_lines.append(f"Migrated {migrated} existing game(s) to SLSsteam config.")
            except Exception as _mig_err:
                pass
            bridge.download_progress.emit(json.dumps({"status": "Ensuring .NET 9 runtime...", "progress": 85}))
            ensure_dotnet_9(print_fn=log_lines.append)
            return (True, "\n".join(str(x) for x in log_lines) or "Linux setup completed.")
        except Exception as exc:
            logger.exception("linux_setup_now failed: %s", exc)
            return (False, str(exc))

    def _on_done(result):
        ok, msg = result if isinstance(result, tuple) else (False, "Linux setup failed")
        bridge._emit_task_result("linux_setup", ok, msg)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_fix_slssteam_hash(bridge):
    """Fix 'Unknown steamclient.so hash' error via headcrab reset + repatch."""
    def _do():
        if not sys.platform.startswith("linux"):
            return (False, "Hash fix is only available on Linux.")
        log_lines: list[str] = []
        try:
            from pathlib import Path as _Path
            from sff.linux.slssteam import detect_steam_type, fix_hash_mismatch

            if detect_steam_type() == "flatpak":
                steam_path = _Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam"
            else:
                steam_path = _Path.home() / ".steam" / "steam"
            ok = fix_hash_mismatch(steam_path, log_lines.append)
            return (ok, "\n".join(str(x) for x in log_lines) or ("Hash issue fixed." if ok else "Hash fix failed."))
        except Exception as exc:
            logger.exception("fix_slssteam_hash failed: %s", exc)
            return (False, str(exc))

    def _on_done(result):
        ok, msg = result if isinstance(result, tuple) else (False, "Hash fix failed")
        bridge._emit_task_result("fix_slssteam_hash", ok, msg)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_get_webui_translations(bridge, lang):
    """Return the webui translation JSON for the given language."""
    from sff.core.utils import root_folder
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

def _bridge_get_steam_libraries(bridge):
    """Returns JSON array of Steam library paths."""
    from sff.core.storage.vdf import get_steam_libs
    if not bridge._steam_path:
        return "[]"
    try:
        libs = get_steam_libs(bridge._steam_path)
        return json.dumps([str(p) for p in libs])
    except Exception:
        return "[]"

def _bridge_set_active_library(bridge, path):
    """Sets the library path for the next download."""
    bridge._active_library = path

def _bridge_browse_ddmod_download_folder(bridge):
    """Open a folder picker for DDMod's direct-download destination."""
    start_dir = ""
    try:
        start_dir = str(bridge._active_library or bridge._steam_path or "")
    except Exception:
        start_dir = ""
    path = QFileDialog.getExistingDirectory(
        bridge.parent(),
        "Select DDMod Download Location",
        start_dir,
    )
    return path or ""

def _bridge_browse_steam_path(bridge, _unused=""):
    """Folder picker for the Steam install root. Validates the pick and
    returns the chosen path on success, '' on cancel or invalid pick.
    Updates `bridge._steam_path` so every other slot picks up the new
    path immediately, then returns it so the frontend can persist it
    through `set_setting('steam_path')` for next launch."""
    from sff.steam_path import validate_steam_path

    parent = bridge.parent()
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
    # everything else that reads bridge._steam_path uses the new value
    # without needing a process restart. Also drop the games cache
    # so the next list call re-walks the new install.
    bridge._steam_path = resolved
    try:
        bridge._installed_games_cache = None
    except Exception:
        pass
    return str(resolved)

def _bridge_open_file_dialog(bridge):
    """Opens native QFileDialog, returns selected path."""
    parent = bridge.parent()
    path = QFileDialog.getExistingDirectory(parent, "Select Folder")
    return path or ""

def _bridge_open_archive_dialog(bridge):
    """Opens a file picker for ZIP/RAR/7z archives. Returns selected file path."""
    path, _ = QFileDialog.getOpenFileName(
        bridge.parent(),
        "Select Archive",
        "",
        "Archives (*.zip *.rar *.7z);;All Files (*)",
    )
    return path or ""

def _bridge_open_exe_file_dialog(bridge):
    """Opens a file picker for executables. Returns selected file path."""
    path, _ = QFileDialog.getOpenFileName(
        bridge.parent(),
        "Select Executable",
        "",
        "Executables (*.exe);;All Files (*)",
    )
    return path or ""

def _bridge_browse_image_file(bridge):
    """Opens a native file picker filtered to PNG/JPG/JPEG images. Returns selected path or ''."""
    from PyQt6.QtWidgets import QFileDialog as _QFD
    path, _ = _QFD.getOpenFileName(
        bridge.parent(),
        "Select Avatar Image",
        "",
        "Image Files (*.png *.jpg *.jpeg)",
    )
    return path or ""

def _bridge_browse_custom_background_file(bridge):
    path, _ = QFileDialog.getOpenFileName(
        bridge.parent(),
        "Select Background Image",
        "",
        "Image Files (*.png *.jpg *.jpeg *.webp)",
    )
    return path or ""

def _bridge_export_settings_file(bridge):
    try:
        from sff.core.storage.settings import export_settings

        path, _ = QFileDialog.getSaveFileName(
            bridge.parent(),
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

def _bridge_import_settings_file(bridge):
    try:
        from sff.core.storage.settings import import_settings

        path, _ = QFileDialog.getOpenFileName(
            bridge.parent(),
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

def _bridge_import_depot_manifest_html(bridge):
    try:
        from sff.manifest.html_manifest_import import (
            flatten_manifest_groups,
            format_manifest_entries,
            parse_depot_manifest_html_files,
        )

        paths, _ = QFileDialog.getOpenFileNames(
            bridge.parent(),
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

def _bridge_set_custom_background(bridge, source_path):
    try:
        from sff.core.storage.settings import set_setting
        from sff.core.structs import Settings
        from sff.core.utils import sff_data_dir

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

def _bridge_clear_custom_background(bridge):
    try:
        from sff.core.storage.settings import clear_setting
        from sff.core.structs import Settings
        from sff.core.utils import sff_data_dir

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

def _bridge_open_lua_file_dialog(bridge):
    """Opens a file picker for Lua files. Returns selected file path."""
    path, _ = QFileDialog.getOpenFileName(
        bridge.parent(),
        "Select Lua File",
        "",
        "Lua/Archive Files (*.lua *.zip *.rar *.7z);;All Files (*)",
    )
    return path or ""

def _bridge_open_manifest_folder_dialog(bridge):
    """Opens a folder picker for selecting a directory containing .manifest files."""
    path = QFileDialog.getExistingDirectory(
        bridge.parent(),
        "Select Manifest Folder",
        "",
    )
    return path or ""

# ── A12 Bulk Import bridge slots ─────────────────────────────
#
# Folder Scan, Drag-and-Drop, and Batch Queue all funnel into the
# same singleton BulkImportQueue so per-file dedupe works across the
# three surfaces. Single-file imports never touch this code path.

def _bridge_open_folder_scan(bridge):
    """Open a native dir picker, walk recursively, validate `.lua`/
    `.manifest` candidates, and enqueue the valid ones into the
    singleton BulkImportQueue. Auto-starts the drain when
    BULK_IMPORT_MODE is `process_immediately`.
    """
    parent = bridge.parent()
    folder = QFileDialog.getExistingDirectory(parent, "Select Folder")
    if not folder:
        return

    def _do():
        from sff.gui.bulk_import import BulkImportQueue

        queue = bridge._get_bulk_import_queue()
        files = BulkImportQueue.collect_from_folder(Path(folder))
        queue.enqueue_files(files)
        bridge._maybe_drain_queue(queue)
        return queue.summary()

    def _on_done(summary):
        bridge._emit_bulk_summary("folder_scan", summary)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_enqueue_dropped_files(bridge, files_json):
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
        queue = bridge._get_bulk_import_queue()
        queue.enqueue_files(Path(p) for p in paths if p)
        bridge._maybe_drain_queue(queue)
        return queue.summary()

    def _on_done(summary):
        bridge._emit_bulk_summary("drop", summary)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_enqueue_dropped_blobs(bridge, blobs_json):
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
        from sff.core.utils import sff_data_dir

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
            from sff.gui.web_bridge import _UNSAFE_FILENAME_RE
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
        queue = bridge._get_bulk_import_queue()
        queue.enqueue_files(iter(paths))
        bridge._maybe_drain_queue(queue)
        return queue.summary()

    def _on_done(summary):
        bridge._emit_bulk_summary("drop", summary)

    bridge._run_async(_do, on_done=_on_done)

def _bridge_run_bulk_import(bridge):
    """Start the queue drain. Used by the `collect_then_confirm` mode
    where files are queued first and the user clicks a Run button to
    kick off processing.
    """
    def _do():
        queue = bridge._get_bulk_import_queue()
        return queue.drain()

    def _on_done(summary):
        bridge._emit_bulk_summary("run", summary)
        bridge._reset_bulk_import_queue()

    bridge._run_async(_do, on_done=_on_done)

def _bridge_cancel_bulk_import(bridge):
    """Raise the cancel signal on the in-flight queue. The current
    file finishes its pipeline cleanly; no new files are dequeued.
    """
    queue = getattr(bridge, "_bulk_import_queue", None)
    if queue is not None:
        queue.cancel()
    bridge._emit_task_result("bulk_import", False, "Bulk import cancelled")

def _bridge_get_recent_lua_files(bridge):
    """Returns JSON array of recent Lua files [{name, path}, ...] from RecentFilesManager."""
    try:
        from sff.recent_files import get_recent_files_manager
        mgr = get_recent_files_manager()
        files = mgr.get_all()
        return json.dumps([{"name": p.name, "path": str(p)} for p in files])
    except Exception as e:
        logger.warning("get_recent_lua_files failed: %s", e)
        return "[]"

def _bridge_get_games_file_info(bridge):
    """Return all_games.txt status as JSON {exists, mtime_str, count}."""
    from sff.core.utils import root_folder
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

def _bridge_get_storage_paths(bridge):
    """Return paths where luas and manifests are stored for manual cleanup."""
    try:
        steam = str(bridge._steam_path) if bridge._steam_path else ""
        from sff.core.utils import sff_data_dir, manifests_staging_dir
        return json.dumps({
            "lua_plugin": f"{steam}/config/stplug-in/" if steam else "",
            "depotcache": f"{steam}/depotcache/" if steam else "",
            "config_depotcache": f"{steam}/config/depotcache/" if steam else "",
            "staging": str(manifests_staging_dir()),
        })
    except Exception:
        return json.dumps({})

def _bridge_update_games_file(bridge):
    """Download full Steam app list and write all_games.txt. Emits task_finished('update_games_file')."""
    def _do():
        try:
            from sff.core.utils import root_folder
            from sff.core.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
            from sff.core.storage.settings import get_setting
            from sff.core.structs import Settings
            import urllib.request as _req
            import json as _json
            from sff.gui.web_bridge import _should_show_software, _get_ssl_ctx
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
        except urllib.error.HTTPError as e:
            if e.code == 403:
                msg = (
                    "Steam Web API key rejected (403 Forbidden). "
                    "The default API key may have been revoked by Valve. "
                    "Set your own Steam Web API key in Settings > Developer "
                    "or wait for the next update."
                )
                logger.warning(msg)
                return (False, msg)
            logger.exception("update_games_file failed: %s", e)
            return (False, str(e))
        except Exception as e:
            logger.exception("update_games_file failed: %s", e)
            return (False, str(e))

    def _on_done(result):
        if isinstance(result, int):
            bridge._emit_task_result("update_games_file", True, f"Game list updated: {result} games")
        elif isinstance(result, tuple) and not result[0]:
            bridge._emit_task_result("update_games_file", False, f"Failed: {result[1]}")
        else:
            bridge._emit_task_result("update_games_file", False, "Failed to update game list")

    bridge._run_async(_do, on_done=_on_done)

def _bridge_get_avatar_base64(bridge):
    """Read the global GBE avatar from GSE Saves/settings/ and return a base64 data URL.
    Returns empty string if no avatar is set."""
    import base64
    from sff.game.fix_game.config_generator import _get_gbe_saves_root
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

def _bridge_set_global_avatar(bridge, source_path):
    """Copy source_path to GSE Saves/settings/account_avatar.{ext}.
    Removes any existing avatar files with other extensions first.
    Returns 'ok' on success or an error message."""
    import shutil
    from sff.game.fix_game.config_generator import _get_gbe_saves_root
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

def _bridge__scan_installed_games(bridge):
    """Walk all Steam libraries and return JSON string of installed games.
    Runs on a background thread -- safe to call from _prefetch_installed_games."""
    if not bridge._steam_path:
        logger.warning("_scan_installed_games: bridge._steam_path is None")
        return "[]"
    from sff.core.storage.vdf import get_steam_libs
    import os
    from sff.gui.web_bridge import _collect_steamidra_managed_sources
    managed_sources = _collect_steamidra_managed_sources(bridge._steam_path)

    libs = list(get_steam_libs(bridge._steam_path))
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

def _bridge_get_fix_game_list(bridge):
    """Returns JSON list of games available for fixing."""
    return bridge.get_installed_games()

def _bridge_toggle_music(bridge):
    """Toggle background music on/off."""
    parent = bridge.parent()
    if parent and hasattr(parent, '_toggle_mute'):
        parent._toggle_mute()

def _bridge_get_gse_identity(bridge):
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

def _bridge_get_all_settings(bridge):
    """Returns JSON object with all current settings for the Settings page."""
    from sff.core.storage.settings import load_all_settings
    from sff.core.structs import Settings
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

def _bridge_get_game_list(bridge):
    """Returns JSON list of games from all Steam libraries (name + app_id + path).
    Same scan as get_installed_games but always includes path."""
    return bridge.get_installed_games()

def _bridge_fetch_library_images(bridge, app_ids_json):
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
            for app_id, url in getattr(bridge, "_library_image_cache", {}).items()
            if str(app_id).isdigit() and url
        }
        missing = [app_id for app_id in app_ids if str(app_id) not in bridge._library_image_cache]
        if missing:
            from sff.gui.bridges.store_bridge import _fetch_steam_image_urls
            fresh, _, _ = _fetch_steam_image_urls(missing)
            for app_id, url in fresh.items():
                if url:
                    bridge._library_image_cache[str(app_id)] = url
                    bridge._library_image_cache.move_to_end(str(app_id))
                    while len(bridge._library_image_cache) > bridge._LIBRARY_IMAGE_CACHE_MAX:
                        bridge._library_image_cache.popitem(last=False)
            cached.update(fresh)
        return cached

    def _on_done(result):
        bridge.task_finished.emit(json.dumps({
            "task": "library_images",
            "success": True,
            "images": {str(k): v for k, v in result.items()},
        }))

    bridge._run_async(_do, on_done=_on_done)

def _bridge_load_library(bridge):
    """Async: scan installed games + fetch Steam API image URLs in one pass.
    Emits task_finished with task='library_loaded' and games=[{...}].
    Mirrors search_games so image_url is ready before card rendering.
    """
    def _do():
        games = json.loads(bridge.get_installed_games())
        if not games:
            return []
        app_ids = [g["app_id"] for g in games if g.get("app_id")]
        cached = getattr(bridge, "_library_image_cache", {})
        missing = [int(app_id) for app_id in app_ids if str(app_id) not in cached]
        if missing:
            from sff.gui.bridges.store_bridge import _fetch_steam_image_urls
            image_urls, _, _ = _fetch_steam_image_urls(missing)
            for img_appid, url in image_urls.items():
                if url:
                    cached[str(img_appid)] = url
        for g in games:
            g["image_url"] = cached.get(str(g["app_id"]))
        return games

    def _on_done(games):
        bridge.task_finished.emit(json.dumps({
            "task": "library_loaded",
            "success": True,
            "games": games or [],
        }))

    bridge._run_async(_do, on_done=_on_done)

def _bridge_refresh_library(bridge):
    bridge._installed_games_cache = None
    bridge.load_library()

def _bridge_delete_game(bridge, app_id, game_path, mode):
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
        if bridge._steam_path:
            try:
                from sff.steam_tools_compat import remove_lua_from_steam
                remove_lua_from_steam(bridge._steam_path, app_id_int)
                lua_removed = True
            except Exception as e:
                logger.warning("delete_game: stplug-in Lua removal failed: %s", e)
            # Also remove from saved_lua/ cache
            try:
                saved_path = Path.cwd() / "saved_lua" / f"{app_id_int}.lua"
                if saved_path.exists():
                    saved_path.unlink()
                    logger.info("delete_game: removed saved_lua cache %s", saved_path)
            except Exception:
                pass

        if mode != "full":
            if lua_removed:
                return (True, "Removed from library. If the game still shows in Steam, restart Steam (or run Auto LC Setup if you haven't yet).")
            return (True, "Removed from library")

        # mode='full' also wipes the ACF manifest + the game folder.
        files_deleted = False

        if bridge._steam_path:
            try:
                from sff.core.storage.vdf import get_steam_libs
                for lib in get_steam_libs(bridge._steam_path):
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
            bridge._emit_task_result("delete_game", ok, msg, app_id=app_id)
        else:
            bridge._emit_task_result("delete_game", False, "Delete failed", app_id=app_id)

    bridge._run_async(_do, on_done=_on_done)

# ── Google Drive auth ─────────────────────────────────────────

def _bridge_dump_achievement_diagnostic(bridge):
    """A16: surface the LumaCore achievement diagnostic ring buffer.

    LumaCore writes <sff_data_dir>/lumacore_diag.txt on detach (and on
    any future menu-triggered dump path). This slot reads the file if
    present and returns its contents, capped to the last 16 KB so the
    Web UI / dialog stays responsive. Returns an empty string when
    the file does not exist yet (LumaCore writes on detach, so a
    running session sees nothing until Steam restarts).
    """
    try:
        from sff.core.utils import sff_data_dir
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
