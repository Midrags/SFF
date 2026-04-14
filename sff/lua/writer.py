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

import shutil
from dataclasses import dataclass
from pathlib import Path

from pathvalidate import sanitize_filename

from sff.http_utils import get_game_name
from sff.prompts import prompt_confirm
from sff.storage.vdf import VDFLoadAndDumper, vdf_dump, vdf_load
from sff.structs import LuaParsedInfo
from sff.utils import enter_path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ACFWriter:
    steam_lib_path: Path

    def write_acf(self, lua: LuaParsedInfo):
        acf_file = self.steam_lib_path / f"steamapps/appmanifest_{lua.app_id}.acf"
        do_write_acf = True
        if acf_file.exists():
            do_write_acf = not prompt_confirm(
                ".acf file found. Are you updating a game you already have installed"
                " or is this a new installation?",
                true_msg="I'm updating a game",
                false_msg="This is a new installation (Overwrites the .acf file, i.e., "
                "resets the status of the game)",
            )

        if do_write_acf:
            app_name = get_game_name(lua.app_id)
            app_id_str = str(lua.app_id)
            installdir = sanitize_filename(app_name).replace("'", "").strip()
            if not installdir:
                installdir = app_id_str
                print(
                    f"Warning: could not determine install directory name. "
                    f"Using '{installdir}' as fallback — rename the folder manually if needed."
                )
            print(f"installdir will be set to: {installdir}")
            acf_contents: dict[str, dict[str, str]] = {
                "AppState": {
                    "appid": app_id_str,
                    "Universe": "1",
                    "name": app_name,
                    "StateFlags": "4",
                    "installdir": installdir,
                    "LastUpdated": "0",
                    "UpdateResult": "0",
                    "SizeOnDisk": "0",
                    "BytesToDownload": "0",
                    "BytesDownloaded": "0",
                }
            }
            vdf_dump(acf_file, acf_contents)
            print(f"Wrote .acf file to {acf_file}")
        else:
            # Clear stale error state so Steam doesn't keep retrying a
            # failed update — this is what causes "NO INTERNET CONNECTION"
            self._patch_acf_error_state(acf_file)

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
            ]:
                if app_state.get(key, "0") != clean_val:
                    app_state[key] = clean_val
                    patched = True
            if patched:
                vdf_dump(acf_file, data)
                print("Patched .acf error state (cleared UpdateResult / validation flags)")
            else:
                print("Skipped writing to .acf file (no stale error state)")
        except Exception as e:
            logger.warning("Could not patch ACF error state: %s", e)
            print("Skipped writing to .acf file")


    def patch_workshop_acf(self, lua: LuaParsedInfo):
        # Steam runs a Workshop update after validating the game.
        # Orphaned WorkshopItemDetails entries (items tracked but not
        # in WorkshopItemsInstalled) cause Steam to try to verify/re-
        # download those items → Access Denied → "NO INTERNET CONNECTION".
        # This fix runs regardless of the NeedsDownload flag because users
        # may have manually set it to 0 while the orphaned entries remain.
        ws_dir = self.steam_lib_path / "steamapps" / "workshop"
        ws_acf = ws_dir / f"appworkshop_{lua.app_id}.acf"
        if not ws_acf.exists():
            return
        try:
            data = vdf_load(ws_acf)
            ws = data.get("AppWorkshop", {})
            size_on_disk = ws.get("SizeOnDisk", "0")
            items_installed = ws.get("WorkshopItemsInstalled", {})
            item_details = ws.get("WorkshopItemDetails", {})

            patched = False

            # Always clear stale download/update flags
            for flag in ("NeedsDownload", "NeedsUpdate"):
                if ws.get(flag, "0") != "0":
                    ws[flag] = "0"
                    patched = True

            # Clear orphaned WorkshopItemDetails entries — items that Steam
            # tracks in Details but are not in ItemsInstalled.  These are the
            # root cause of the NO INTERNET CONNECTION loop.
            if size_on_disk in ("0", "") and not items_installed and item_details:
                # Nothing is installed at all — wipe the whole details block
                ws["WorkshopItemDetails"] = {}
                patched = True
            elif item_details:
                # Some items installed — only remove the orphaned ones
                orphaned = [k for k in list(item_details) if k not in items_installed]
                for k in orphaned:
                    del item_details[k]
                if orphaned:
                    patched = True

            if patched:
                vdf_dump(ws_acf, data)
                print(
                    f"Patched workshop ACF — cleared stale flags/orphaned items "
                    f"to prevent 'NO INTERNET CONNECTION' ({ws_acf.name})"
                )
            else:
                print(f"Workshop ACF already clean ({ws_acf.name})")
        except Exception as e:
            logger.warning("Could not patch workshop ACF: %s", e)


@dataclass
class ConfigVDFWriter:
    steam_path: Path

    def add_decryption_keys_to_config(self, lua: LuaParsedInfo):
        vdf_file = self.steam_path / "config/config.vdf"
        shutil.copyfile(vdf_file, (self.steam_path / "config/config.vdf.backup"))
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
