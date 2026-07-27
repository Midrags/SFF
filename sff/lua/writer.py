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


import os
import shutil
import time

from dataclasses import dataclass

from pathlib import Path

import sys

from typing import Optional


from pathvalidate import sanitize_filename


from sff.http_utils import get_game_name

from sff.prompts import prompt_confirm

from sff.storage.vdf import VDFLoadAndDumper, vdf_dump, vdf_load

from sff.structs import LuaParsedInfo

from sff.utils import enter_path

import logging


logger = logging.getLogger(__name__)


def _normalise_manifest_map(manifest_map: Optional[dict]) -> dict[str, str]:
    if not manifest_map:
        return {}
    clean: dict[str, str] = {}
    for depot_id, manifest_id in manifest_map.items():
        depot_str = str(depot_id).strip()
        manifest_str = str(manifest_id).strip()
        if depot_str.isdigit() and manifest_str.isdigit():
            clean[depot_str] = manifest_str
    return clean


def _manifest_map_for_lua(lua: LuaParsedInfo, manifest_override: Optional[dict]) -> dict[str, str]:
    return _normalise_manifest_map(manifest_override) or _normalise_manifest_map(
        getattr(lua, "manifest_overrides", {}) or {}
    )


@dataclass

class ACFWriter:

    steam_lib_path: Path

    def write_acf(
        self,
        lua: LuaParsedInfo,
        manifest_override: Optional[dict] = None,
        buildid: str = "0",
        size_on_disk: int = 0,
    ):
        # On Windows, LumaCore manages app ownership — ACF writing is not needed
        # and can cause Steam to show "Purchase" on secondary accounts.
        if sys.platform == "win32":
            logger.debug("write_acf: skipped on Windows (LumaCore handles ownership)")
            return

        acf_file = self.steam_lib_path / f"steamapps/appmanifest_{lua.app_id}.acf"
        do_write_acf = True
        if acf_file.exists():
            do_write_acf = not prompt_confirm(
                ".acf file found. Are you updating a game you already have installed"
                " or is this a new installation?",
                true_msg="Update",
                false_msg="New",
            )
        if do_write_acf:
            app_name = get_game_name(lua.app_id)
            app_id_str = str(lua.app_id)
            installdir = sanitize_filename(app_name).replace("'", "").strip()
            manifest_map = _manifest_map_for_lua(lua, manifest_override)
            acf_file.parent.mkdir(parents=True, exist_ok=True)
            if not installdir:
                installdir = app_id_str
                print(
                    f"Warning: could not determine install directory name. "
                    f"Using '{installdir}' as fallback — rename the folder manually if needed."
                )
            print(f"installdir will be set to: {installdir}")
            app_state: dict = {
                "appid": app_id_str,
                "Universe": "1",
                "name": app_name,
                "StateFlags": "4",
                "installdir": installdir,
                "LastUpdated": str(int(time.time())),
                "lastupdated": str(int(time.time())),
                "SizeOnDisk": str(size_on_disk),
                "StagingSize": "0",
                "buildid": str(buildid),
                "UpdateResult": "0",
                "BytesToDownload": str(size_on_disk),
                "BytesDownloaded": str(size_on_disk),
                "BytesToStage": "0",
                "BytesStaged": "0",
                "TargetBuildID": str(buildid),
                "AutoUpdateBehavior": "0",
                "AllowOtherDownloadsWhileRunning": "0",
                "ScheduledAutoUpdate": "0",
                "DownloadType": "1",
            }
            if manifest_map:
                depot_list = list(manifest_map.items())
                installed = {}
                mounted = {}
                for i, (depot_id, manifest_id) in enumerate(depot_list):
                    depot_size = str(size_on_disk) if i == 0 and size_on_disk else "0"
                    installed[str(depot_id)] = {"manifest": str(manifest_id), "size": depot_size}
                    mounted[str(depot_id)] = str(manifest_id)
                app_state["InstalledDepots"] = installed
                app_state["MountedDepots"] = mounted
                print(
                    f"InstalledDepots set for {len(manifest_map)} depot(s) -> "
                    + ", ".join(
                        f"{d}:{m}" for d, m in list(manifest_map.items())[:3]
                    )
                    + ("..." if len(manifest_map) > 3 else "")
                )
            acf_contents = {"AppState": app_state}
            vdf_dump(acf_file, acf_contents)
            try:
                os.chmod(acf_file, 0o444)
            except OSError:
                pass
            print(f"Wrote .acf file to {acf_file}")
        else:
            # Clear stale error state so Steam doesn't keep retrying a
            # failed update — this is what causes "NO INTERNET CONNECTION"
            self._patch_acf_error_state(acf_file)

    def write_acf_direct(
        self,
        lua: LuaParsedInfo,
        manifest_override: Optional[dict] = None,
        size_on_disk: int = 0,
        buildid: str = "0",
        empty_depots: bool = False,
    ):
        # On Windows, LumaCore manages app ownership — ACF writing is not needed.
        if sys.platform == "win32":
            logger.debug("write_acf_direct: skipped on Windows (LumaCore handles ownership)")
            return
        app_name = get_game_name(lua.app_id)
        app_id_str = str(lua.app_id)
        installdir = sanitize_filename(app_name).replace("'", "").strip()
        manifest_map = _manifest_map_for_lua(lua, manifest_override)
        if not installdir:
            installdir = app_id_str
            print(
                f"Warning: could not determine install directory name. "
                f"Using '{installdir}' as fallback — rename the folder manually if needed."
            )
        print(f"installdir will be set to: {installdir}")
        acf_file = self.steam_lib_path / f"steamapps/appmanifest_{lua.app_id}.acf"
        acf_file.parent.mkdir(parents=True, exist_ok=True)
        app_state: dict = {
            "appid": app_id_str,
            "Universe": "1",
            "name": app_name,
            "StateFlags": "4",
            "installdir": installdir,
            "LastUpdated": str(int(time.time())),
            "lastupdated": str(int(time.time())),
            "SizeOnDisk": str(size_on_disk),
            "StagingSize": "0",
            "buildid": str(buildid),
            "UpdateResult": "0",
            "BytesToDownload": str(size_on_disk),
            "BytesDownloaded": str(size_on_disk),
            "BytesToStage": "0",
            "BytesStaged": "0",
            "TargetBuildID": str(buildid),
            "AutoUpdateBehavior": "0",
            "AllowOtherDownloadsWhileRunning": "0",
            "ScheduledAutoUpdate": "0",
            "DownloadType": "1",
        }
        if manifest_map:
            if empty_depots:
                app_state["InstalledDepots"] = {}
            else:
                depot_list = list(manifest_map.items())
                installed = {}
                mounted = {}
                for i, (depot_id, manifest_id) in enumerate(depot_list):
                    depot_size = str(size_on_disk) if i == 0 and size_on_disk else "0"
                    installed[str(depot_id)] = {"manifest": str(manifest_id), "size": depot_size}
                    mounted[str(depot_id)] = str(manifest_id)
                app_state["InstalledDepots"] = installed
                app_state["MountedDepots"] = mounted
            if sys.platform != "win32":
                app_state["UserConfig"] = {
                    "platform_override_dest": "linux",
                    "platform_override_source": "windows",
                }
                app_state["MountedConfig"] = {
                    "platform_override_dest": "linux",
                    "platform_override_source": "windows",
                }
            print(
                f"InstalledDepots set for {len(manifest_map)} depot(s) -> "
                + ", ".join(
                    f"{d}:{m}" for d, m in list(manifest_map.items())[:3]
                )
                + ("..." if len(manifest_map) > 3 else "")
            )
        acf_contents = {"AppState": app_state}
        vdf_dump(acf_file, acf_contents)
        try:
            os.chmod(acf_file, 0o444)
        except OSError:
            pass
        print(f"Wrote .acf file to {acf_file}")

    @staticmethod

    def _patch_acf_error_state(acf_file: Path):

        try:
            data = vdf_load(acf_file)
            app_state = data.get("AppState", {})
            patched = False
            for key, clean_val in [
                ("UpdateResult", "0"),
                ("FullValidateAfterNextUpdate", "0"),
                ("ScheduledAutoUpdate", "0"),
                ("BytesToDownload", "0"),
                ("BytesDownloaded", "0"),
                ("BytesToStage", "0"),
                ("BytesStaged", "0"),
                ("StagingSize", "0"),
            ]:
                if app_state.get(key) != clean_val:
                    app_state[key] = clean_val
                    patched = True
            try:
                flags = int(app_state.get("StateFlags", "0"))
                if flags & 16:
                    app_state["StateFlags"] = str(flags & ~16)
                    patched = True
            except (ValueError, TypeError):
                pass
            if patched:
                vdf_dump(acf_file, data)
                try:
                    os.chmod(acf_file, 0o444)
                except OSError:
                    pass
                print("Patched .acf error state (cleared UpdateResult / validation flags)")
            else:
                print("Skipped writing to .acf file (no stale error state)")
        except Exception as e:
            logger.warning("Could not patch ACF error state: %s", e)
            print("Skipped writing to .acf file")

    def patch_workshop_acf(self, lua: LuaParsedInfo):

        # Steam runs a Workshop update after validating the game.  If the
        # workshop ACF has NeedsDownload=1 the update will try to fetch
        # workshop manifests the account can't access → "NO INTERNET
        # CONNECTION".  Clear the flag when no workshop content is
        # actually installed (SizeOnDisk=0).
        ws_dir = self.steam_lib_path / "steamapps" / "workshop"
        ws_acf = ws_dir / f"appworkshop_{lua.app_id}.acf"
        if not ws_acf.exists():
            return
        try:
            data = vdf_load(ws_acf)
            ws = data.get("AppWorkshop", {})
            needs_dl = ws.get("NeedsDownload", "0")
            size_on_disk = ws.get("SizeOnDisk", "0")
            if needs_dl != "1":
                return
            # Only wipe when nothing is actually installed
            if size_on_disk not in ("0", ""):
                return
            ws["NeedsDownload"] = "0"
            ws["NeedsUpdate"] = "0"
            # The items aren't installed (SizeOnDisk=0), so tracking
            # them just causes repeated "Access Denied" failures.
            if "WorkshopItemDetails" in ws:
                ws["WorkshopItemDetails"] = {}
            vdf_dump(ws_acf, data)
            try:
                os.chmod(ws_acf, 0o444)
            except OSError:
                pass
            print(
                f"Patched workshop ACF — cleared NeedsDownload to prevent "
                f"'NO INTERNET CONNECTION' ({ws_acf.name})"
            )
        except Exception as e:
            logger.warning("Could not patch workshop ACF: %s", e)

    def patch_acf_depot_manifests(self, acf_file: Path, manifest_map: dict):
        """Update InstalledDepots and MountedDepots in-place with new manifest GIDs.

        Preserves SizeOnDisk, installdir, StateFlags, and all other existing fields.
        Also clears stale update-error flags. Used by update_all_manifests so that
        Steam does not report '0 B installed' after new manifest GIDs are downloaded.
        """
        if not manifest_map:
            return
        try:
            data = vdf_load(acf_file)
            app_state = data.get("AppState", {})
            installed = app_state.get("InstalledDepots", {})
            for depot_id, manifest_id in manifest_map.items():
                depot_str = str(depot_id)
                manifest_str = str(manifest_id)
                entry = installed.get(depot_str)
                if isinstance(entry, dict):
                    entry["manifest"] = manifest_str
                else:
                    installed[depot_str] = {"manifest": manifest_str, "size": "0"}
            app_state["InstalledDepots"] = installed
            if sys.platform == "win32":
                app_state["MountedDepots"] = {
                    str(d): str(m) for d, m in manifest_map.items()
                }
            for key, clean_val in [
                ("UpdateResult", "0"),
                ("FullValidateAfterNextUpdate", "0"),
                ("ScheduledAutoUpdate", "0"),
            ]:
                if app_state.get(key, clean_val) != clean_val:
                    app_state[key] = clean_val
            data["AppState"] = app_state
            vdf_dump(acf_file, data)
            try:
                os.chmod(acf_file, 0o444)
            except OSError:
                pass
            print(
                f"Patched InstalledDepots for {len(manifest_map)} depot(s) in {acf_file.name}"
            )
        except Exception as e:
            logger.warning("Could not patch ACF depot manifests for %s: %s", acf_file, e)


