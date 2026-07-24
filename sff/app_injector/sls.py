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

"""SLSSteam stuff"""

import logging
from pathlib import Path

from colorama import Fore, Style

from sff.app_injector.base import AppInjectionManager
from sff.lua.writer import ConfigVDFWriter
from sff.manifest.downloader import ManifestDownloader
from sff.prompts import prompt_confirm, prompt_file, prompt_select, prompt_text
from sff.steam_client import ParsedDLC, SteamInfoProvider
from sff.steam_store import get_dlc_list_from_store, get_dlc_names_from_store
from sff.storage.settings import get_setting, set_setting
from sff.storage.yaml import YAMLParser
from sff.structs import InjectionChoice, DLCTypes, LuaParsedInfo, MainReturnCode, Settings
from sff.utils import enter_path
from typing import Union

logger = logging.getLogger(__name__)


class SLSManager(AppInjectionManager):
    def __init__(self, steam_path, provider):
        self.steam_path = steam_path
        self.provider = provider
        saved_path = get_setting(Settings.SLS_CONFIG_LOCATION)
        if saved_path is None:
            from sff.linux.slssteam import detect_steam_type, get_slssteam_config_dir
            self.sls_config_path = get_slssteam_config_dir(detect_steam_type()) / "config.yaml"
        else:
            self.sls_config_path = Path(saved_path)
        if not self.sls_config_path.exists():
            print(
                Fore.YELLOW
                + "\n[SLSsteam] Config not found at: "
                + str(self.sls_config_path)
                + "\n\n"
                + "Launch Steam once so SLSsteam creates its config file, then retry.\n"
                + "If you already launched Steam, check that SLSsteam is installed:\n"
                + "  Tools tab -> Linux Setup -> Auto-Install SLSsteam"
                + Style.RESET_ALL
            )
            raise FileNotFoundError(
                f"SLSsteam config not found at {self.sls_config_path}. "
                "Launch Steam once to let SLSsteam generate it."
            )
        elif saved_path is None:
            colorized = (
                Fore.YELLOW + str(self.sls_config_path.resolve()) + Style.RESET_ALL
            )
            print(
                f"SLSSteam config file automatically selected: {colorized}\n"
                "Change this in settings if it's the wrong folder."
            )
            set_setting(
                Settings.SLS_CONFIG_LOCATION, str(self.sls_config_path.absolute())
            )

    def get_local_ids(self):
        parser = YAMLParser(self.sls_config_path)
        data = parser.read() or {}
        return data.get("AdditionalApps") or []

    def add_ids(
        self, data: Union[int, list[int], LuaParsedInfo], skip_check: bool = False
    ):
        from sff.linux.yaml_config import add_additional_app
        if isinstance(data, int):
            data = [data]
        elif isinstance(data, LuaParsedInfo):
            data = [int(data.app_id)]
        changes = 0
        for new_app_id in data:
            added = add_additional_app(self.sls_config_path, str(new_app_id))
            if added:
                print(f"{new_app_id} added to SLSSteam config.")
                changes += 1
            else:
                print(f"{new_app_id} already in SLSSteam config.")

    def _dlc_check_via_store(self, base_id):
        """DLC check using Steam Store API only (no Steam client login). Fallback when Steam API fails."""
        print("Using Steam Store (no login required)...")
        result = get_dlc_list_from_store(base_id)
        if not result:
            print("Could not load DLC list from Steam Store. Try again later.")
            return
        _base_name, dlc_ids = result
        if not dlc_ids:
            print("This game has no DLC.")
            return
        print(f"Found {len(dlc_ids)} DLC(s). Fetching names...")
        names = get_dlc_names_from_store(dlc_ids)
        local_ids = set(self.get_local_ids())
        not_in_config = []
        rows_store = []
        for app_id in dlc_ids:
            in_list = app_id in local_ids
            if not in_list:
                not_in_config.append(app_id)
            rows_store.append((str(app_id), names.get(app_id, f"DLC {app_id}"), in_list))
        width_id = max(len("ID"), max((len(r[0]) for r in rows_store), default=2))
        width_name = max(len("Name"), max((len(r[1]) for r in rows_store), default=4))
        print(f"\n{'ID':<{width_id}}  {'Name':<{width_name}}  In config?")
        print(f"{'-' * width_id}  {'-' * width_name}  ----------")
        for _id, _name, _in in rows_store:
            mark = "O" if _in else "X"
            print(f"{_id:<{width_id}}  {_name:<{width_name}}  {mark}")
        if not_in_config:
            print("Some DLCs are not in the SLSSteam config.")
            if prompt_confirm("Do you want to add these to the config?"):
                self.add_ids(not_in_config, skip_check=False)
        else:
            print("All DLCs are in the config.")

    def display_menu(self, provider=None):
        choice = prompt_select(
            "Choose:",
            [
                (InjectionChoice.ADD.value, InjectionChoice.ADD),
                (InjectionChoice.DELETE.value, InjectionChoice.DELETE),
            ],
            cancellable=True,
        )
        if choice is None:
            return MainReturnCode.LOOP_NO_PROMPT
        if choice == InjectionChoice.ADD:
            ids_raw = prompt_text("Enter IDs to add (space-separated):")
            ids = [int(x) for x in ids_raw.split() if x.isdigit()]
            if ids:
                self.add_ids(ids)
        elif choice == InjectionChoice.DELETE:
            local_ids = self.get_local_ids()
            if not local_ids:
                print("No IDs in SLSSteam config.")
                return MainReturnCode.LOOP_NO_PROMPT
            to_delete = prompt_select(
                "Select IDs to remove:",
                [(str(x), x) for x in local_ids],
                multiselect=True,
                cancellable=True,
            )
            if to_delete:
                from sff.linux.yaml_config import remove_additional_app
                removed = 0
                for id_ in to_delete:
                    if remove_additional_app(self.sls_config_path, str(id_)):
                        removed += 1
                print(f"Removed {removed} ID(s) from SLSSteam config.")
        return MainReturnCode.LOOP_NO_PROMPT

    def dlc_check(self, provider, base_id, auto_add_depot_dlcs: bool = False):
        print("Checking for DLC...")
        try:
            base_info = provider.get_single_app_info(base_id)
        except Exception as e:
            logger.debug("Steam API failed for DLC check: %s", e)
            print("Steam connection failed. Using Steam Store instead (no login)...")
            self._dlc_check_via_store(base_id)
            return
        dlcs = enter_path(base_info, "extended", "listofdlc")
        logger.debug(f"listofdlc: {dlcs}")
        if not dlcs:
            print("This game has no DLC.")
        else:
            assert isinstance(dlcs, str)
            dlcs = [int(x) for x in dlcs.split(",")]
            try:
                dlc_info = provider.get_app_info(dlcs)
            except Exception as e:
                logger.debug("Steam API failed for DLC details: %s", e)
                print("Steam connection failed. Using Steam Store instead (no login)...")
                self._dlc_check_via_store(base_id)
                return
            config = ConfigVDFWriter(self.steam_path)
            manifest = ManifestDownloader(self.provider, self.steam_path)
            if dlc_info:
                unowned_non_depot_dlcs = []
                unowned_depot_dlcs_with_keys = []
                local_ids = self.get_local_ids()
                parsed_dlcs = [
                    ParsedDLC(int(depot_id), data, base_info, local_ids)
                    for depot_id, data in dlc_info.items()
                ]
                depot_dlcs = [x.id for x in parsed_dlcs if x.type == DLCTypes.DEPOT]
                key_map = config.ids_in_config(depot_dlcs)
                manifest_map = (
                    manifest.get_dlc_manifest_status(depot_dlcs) if depot_dlcs else {}
                )
                non_depot_dlc_count = 0
                bool_plain = {
                    True: "O", False: "X", None: "N/A"
                }
                rows_dlc = []
                for dlc in parsed_dlcs:
                    if dlc.type == DLCTypes.NOT_DEPOT:
                        non_depot_dlc_count += 1
                        if not dlc.in_applist:
                            unowned_non_depot_dlcs.append(dlc.id)
                    elif dlc.type == DLCTypes.DEPOT:
                        if not dlc.in_applist and key_map.get(dlc.id):
                            unowned_depot_dlcs_with_keys.append(dlc.id)
                    rows_dlc.append((
                        str(dlc.id), dlc.name, dlc.type.value,
                        dlc.in_applist, key_map.get(dlc.id), manifest_map.get(dlc.id),
                    ))
                width_id = max(len("ID"), max((len(r[0]) for r in rows_dlc), default=2))
                width_name = max(len("Name"), max((len(r[1]) for r in rows_dlc), default=4))
                width_type = max(len("Type"), max((len(r[2]) for r in rows_dlc), default=4))
                print(
                    f"\n{'ID':<{width_id}}  {'Name':<{width_name}}  {'Type':<{width_type}}  "
                    "In AppList?  Has Key?  Has Manifest?"
                )
                print(
                    f"{'-' * width_id}  {'-' * width_name}  {'-' * width_type}  "
                    "-----------  --------  -------------"
                )
                for _id, _nm, _tp, _al, _hk, _hm in rows_dlc:
                    print(
                        f"{_id:<{width_id}}  {_nm:<{width_name}}  {_tp:<{width_type}}  "
                        f"{bool_plain[_al]:<11}  {bool_plain[_hk]:<8}  {bool_plain[_hm]:<13}"
                    )
                print(
                    Fore.YELLOW + "NOTE: Pre-installed DLCs don't need "
                    "decryption key & manifest\n"
                    "Keys and manifests are only required "
                    "when you don't have the DLC downlaoded yet." + Style.RESET_ALL
                )
                if len(unowned_non_depot_dlcs) > 0:
                    print(
                        "This game has pre-installed DLCs that aren't "
                        "in the AppList."
                    )
                    if prompt_confirm("Do you want to add these to the AppList?"):
                        self.add_ids(unowned_non_depot_dlcs, skip_check=False)
                elif len(unowned_non_depot_dlcs) == 0 and non_depot_dlc_count > 0:
                    print("All pre-installed DLCs are already enabled.")
                elif non_depot_dlc_count == 0:
                    print(
                        "This game has no pre-installed DLCs :(\n"
                        "You'll have to find a lua that has "
                        "decryption keys for them."
                    )
                if unowned_depot_dlcs_with_keys:
                    if auto_add_depot_dlcs:
                        print(
                            Fore.YELLOW
                            + f"Auto-adding {len(unowned_depot_dlcs_with_keys)} DLC ID(s) to AppList: "
                            + ", ".join(str(x) for x in unowned_depot_dlcs_with_keys)
                            + Style.RESET_ALL
                        )
                        self.add_ids(unowned_depot_dlcs_with_keys, skip_check=False)
                    else:
                        print(
                            f"{len(unowned_depot_dlcs_with_keys)} DLC(s) with available keys "
                            f"are not in the AppList (IDs: "
                            + ", ".join(str(x) for x in unowned_depot_dlcs_with_keys) + ")."
                        )
                        if prompt_confirm("Add these DLC IDs to the AppList?"):
                            self.add_ids(unowned_depot_dlcs_with_keys, skip_check=False)
