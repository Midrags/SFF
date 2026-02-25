"""For managing Greenluma's AppList folder"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional, Union

from colorama import Fore, Style
from rich.console import Console
from rich.table import Column, Table

from smd.app_injector.base import AppInjectionManager
from smd.lua.writer import ConfigVDFWriter
from smd.manifest.downloader import ManifestDownloader
from smd.prompts import prompt_confirm, prompt_dir, prompt_select, prompt_text
from smd.steam_client import ParsedDLC, SteamInfoProvider, get_product_info
from smd.steam_store import get_dlc_list_from_store, get_dlc_names_from_store
from smd.storage.settings import get_setting, set_setting
from smd.structs import (
    AppIDInfo,
    AppListChoice,
    AppListPathAndID,
    DepotOrAppID,
    DLCTypes,
    LuaParsedInfo,
    MainReturnCode,
    OrganizedAppIDs,
    ProductInfo,
    Settings,
)
from smd.utils import enter_path

logger = logging.getLogger(__name__)


class AppListManager(AppInjectionManager):
    def __init__(self, steam_path: Path, provider: SteamInfoProvider):
        # Get ID limit from settings (None/0 = unlimited)
        limit_str = get_setting(Settings.APPLIST_ID_LIMIT)
        if limit_str:
            try:
                self.max_id_limit = int(limit_str)
                if self.max_id_limit <= 0:
                    self.max_id_limit = None  # 0 or negative = unlimited
            except (ValueError, TypeError):
                self.max_id_limit = None  # Invalid value = unlimited
        else:
            self.max_id_limit = None  # No setting = unlimited by default
        self.steam_path = steam_path
        self.provider = provider

        # App ID / Depot IDs mapped to their name and type
        self.id_map: dict[int, DepotOrAppID] = {}

        saved_applist = get_setting(Settings.APPLIST_FOLDER)
        self.applist_folder = (
            steam_path / "AppList" if saved_applist is None else Path(saved_applist)
        )

        if not self.applist_folder.exists():
            self.applist_folder = prompt_dir(
                "Could not find AppList folder. " "Please specify the full path here:"
            )
            set_setting(Settings.APPLIST_FOLDER, str(self.applist_folder.absolute()))
        elif saved_applist is None:
            colorized = (
                Fore.YELLOW + str(self.applist_folder.resolve()) + Style.RESET_ALL
            )
            print(
                f"AppsList folder automatically selected: {colorized}\n"
                "Change this in settings if it's the wrong folder."
            )
            set_setting(Settings.APPLIST_FOLDER, str(self.applist_folder.absolute()))

        if saved_applist:
            colorized = (
                Fore.YELLOW + str(self.applist_folder.resolve()) + Style.RESET_ALL
            )
            print(f"Your AppList folder is {colorized}")
            print(
                Fore.LIGHTBLACK_EX
                + "If you are using Stealth Mode (Any folder), make sure"
                " this points to the folder you put GreenLuma in" + Style.RESET_ALL
            )
        self.fix_names()

    def get_local_filenames(self, sort: bool = False) -> list[Path]:
        """get_local_ids but just filenames and no last_idx editing"""
        files: list[Path] = []
        for file in self.applist_folder.glob("*.txt"):
            if not file.stem.isdigit():
                logger.debug(f"[get_local_filenames] Ignored {file.name}")
                continue
            files.append(file)
        if sort:
            files.sort(key=lambda x: int(x.stem) if x.stem.isnumeric() else -1)
        return files

    def get_local_ids(self, sort: bool = False) -> list[AppListPathAndID]:
        """Returns a list of tuple(path, app_id) and
        updates self.last_idx to the filename with the largest number"""
        self.last_idx = -1
        ids: list[AppListPathAndID] = []
        for file in self.applist_folder.glob("*.txt"):
            if not file.stem.isdigit():
                logger.debug(f"[get_local_ids] Ignored {file.name}")
                continue
            file_idx = int(file.stem)
            if file_idx > self.last_idx:
                self.last_idx = file_idx

            contents = file.read_text(encoding="utf-8").strip()

            if contents.isnumeric():
                appid = int(contents)
            else:
                raise Exception(
                    f"{file.name} does not contain a "
                    "number. Text files in AppList should only contain the number "
                    "of their App ID. Please fix this and launch SFF again."
                )
            ids.append(AppListPathAndID(file, appid))
        if sort:
            ids.sort(key=lambda x: int(x.path.stem) if x.path.stem.isnumeric() else -1)
        return ids

    def add_ids(
        self, data: Union[int, list[int], LuaParsedInfo], skip_check: bool = False
    ):
        """Adds IDs to the AppList folder"""
        if isinstance(data, int):
            app_ids = [data]
        elif isinstance(data, LuaParsedInfo):
            app_ids = [int(x.depot_id) for x in data.depots]
        else:
            app_ids = data

        # Get current local IDs and update last_idx
        local_ids_data = [] if skip_check else self.get_local_ids()
        local_ids = [x.app_id for x in local_ids_data]
        current_count = len(local_ids)
        
        # Filter out IDs that already exist
        new_ids = [app_id for app_id in app_ids if app_id not in local_ids]
        existing_ids = [app_id for app_id in app_ids if app_id in local_ids]
        
        # Print existing IDs first
        for app_id in existing_ids:
            print(f"{app_id} already in AppList")
        
        if not new_ids:
            # All IDs already exist
            return
        
        # Calculate how many IDs will be added
        new_count = len(new_ids)
        projected_total = current_count + new_count
        
        # Check limit upfront before adding any IDs (only if limit is set)
        if self.max_id_limit is not None:
            # Calculate how many need to be removed (account for current over-limit state)
            current_excess = max(0, current_count - self.max_id_limit)
            total_excess = max(0, projected_total - self.max_id_limit)
            excess_count = total_excess
            
            if projected_total > self.max_id_limit:
                if current_excess > 0:
                    print(
                        Fore.YELLOW + f"\nNote: You currently have {current_count} IDs (exceeds limit by {current_excess}). "
                        f"Adding {new_count} more ID(s) will result in {projected_total} IDs."
                        + Style.RESET_ALL
                    )
                else:
                    print(
                        Fore.YELLOW + f"\nNote: Adding {new_count} ID(s) will exceed the {self.max_id_limit} ID limit "
                        f"(current: {current_count}, after: {projected_total})."
                        + Style.RESET_ALL
                    )
                print(
                    Fore.YELLOW + f"You need to remove at least {excess_count} ID(s) to stay within the limit."
                    + Style.RESET_ALL
                )
                
                # Auto-remove old IDs to make room for all new IDs
                if prompt_confirm(
                    f"Would you like to automatically remove {excess_count} oldest ID(s) to make room?",
                    default=True,
                ):
                    self._handle_id_limit_exceeded(excess_count)
                    # Refresh local IDs after cleanup - this will update last_idx
                    local_ids_data = self.get_local_ids()
                else:
                    print(
                        Fore.YELLOW + "Skipping ID addition. You can manually remove IDs later using the 'Manage AppList IDs' menu."
                        + Style.RESET_ALL
                    )
                    return
        
        # Now add all new IDs
        for app_id in new_ids:
            new_idx = self.last_idx + 1
            with (self.applist_folder / f"{new_idx}.txt").open("w") as f:
                f.write(str(app_id))
            self.last_idx = new_idx
            id_count = new_idx + 1
            print(
                f"{app_id} added to AppList. " f"There are now {id_count} IDs stored."
            )
        
        # Final check (shouldn't trigger if we handled it upfront, but safety check)
        if self.max_id_limit is not None:
            final_count = len(self.get_local_ids())
            if final_count > self.max_id_limit:
                logger.warning(
                    f"ID limit exceeded after addition: {final_count} > {self.max_id_limit}"
                )

    def remove_ids(self, ids_to_delete: list[int]):
        """became unused and replaced with delete_paths"""
        local_ids = self.get_local_ids(sort=True)
        remaining_ids = [*local_ids]
        for local_id in local_ids:
            if local_id.app_id in ids_to_delete:
                local_id.path.unlink(missing_ok=True)
                remaining_ids.remove(local_id)
                print(f"{local_id.path.name} deleted")
        for new_idx, remaining_id in enumerate(remaining_ids):
            new_name = remaining_id.path.parent / f"{new_idx}.txt"
            if remaining_id.path.name != new_name.name:
                remaining_id.path.rename(new_name)

    def delete_paths(self, paths_to_delete: list[Path], all_paths: list[Path]):
        """Deletes all paths_to_delete and renames remaining files.
        Assumes all_paths is already sorted in ascending order"""
        remaining_paths = [*all_paths]
        for path in paths_to_delete:
            path.unlink(missing_ok=True)
            remaining_paths.remove(path)
            print(f"{path.name} deleted")
        for new_idx, path in enumerate(remaining_paths):
            new_name = path.parent / f"{new_idx}.txt"
            if path.name != new_name.name:
                path.rename(new_name)

    def fix_names(self):
        """Fixes filenames if they're wrong (e.g. 0.txt is missing, gap in numbering)"""
        ids = self.get_local_filenames(sort=True)
        for new_idx, old_path in enumerate(ids):
            new_name = old_path.parent / f"{new_idx}.txt"
            if new_name.name != old_path.name:
                old_path.rename(new_name)

    def _handle_id_limit_exceeded(self, excess_count: int):
        """Removes the oldest IDs to bring the count back under the limit"""
        if self.max_id_limit is None:
            return  # No limit set, nothing to do
        
        local_ids = self.get_local_ids(sort=True)
        current_count = len(local_ids)
        
        if current_count <= self.max_id_limit:
            return
        
        # Calculate how many to remove (add a small buffer to ensure we're under limit)
        to_remove = excess_count + 1  # Remove one extra to be safe
        
        # Get the oldest IDs (lowest indices, sorted by filename)
        ids_to_remove = local_ids[:to_remove]
        
        print(
            Fore.YELLOW + f"\nRemoving {len(ids_to_remove)} oldest ID(s) to make room:"
            + Style.RESET_ALL
        )
        for item in ids_to_remove:
            print(f"  - {item.app_id} ({item.path.name})")
        
        paths_to_remove = [item.path for item in ids_to_remove]
        all_paths = [item.path for item in local_ids]
        self.delete_paths(paths_to_remove, all_paths)
        
        # Update last_idx after deletion by refreshing local IDs
        self.get_local_ids()  # This will update last_idx
        
        remaining_count = len(self.get_local_ids())
        limit_text = f"limit: {self.max_id_limit}" if self.max_id_limit is not None else "unlimited"
        print(
            Fore.GREEN + f"\nSuccessfully removed {len(ids_to_remove)} ID(s). "
            f"You now have {remaining_count} IDs ({limit_text})."
            + Style.RESET_ALL
        )

    def tweak_last_digit(self, app_id: int):
        chars = list(str(app_id))
        chars[-1] = "0"
        return int("".join(chars))

    def _update_depot_info(self, product_info: ProductInfo):
        """Updates `self.id_map` with data from `product_info`"""
        apps_data = enter_path(product_info, "apps")

        for app_id, app_details in apps_data.items():
            assert isinstance(app_id, int)
            app_name = enter_path(app_details, "common", "name")
            depots = enter_path(app_details, "depots")

            self.id_map[app_id] = DepotOrAppID(app_name, app_id, None)

            for depot_id in depots.keys():
                if depot_id.isdigit():
                    depot_id = int(depot_id)
                    parent_id = app_id if app_id != depot_id else None
                    self.id_map[int(depot_id)] = DepotOrAppID(
                        app_name, int(depot_id), parent_id
                    )

    def _populate_id_map(self, app_ids: list[int]):
        """populates `self.id_map` but with an extra layer of recursion in case an ID
        has been added that does not come with the parent ID"""
        info = get_product_info(self.provider, list(app_ids))
        self._update_depot_info(info)

        still_missing: list[int] = []

        for app_id in app_ids:
            if app_id not in self.id_map:
                # There is a Depot ID in AppList without a corresponding base App ID
                still_missing.append(self.tweak_last_digit(app_id))

        if still_missing:
            info = get_product_info(self.provider, still_missing)
            self._update_depot_info(info)

    def _organize_ids(self, ids: list[int]):
        """Organize Depot IDs inside parent App IDs"""
        organized: OrganizedAppIDs = {}

        for app_id in ids:
            if app_id in self.id_map:
                item = self.id_map[app_id]
                if item.parent_id is not None:  # is a depot
                    if item.parent_id in organized:
                        info = organized[item.parent_id]
                    else:
                        info = AppIDInfo(False, item.name)
                        organized[item.parent_id] = info
                    info.depots.append(item.id)
                    if item.id == item.parent_id:
                        info.exists = True
                else:
                    if app_id in organized:
                        info = organized[app_id]
                        info.exists = True
                    else:
                        organized[app_id] = AppIDInfo(True, item.name)
            else:
                organized[app_id] = AppIDInfo(True, "UNKNOWN GAME")
        return organized

    def _menu_items_from_organized(self, organized: OrganizedAppIDs):
        """Convert organized IDs into menu items for prompt_select"""
        menu_items: list[tuple[str, int]] = []

        for app_id, info in organized.items():
            ext = "(MISSING)" if not info.exists else ""
            name = f"{app_id} - {info.name} {ext}"
            menu_items.append((name, app_id))
            depots = info.depots
            for depot in depots:
                menu_items.append((f"└──>{depot}", depot))
        return menu_items

    def _prompt_include_depots(
        self, selected_ids: set[int], organized: OrganizedAppIDs
    ):
        """Prompts to select depots related to selected parent IDs.
        Modified selected_ids in-place."""
        selected_base_ids = [
            x for x in selected_ids if x in organized and organized[x].depots
        ]
        if len(selected_base_ids) > 0:
            for app_id in selected_base_ids:
                name = organized[app_id].name
                depots = organized[app_id].depots
                if prompt_confirm(
                    f"Would you to select all Depot IDs related to {name}?",
                ):
                    selected_ids.update(depots)

    def _get_paths_from_ids(
        self, app_ids: set[int], path_and_ids: list[AppListPathAndID]
    ):
        """Converts IDs to Paths"""
        file_map: defaultdict[int, list[Path]] = defaultdict(list)
        # app id mapped to files that have that ID
        for x in path_and_ids:
            file_map[x.app_id].append(x.path)
        paths_to_delete: list[Path] = []
        for app_id in app_ids:
            for path in file_map[app_id]:
                paths_to_delete.append(path)
        return paths_to_delete

    def prompt_id_deletion(self):
        """Show all AppList IDs and let the user delete them"""

        path_and_ids = self.get_local_ids(sort=True)
        if not path_and_ids:
            print(
                "There's nothing inside the AppList folder. "
                "Try adding one manually or automatically when you "
                "add a game with the tool."
            )
            return

        # i'm not using set() cuz that doesn't preserve insertion order lmao
        local_ids = list(dict.fromkeys([int(x.app_id) for x in path_and_ids]))

        self._populate_id_map(local_ids)

        organized = self._organize_ids(local_ids)

        # list of tuple(app name, app id)
        menu_items = self._menu_items_from_organized(organized)
        if len(menu_items) < len(local_ids):
            logger.warning("There are less menu items than actual IDs inside AppList.")

        ids_to_delete_list: Optional[list[int]] = prompt_select(
            "Select IDs to delete from AppList:",
            menu_items,
            multiselect=True,
            long_instruction="Press Space to select items, "
            "and Enter to confirm selections. Ctrl+Z to cancel.",
            mandatory=False,
        )
        if ids_to_delete_list is None:
            print("No IDs selected. Doing nothing")
            return
        ids_to_delete = set(ids_to_delete_list)
        self._prompt_include_depots(ids_to_delete, organized)

        paths_to_delete = self._get_paths_from_ids(ids_to_delete, path_and_ids)
        all_paths = [x.path for x in path_and_ids]
        self.delete_paths(paths_to_delete, all_paths)

    def _dlc_check_via_store(self, base_id: int) -> None:
        """DLC check using Steam Store API only (no Steam client login). Fallback when Steam API fails."""
        print("Using Steam Store (no login required)...")
        result = get_dlc_list_from_store(base_id)
        if not result:
            print("Could not load DLC list from Steam Store. Try again later.")
            return
        base_name, dlc_ids = result
        if not dlc_ids:
            print("This game has no DLC.")
            return
        print(f"Found {len(dlc_ids)} DLC(s). Fetching names...")
        names = get_dlc_names_from_store(dlc_ids)
        local_ids = {x.app_id for x in self.get_local_ids()}
        console = Console()
        table = Table(
            "ID",
            "Name",
            Column(header="In AppList?", justify="center"),
        )
        not_in_applist: list[int] = []
        for app_id in dlc_ids:
            in_list = app_id in local_ids
            if not in_list:
                not_in_applist.append(app_id)
            table.add_row(
                str(app_id),
                names.get(app_id, f"DLC {app_id}"),
                "[green]O[/green]" if in_list else "[red]X[/red]",
            )
        console.print(table)
        if not_in_applist:
            print("Some DLCs are not in the AppList.")
            if prompt_confirm("Do you want to add these to the AppList?"):
                self.add_ids(not_in_applist, skip_check=False)
        else:
            print("All DLCs are in the AppList.")

    def dlc_check(self, provider: SteamInfoProvider, base_id: int):
        print("Checking for DLC...")
        try:
            base_info = get_product_info(provider, [base_id])
        except Exception as e:
            logger.debug("Steam API failed for DLC check: %s", e)
            print("Steam connection failed. Using Steam Store instead (no login)...")
            self._dlc_check_via_store(base_id)
            return
        base_info_trimmed = enter_path(base_info, "apps", base_id)
        dlcs = enter_path(base_info_trimmed, "extended", "listofdlc")
        logger.debug(f"listofdlc: {dlcs}")
        if not dlcs:
            print("This game has no DLC.")
        else:
            assert isinstance(dlcs, str)
            dlcs = [int(x) for x in dlcs.split(",")]
            try:
                dlc_info = get_product_info(provider, dlcs)
            except Exception as e:
                logger.debug("Steam API failed for DLC details: %s", e)
                print("Steam connection failed. Using Steam Store instead (no login)...")
                self._dlc_check_via_store(base_id)
                return
            config = ConfigVDFWriter(self.steam_path)
            manifest = ManifestDownloader(self.provider, self.steam_path)
            if dlc_info:
                if apps := dlc_info.get("apps"):
                    unowned_non_depot_dlcs: list[int] = []
                    local_ids = [x.app_id for x in self.get_local_ids()]
                    parsed_dlcs: list[ParsedDLC] = [
                        ParsedDLC(int(depot_id), data, base_info_trimmed, local_ids)
                        for depot_id, data in apps.items()
                    ]
                    depot_dlcs = [x.id for x in parsed_dlcs if x.type == DLCTypes.DEPOT]
                    key_map = config.ids_in_config(depot_dlcs)
                    manifest_map = (
                        manifest.get_dlc_manifest_status(depot_dlcs)
                        if depot_dlcs
                        else {}
                    )
                    non_depot_dlc_count = 0
                    console = Console()
                    table = Table(
                        "ID",
                        "Name",
                        "Type",
                        Column(header="In AppList?", justify="center"),
                        Column(header="Has Key?", justify="center"),
                        Column(header="Has Manifest?", justify="center"),
                    )
                    bool_map: dict[Optional[bool], str] = {
                        True: "[green]O[/green]",
                        False: "[red]X[/red]",
                        None: "N/A",
                    }
                    for dlc in parsed_dlcs:
                        if dlc.type == DLCTypes.NOT_DEPOT:
                            non_depot_dlc_count += 1
                            if not dlc.in_applist:
                                unowned_non_depot_dlcs.append(dlc.id)
                        table.add_row(
                            str(dlc.id),
                            dlc.name,
                            dlc.type.value,
                            bool_map[dlc.in_applist],
                            bool_map[key_map.get(dlc.id)],
                            bool_map[manifest_map.get(dlc.id)],
                        )
                    console.print(table)
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

    def display_menu(self, provider: SteamInfoProvider) -> MainReturnCode:
        applist_choice: Optional[AppListChoice] = prompt_select(
            "Choose:", list(AppListChoice), cancellable=True
        )
        if applist_choice is None:
            return MainReturnCode.LOOP_NO_PROMPT
        if applist_choice == AppListChoice.DELETE:
            self.prompt_id_deletion()
        elif applist_choice == AppListChoice.ADD:
            validator: Callable[[str], bool] = lambda x: all(
                [y.isdigit() for y in x.split()]
            )
            digit_filter: Callable[[str], list[int]] = lambda x: [
                int(y) for y in x.split()
            ]
            ids: list[int] = prompt_text(
                "Input IDs that you would like to add (separate them with spaces)",
                validator=validator,
                filter=digit_filter,
            )
            self.add_ids(ids)

        return MainReturnCode.LOOP_NO_PROMPT
