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

"""LumaCore injection manager for Windows."""

import logging
from pathlib import Path
from typing import Union

from colorama import Fore, Style

from sff.app_injector.base import AppInjectionManager
from sff.steam_client import SteamInfoProvider
from sff.structs import LuaParsedInfo

logger = logging.getLogger(__name__)


class LumaCoreManager(AppInjectionManager):
    """Manages app ID injection via LumaCore's stplug-in Lua files on Windows."""

    def __init__(self, steam_path: Path, provider: SteamInfoProvider):
        self.steam_path = steam_path
        self.provider = provider
        self.applist_folder = None

    @property
    def stplug_in(self) -> Path:
        return self.steam_path / "config" / "stplug-in"

    def get_local_ids(self) -> set:
        ids = set()
        folder = self.stplug_in
        if not folder.exists():
            return ids
        for f in folder.glob("*.lua"):
            try:
                ids.add(int(f.stem))
            except ValueError:
                pass
        return ids

    def add_ids(
        self, data: Union[int, list, LuaParsedInfo], skip_check: bool = False
    ):
        pass

    def dlc_check(self, provider, base_id, auto_add_depot_dlcs: bool = False):
        from sff.steam_store import get_dlc_list_from_store, get_dlc_names_from_store
        from sff.structs import DLCTypes, MainReturnCode
        from rich.console import Console
        from rich.table import Column, Table
        from sff.prompts import prompt_confirm

        console = Console()

        print(Fore.CYAN + f"\nFetching DLC list for App ID {base_id}..." + Style.RESET_ALL)
        try:
            dlc_list = get_dlc_list_from_store(base_id, provider)
        except Exception as e:
            print(Fore.RED + f"Failed to fetch DLC list: {e}" + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT

        if not dlc_list:
            print(Fore.YELLOW + "No DLCs found for this game." + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT

        local_ids = self.get_local_ids()

        table = Table(
            Column("Status", style="cyan"),
            Column("DLC ID", style="white"),
            Column("Name", style="white"),
            title=f"DLC List — App {base_id}",
        )
        missing = []
        for dlc in dlc_list:
            dlc_id = dlc if isinstance(dlc, int) else getattr(dlc, "app_id", dlc)
            owned = dlc_id in local_ids
            status = "[green]Unlocked[/green]" if owned else "[red]Missing[/red]"
            name = ""
            try:
                names = get_dlc_names_from_store([dlc_id], provider)
                name = names.get(dlc_id, "")
            except Exception:
                pass
            table.add_row(status, str(dlc_id), name)
            if not owned:
                missing.append(dlc_id)

        console.print(table)

        if not missing:
            print(Fore.GREEN + "All DLCs are unlocked." + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT

        print(Fore.YELLOW + f"{len(missing)} DLC(s) not unlocked." + Style.RESET_ALL)
        if prompt_confirm("Add missing DLCs to the Lua file?"):
            print(
                Fore.YELLOW
                + "To add DLCs, re-download the game's Lua file via 'Download Games'."
                + Style.RESET_ALL
            )
        return MainReturnCode.LOOP_NO_PROMPT