@dataclass

class ConfigVDFWriter:

    steam_path: Path

    def add_decryption_keys_to_config(self, lua: LuaParsedInfo):

        vdf_file = self.steam_path / "config/config.vdf"
        try:
            shutil.copyfile(vdf_file, (self.steam_path / "config/config.vdf.backup"))
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.warning("Could not back up config.vdf (Steam may be running): %s", e)
        with VDFLoadAndDumper(vdf_file) as vdf_data:
            for pair in lua.depots:
                depot_id = pair.depot_id
                dec_key = pair.decryption_key
                if dec_key == "":
                    logger.debug(f"Skipping {depot_id} because it's not a depot")
                    continue
                print(
                    f"Depot {depot_id} has decryption key {dec_key}... ",
                    end="",
                    flush=True,
                )
                depots = enter_path(
                    vdf_data,
                    "InstallConfigStore",
                    "Software",
                    "Valve",
                    "Steam",
                    "depots",
                    mutate=True,
                    ignore_case=True,
                )
                if depot_id not in depots:
                    depots[depot_id] = {"DecryptionKey": dec_key}
                    print("Added to config.vdf successfully.")
                else:
                    print("Already in config.vdf.")

    def remove_decryption_keys(self, depot_ids: list) -> int:
        vdf_file = self.steam_path / "config/config.vdf"
        shutil.copyfile(vdf_file, (self.steam_path / "config/config.vdf.backup"))
        removed = 0
        with VDFLoadAndDumper(vdf_file) as vdf_data:
            depots = enter_path(
                vdf_data,
                "InstallConfigStore",
                "Software",
                "Valve",
                "Steam",
                "depots",
                mutate=True,
                ignore_case=True,
            )
            for depot_id in depot_ids:
                depot_id_str = str(depot_id)
                if depot_id_str in depots:
                    del depots[depot_id_str]
                    removed += 1
        return removed

    def ids_in_config(self, ids: list[int]):

        vdf_file = self.steam_path / "config/config.vdf"
        data = vdf_load(vdf_file)
        depots = enter_path(
            data,
            "InstallConfigStore",
            "Software",
            "Valve",
            "Steam",
            "depots",
            mutate=True,
            ignore_case=True,
        )
        return {x: (str(x) in depots) for x in ids}
