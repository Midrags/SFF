import functools
import logging
import os
import shutil
import subprocess
import sys
import time
import webbrowser
import zipfile
from collections import OrderedDict
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Union

from colorama import Fore, Style

from smd.app_injector.applist import AppListManager
from smd.app_injector.sls import SLSManager
from smd.analytics import get_analytics_tracker
from smd.game_specific import ACFInfo, GameHandler
from smd.http_utils import download_to_path
from smd.library_scanner import LibraryScanner
from smd.lua.manager import LuaManager
from smd.lua.writer import ACFWriter, ConfigVDFWriter
from smd.manifest.downloader import ManifestDownloader
from smd.midi import MidiPlayer
from smd.notifications import get_notification_service
from smd.processes import SteamProcess
from smd.prompts import (
    prompt_confirm,
    prompt_dir,
    prompt_file,
    prompt_secret,
    prompt_select,
    prompt_text,
)
from smd.recent_files import get_recent_files_manager
from smd.storage.acf import ACFParser, get_app_name_from_acf
from smd.storage.vdf import ensure_library_has_app, get_steam_libs
from smd.steam_client import get_product_info, SteamInfoProvider
from smd.steam_store import get_app_name_from_store
from smd.steam_tools_compat import (
    install_lua_to_steam,
    remove_lua_from_steam,
    sync_all_manifests_to_config_depotcache,
    sync_all_saved_lua_to_steam,
)
from smd.storage.settings import (
    clear_setting,
    export_settings,
    get_setting,
    import_settings,
    load_all_settings,
    set_setting,
)
from smd.storage.vdf import get_steam_libs, vdf_dump, vdf_load
from smd.strings import LINUX_RELEASE_PREFIX, RELEASE_PAGE_URL, VERSION, WINDOWS_RELEASE_PREFIX
from smd.structs import (
    ContextMenuOptions,
    GameSpecificChoices,
    LoggedInUser,
    LuaChoice,
    MainReturnCode,
    MidiFiles,
    OSType,
    SettingCustomTypes,
    SettingOperations,
    Settings,
    SettingsManagementOptions,
)
from smd.updater import Updater, is_newer_version
from smd.utils import enter_path, root_folder
from smd.zip import zip_folder

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    from smd.registry_access import (
        install_context_menu,
        set_stats_and_achievements,
        uninstall_context_menu,
    )
else:
    install_context_menu = lambda: None  # noqa: E731
    set_stats_and_achievements = lambda *args: False  # type: ignore # noqa: E731
    uninstall_context_menu = lambda: None  # noqa: E731


def music_toggle_decorator(func):  # type: ignore
    """
    A decorator that mutes/unmutes channels before/after a method call.
    The wrapper will receive the class instance as its first argument.
    """

    @functools.wraps(func)  # type: ignore
    def wrapper(self: "UI", *args, **kwargs):  # type: ignore
        if self.midi_player:
            self.midi_player.set_range(0, 5, 0)

        result = func(self, *args, **kwargs)  # type: ignore
        if self.midi_player:
            self.midi_player.set_range(0, 5, 1)

        return result  # type: ignore

    return wrapper  # type: ignore


class UI:
    def __init__(
        self,
        provider: SteamInfoProvider,
        steam_path: Path,
        os_type: OSType
    ):
        self.provider = provider
        self.steam_path = steam_path
        self.app_list_man = (
            AppListManager(steam_path, self.provider)
            if os_type == OSType.WINDOWS
            else None
        )
        self.os_type = os_type
        self.sls_man = (
            SLSManager(steam_path, provider) if os_type == OSType.LINUX else None
        )
        self.notification_service = get_notification_service()
        self.recent_files_manager = get_recent_files_manager()
        self.analytics_tracker = get_analytics_tracker()

        self.init_midi_player()

    def init_midi_player(self):
        if (play_music := get_setting(Settings.PLAY_MUSIC)) is None:
            set_setting(Settings.PLAY_MUSIC, False)
            play_music = False

        if any([not x.value.exists() for x in list(MidiFiles)]) or not play_music:
            self.midi_player = None
        else:
            self.midi_player = MidiPlayer(MidiFiles.MIDI_PLAYER_DLL.value)
            self.midi_player.start()

    def kill_midi_player(self):
        if self.midi_player:
            self.midi_player.stop()
            del self.midi_player
            self.midi_player = None  # prolly does nothing but whatever

    @music_toggle_decorator
    def edit_settings_menu(self) -> MainReturnCode:
        """Settings management menu with export/import functionality"""
        while True:
            choice: Optional[SettingsManagementOptions] = prompt_select(
                "Settings Management:",
                list(SettingsManagementOptions),
                cancellable=True,
            )
            
            if not choice or choice == SettingsManagementOptions.BACK:
                break
            
            if choice == SettingsManagementOptions.EDIT_SETTINGS:
                self._edit_settings_submenu()
            elif choice == SettingsManagementOptions.EXPORT_SETTINGS:
                self._export_settings_submenu()
            elif choice == SettingsManagementOptions.IMPORT_SETTINGS:
                self._import_settings_submenu()
        
        return MainReturnCode.LOOP_NO_PROMPT
    
    def _edit_settings_submenu(self) -> None:
        """Original settings editing functionality"""
        win_only = [Settings.APPLIST_FOLDER, Settings.GL_VERSION]
        linux_only = [Settings.SLS_CONFIG_LOCATION]
        if self.os_type == OSType.WINDOWS:
            ignore = linux_only
        elif self.os_type == OSType.LINUX:
            ignore = win_only
        else:
            ignore = []

        while True:
            saved_settings = load_all_settings()
            selected_key: Optional[Settings] = prompt_select(
                "Select a setting to change:",
                [
                    (
                        x.clean_name
                        + (
                            " (unset)"
                            if x.key_name not in saved_settings
                            else (
                                f": {saved_settings.get(x.key_name)}"
                                if not x.hidden
                                else ": [ENCRYPTED]"
                            )
                        ),
                        x,
                    )
                    for x in Settings if x not in ignore
                ],
                cancellable=True,
            )
            if not selected_key:
                break
            value = saved_settings.get(selected_key.key_name)
            value = value if value is not None else "(unset)"
            print(
                f"{selected_key.clean_name} is set to "
                + Fore.YELLOW
                + ("[ENCRYPTED]" if selected_key.hidden else str(value))
                + Style.RESET_ALL
            )
            operation: Optional[SettingOperations] = prompt_select(
                "What do you want to do with this setting?",
                list(SettingOperations),
                cancellable=True,
            )

            if operation is None:
                continue

            if operation == SettingOperations.DELETE:
                clear_setting(selected_key)
                continue

            if operation == SettingOperations.EDIT:
                new_settings_value: Union[str, bool]
                if selected_key.type == bool:
                    new_settings_value = prompt_confirm(
                        "Select the new value:", "Enable", "Disable"
                    )
                elif isinstance(selected_key.type, list):
                    enum_val: Enum = prompt_select(
                        "Select the new value:", selected_key.type
                    )
                    new_settings_value = enum_val.value
                elif selected_key.type == str:
                    func = prompt_secret if selected_key.hidden else prompt_text
                    new_settings_value = func("Enter the new value:")
                elif selected_key.type == SettingCustomTypes.DIR:
                    new_settings_value = str(
                        prompt_dir("Enter the new directory:").resolve()
                    )
                elif selected_key.type == SettingCustomTypes.FILE:
                    new_settings_value = str(
                        prompt_file("Enter the new file path:").resolve()
                    )
                elif selected_key.type == dict:
                    # Dict settings (like ACTIVE_UNLOCKER_PER_GAME) are managed internally
                    print(f"{selected_key.clean_name} is managed automatically by the application.")
                    continue
                else:
                    raise Exception("Unhandled setting type. Shouldn't happen.")
                set_setting(selected_key, new_settings_value)

                if selected_key == Settings.PLAY_MUSIC:
                    if value is True and new_settings_value is False:
                        self.kill_midi_player()
                    elif value is False and new_settings_value is True:
                        self.init_midi_player()

                if (
                    selected_key == Settings.APPLIST_FOLDER
                    and self.os_type == OSType.WINDOWS
                ):
                    self.app_list_man = AppListManager(self.steam_path, self.provider)

    def _get_applist_ids(self) -> Optional[list[int]]:
        """Get AppList/SLS IDs. Returns None if OS unsupported."""
        if self.app_list_man is None and self.sls_man is None:
            return None
        if self.app_list_man:
            return [x.app_id for x in self.app_list_man.get_local_ids()]
        if self.sls_man:
            return self.sls_man.get_local_ids()
        return None

    def _export_settings_submenu(self) -> None:
        """Export settings to JSON file"""
        print(Fore.CYAN + "\n=== Export Settings ===" + Style.RESET_ALL)
        
        # Ask if user wants to include sensitive data
        include_sensitive = prompt_confirm(
            "Include sensitive data (passwords, API keys)?",
            true_msg="Yes (include)",
            false_msg="No (exclude)"
        )
        
        # Get export path
        default_path = root_folder(outside_internal=True) / "settings_export.json"
        print(f"Default export path: {Fore.YELLOW}{default_path}{Style.RESET_ALL}")
        
        use_default = prompt_confirm(
            "Use default path?",
            true_msg="Yes",
            false_msg="No (choose custom path)"
        )
        
        if use_default:
            export_path = default_path
        else:
            export_path = Path(prompt_text("Enter export file path:"))
            if not export_path.suffix:
                export_path = export_path.with_suffix(".json")
        
        # Perform export
        success = export_settings(export_path, include_sensitive)
        
        if success:
            print(Fore.GREEN + f"✓ Settings exported successfully to: {export_path}" + Style.RESET_ALL)
            if not include_sensitive:
                print(Fore.YELLOW + "Note: Sensitive data was excluded from export" + Style.RESET_ALL)
        else:
            print(Fore.RED + "✗ Failed to export settings. Check debug.log for details." + Style.RESET_ALL)
    
    def _import_settings_submenu(self) -> None:
        """Import settings from JSON file"""
        print(Fore.CYAN + "\n=== Import Settings ===" + Style.RESET_ALL)
        print(Fore.YELLOW + "Warning: This will overwrite existing settings!" + Style.RESET_ALL)
        
        if not prompt_confirm("Continue with import?", false_msg="Cancel"):
            return
        
        # Get import path
        import_path = prompt_file("Select settings JSON file to import:")
        
        if not import_path.exists():
            print(Fore.RED + f"✗ File not found: {import_path}" + Style.RESET_ALL)
            return
        
        # Perform import
        success, message = import_settings(import_path)
        
        if success:
            print(Fore.GREEN + f"✓ {message}" + Style.RESET_ALL)
        else:
            print(Fore.RED + f"✗ {message}" + Style.RESET_ALL)

    @music_toggle_decorator
    def offline_fix_menu(self) -> MainReturnCode:
        print(
            Fore.YELLOW
            + "Steam will fail to launch when you close it while in OFFLINE Mode. "
            "Set it back to ONLINE to fix it." + Style.RESET_ALL
        )
        loginusers_file = self.steam_path / "config/loginusers.vdf"
        if not loginusers_file.exists():
            print(
                "loginusers.vdf file can't be found. "
                "Have you already logged in once through Steam?"
            )
            return MainReturnCode.LOOP_NO_PROMPT
        vdf_data = vdf_load(loginusers_file, mapper=OrderedDict)

        vdf_users = vdf_data.get("users")
        if vdf_users is None:
            print("There are no users on this Steam installation...")
            return MainReturnCode.LOOP_NO_PROMPT
        user_ids = vdf_users.keys()
        users: list[LoggedInUser] = []
        for user_id in user_ids:
            x = vdf_users[user_id]
            users.append(
                LoggedInUser(
                    user_id,
                    x.get("PersonaName", "[MISSING]"),
                    x.get("WantsOfflineMode", "[MISSING]"),
                )
            )
        if len(users) == 0:
            print("There are no users on this Steam installation")
            return MainReturnCode.LOOP_NO_PROMPT
        offline_converter: Callable[[str], str] = lambda x: (
            "ONLINE" if x == "0" else "OFFLINE"
        )
        chosen_user: Optional[LoggedInUser] = prompt_select(
            "Select a user: ",
            [
                (
                    f"{x.persona_name} - " + offline_converter(x.wants_offline_mode),
                    x,
                )
                for x in users
            ],
            cancellable=True,
        )
        if chosen_user is None:
            return MainReturnCode.LOOP_NO_PROMPT

        new_value = "0" if chosen_user.wants_offline_mode == "1" else "1"

        vdf_data["users"][chosen_user.steam64_id]["WantsOfflineMode"] = new_value
        vdf_dump(loginusers_file, vdf_data)
        print(f"{chosen_user.persona_name} is now {offline_converter(new_value)}")
        return MainReturnCode.LOOP

    @music_toggle_decorator
    def applist_menu(self) -> MainReturnCode:
        if self.app_list_man is None:
            print("Functionality for linux will be implemented soon.")
            return MainReturnCode.LOOP_NO_PROMPT
        return self.app_list_man.display_menu(self.provider)

    def sync_lua_to_steam_menu(self) -> MainReturnCode:
        """Sync saved LUAs and manifests into Steam config so games work without DLLInjector (Steam Tools style)."""
        saved_lua_dir = Path.cwd() / "saved_lua"
        n_lua = sync_all_saved_lua_to_steam(self.steam_path, saved_lua_dir)
        n_man = sync_all_manifests_to_config_depotcache(self.steam_path)
        stplug = self.steam_path / "config" / "stplug-in"
        config_depot = self.steam_path / "config" / "depotcache"
        if n_lua > 0 or n_man > 0:
            print(
                Fore.GREEN + f"Synced {n_lua} LUA(s) to {stplug}, {n_man} manifest(s) to {config_depot}. "
                "Games should now appear and work when launching Steam with or without DLLInjector."
                + Style.RESET_ALL
            )
        else:
            print(
                Fore.YELLOW + f"No saved LUAs in {saved_lua_dir} and no manifests in depotcache. "
                "Process a .lua file first, then run this again."
                + Style.RESET_ALL
            )
        return MainReturnCode.LOOP

    def remove_game_menu(self) -> MainReturnCode:
        """Remove a game from library: delete stplug-in LUA and optionally AppList entry. User can choose from list or type App ID."""
        stplug_in = self.steam_path / "config" / "stplug-in"
        if not stplug_in.exists():
            print(
                Fore.YELLOW + "No stplug-in folder found. Add games first (e.g. sync LUAs or process a .lua file)."
                + Style.RESET_ALL
            )
            return MainReturnCode.LOOP

        app_ids = sorted(
            int(f.stem)
            for f in stplug_in.glob("*.lua")
            if f.stem.isdigit()
        )
        if not app_ids:
            print(
                Fore.YELLOW + "No games in stplug-in. Add games first, then you can remove them here."
                + Style.RESET_ALL
            )
            return MainReturnCode.LOOP

        choice = prompt_select(
            "Remove by list or type App ID?",
            [
                ("Choose from list of games in library", "list"),
                ("Type App ID to remove", "type"),
            ],
            cancellable=True,
        )
        if choice is None:
            return MainReturnCode.LOOP

        to_remove: list[int] = []
        if choice == "type":
            raw = prompt_text(
                "Enter App ID to remove (e.g. 268910):",
                validator=lambda x: x.strip().isdigit(),
                invalid_msg="Must be a number.",
                filter=lambda x: int(x.strip()) if x.strip().isdigit() else None,
            )
            if raw is None:
                return MainReturnCode.LOOP
            to_remove = [raw]
            if not (stplug_in / f"{raw}.lua").exists() and (
                self.app_list_man is None
                or raw not in [x.app_id for x in self.app_list_man.get_local_ids()]
            ):
                print(
                    Fore.YELLOW + f"App ID {raw} has no LUA in stplug-in and is not in AppList. Nothing to remove."
                    + Style.RESET_ALL
                )
                return MainReturnCode.LOOP
        else:
            # choice == "list" — ACF first, then Steam store for uninstalled
            names = {aid: get_app_name_from_acf(self.steam_path, aid) for aid in app_ids}
            need_store = [aid for aid in app_ids if names[aid] == str(aid)]
            if need_store:
                print(
                    Fore.CYAN + "Fetching names for uninstalled games from Steam store..."
                    + Style.RESET_ALL
                )
                for aid in need_store:
                    store_name = get_app_name_from_store(aid)
                    if store_name:
                        names[aid] = store_name
            menu_items = [
                (f"{aid} - {names[aid]}" if names[aid] != str(aid) else str(aid), aid)
                for aid in app_ids
            ]
            selected = prompt_select(
                "Select game(s) to remove:",
                menu_items,
                multiselect=True,
                long_instruction="Space to select, Enter to confirm. Ctrl+Z to cancel.",
                mandatory=False,
                cancellable=True,
            )
            if selected is None:
                return MainReturnCode.LOOP
            to_remove = list(selected) if isinstance(selected, list) else [selected]

        if not to_remove:
            print("No games selected. Doing nothing.")
            return MainReturnCode.LOOP

        if not prompt_confirm(
            f"Remove {len(to_remove)} game(s) from library? Restart Steam afterward for changes to take effect.",
            default=True,
        ):
            return MainReturnCode.LOOP

        for app_id in to_remove:
            remove_lua_from_steam(self.steam_path, app_id)

        if self.app_list_man:
            path_and_ids = self.app_list_man.get_local_ids(sort=True)
            path_map_ids = {x.app_id for x in path_and_ids}
            ids_to_remove = [a for a in to_remove if a in path_map_ids]
            if ids_to_remove:
                paths_to_delete = self.app_list_man._get_paths_from_ids(
                    set(ids_to_remove), path_and_ids
                )
                all_paths = [x.path for x in path_and_ids]
                self.app_list_man.delete_paths(paths_to_delete, all_paths)

        print(
            Fore.GREEN + f"Removed {len(to_remove)} game(s). Restart Steam for changes to take effect."
            + Style.RESET_ALL
        )
        return MainReturnCode.LOOP

    def select_steam_library(self):
        steam_libs = get_steam_libs(self.steam_path)
        if len(steam_libs) == 1:
            return steam_libs[0]
        steam_lib_path: Optional[Path] = prompt_select(
            "Select a Steam library location:",
            steam_libs,
            cancellable=True,
            default=steam_libs[0],
        )
        return steam_lib_path

    @music_toggle_decorator
    def handle_game_specific(self, choice: GameSpecificChoices) -> MainReturnCode:
        injection_manager = self.app_list_man or self.sls_man
        if injection_manager is None:
            print("Unsupported OS for this action.")
            return MainReturnCode.LOOP_NO_PROMPT

        source_choices = [
            ("Steam games", "steam"),
            ("Games outside of Steam", "outside"),
        ]
        source: Optional[str] = prompt_select(
            "Choose game source:",
            source_choices,
            cancellable=True,
        )
        if source is None:
            return MainReturnCode.LOOP_NO_PROMPT

        if source == "steam":
            steam_libs = get_steam_libs(self.steam_path)
            lib_path = steam_libs[0] if steam_libs else self.steam_path
            handler = GameHandler(
                self.steam_path, lib_path, self.provider, injection_manager
            )
            return handler.execute_choice(choice)

        # "outside" — user selects a folder path
        game_path = prompt_dir(
            "Enter the game folder path (root folder containing the game):"
        )
        game_name_raw = prompt_text(
            "Game name for search (e.g. on online-fix.me). Press Enter to use folder name:",
            validator=lambda x: True,
        )
        game_name = (game_name_raw or "").strip() or game_path.name
        app_id_raw = prompt_text(
            "Steam App ID (optional; needed for DLC/Workshop). Press Enter to skip:",
            validator=lambda x: True,
        )
        app_id = (app_id_raw or "").strip() or "0"
        override_game = ACFInfo(app_id, game_path.resolve(), name=game_name)
        steam_libs = get_steam_libs(self.steam_path)
        lib_path = steam_libs[0] if steam_libs else self.steam_path
        handler = GameHandler(
            self.steam_path, lib_path, self.provider, injection_manager
        )
        return handler.execute_choice(choice, override_game=override_game)

    def run_game_action_with_selection(
        self, choice: GameSpecificChoices, acf_info: ACFInfo
    ) -> MainReturnCode:
        """Run a game-specific action with a pre-selected game (for GUI). No prompts for source/game."""
        injection_manager = self.app_list_man or self.sls_man
        if injection_manager is None:
            print("Unsupported OS for this action.")
            return MainReturnCode.LOOP_NO_PROMPT
        steam_libs = get_steam_libs(self.steam_path)
        lib_path = steam_libs[0] if steam_libs else self.steam_path
        handler = GameHandler(
            self.steam_path, lib_path, self.provider, injection_manager
        )
        return handler.execute_choice(choice, override_game=acf_info)

    @music_toggle_decorator
    def process_lua_minimal(self) -> MainReturnCode:
        """Processes a .lua file but only does the lua input, lua backup, and manifest
        download steps"""

        if self.os_type == OSType.WINDOWS:
            print(
                Fore.YELLOW
                + "This is the minimal version of the lua processing logic. "
                "Only use this when updating a game or if you want to export manifest "
                "files to a different folder." + Style.RESET_ALL
            )
            if not prompt_confirm("Continue?"):
                return MainReturnCode.LOOP_NO_PROMPT

        lua_manager = LuaManager(self.os_type)
        downloader = ManifestDownloader(self.provider, self.steam_path)
        steam_proc = (
            SteamProcess(self.steam_path, self.app_list_man.applist_folder)
            if self.app_list_man
            else None
        )

        parsed_lua = lua_manager.fetch_lua()
        if parsed_lua is None:
            return MainReturnCode.LOOP_NO_PROMPT
        lua_manager.backup_lua(parsed_lua)
        install_lua_to_steam(
            self.steam_path,
            str(parsed_lua.app_id),
            lua_manager.saved_lua / f"{parsed_lua.app_id}.lua",
        )
        print(Fore.YELLOW + "\nDownloading Manifests:" + Style.RESET_ALL)
        decrypt = prompt_confirm(
            "Would you like to also decrypt the manifest files?"
            " (Usually not needed)",
            default=False,
        )
        manifests = downloader.download_manifests(parsed_lua, decrypt=decrypt, auto_manifest=True)
        move_files = prompt_confirm(
            "Manifests are now in the depotcache folder. "
            "Would you like to transfer these files to another folder?",
            default=False,
        )
        dst = None
        do_zip = None
        target_zip = None
        if move_files:
            dst = prompt_dir(
                "Paste in here the folder you'd like to move them to "
                "(Blank defaults to Downloads folder):"
            )
            default_dir = False
            unique_name = f"{parsed_lua.app_id}_{time.time()}"
            if str(dst) == ".":
                default_dir = True
                dst = Path.home() / f"Downloads/{unique_name}"
                dst.mkdir(parents=True, exist_ok=True)
            for file in manifests:
                shutil.move(file, dst / file.name)
                print(f"{file.name} moved")
            do_zip = prompt_confirm(
                "Would you like to ZIP these files along with the lua? "
                "(Can be used for ACCELA on Linux)"
            )
            if do_zip:
                with (dst / f"{parsed_lua.app_id}.lua").open(
                    "w", encoding="utf-8"
                ) as f:
                    f.write(parsed_lua.contents)
                if default_dir:
                    target_zip = dst.parent / f"{unique_name}.zip"
                    zip_folder(dst, target_zip)
                    shutil.rmtree(dst)
                else:
                    target_zip = dst / f"{unique_name}.zip"
                    zip_folder(dst, target_zip)
                    for file in map(lambda x: dst / x.name, manifests):
                        file.unlink(missing_ok=True)
        if steam_proc:
            auto_launch = steam_proc.prompt_launch_or_restart()
        else:
            auto_launch = False

        print(Fore.GREEN + "\nSuccess! ", end="")
        if move_files and dst:
            if do_zip and target_zip:
                print(f"Files have been zipped to {target_zip}")
            else:
                print(f"Files can be found in {dst}")
        else:
            extra_msg = (
                "Close Steam and run DLLInjector again "
                "(or not depending on how you installed Greenluma). "
            ) if not auto_launch else ""
            print(
                extra_msg + 'Your game should show up in the library ready to "update"',
                end="",
            )
        print(Style.RESET_ALL)
        return MainReturnCode.LOOP

    @music_toggle_decorator
    def process_lua_full(self, file: Optional[Path] = None) -> MainReturnCode:
        """Processes a .lua file and goes through all the usual steps"""
        import time
        start_time = time.time()
        
        if (lib_path := self.select_steam_library()) is None:
            return MainReturnCode.LOOP_NO_PROMPT

        lua_manager = LuaManager(self.os_type)
        downloader = ManifestDownloader(self.provider, self.steam_path)
        config = ConfigVDFWriter(self.steam_path)
        acf = ACFWriter(lib_path)
        steam_proc = (
            SteamProcess(self.steam_path, self.app_list_man.applist_folder)
            if self.app_list_man
            else None
        )
        parsed_lua = lua_manager.fetch_lua(
            LuaChoice.ADD_LUA if file else None, override_path=file
        )
        if parsed_lua is None:
            return MainReturnCode.LOOP_NO_PROMPT
        if parsed_lua.path:
            self.recent_files_manager.add(parsed_lua.path)
        self.analytics_tracker.record_feature_usage("process_lua_full")
        
        set_stats_and_achievements(int(parsed_lua.app_id))
        if self.app_list_man:
            print(Fore.YELLOW + "\nAdding to AppList folder:" + Style.RESET_ALL)
            self.app_list_man.add_ids(parsed_lua)
            self.app_list_man.dlc_check(self.provider, int(parsed_lua.app_id))
        elif self.sls_man:
            print(Fore.YELLOW + "\nAdding to SLSSteam config:" + Style.RESET_ALL)
            self.sls_man.add_ids(parsed_lua)
            self.sls_man.dlc_check(self.provider, int(parsed_lua.app_id))
        print(Fore.YELLOW + "\nAdding Decryption Keys:" + Style.RESET_ALL)
        config.add_decryption_keys_to_config(parsed_lua)
        lua_manager.backup_lua(parsed_lua)
        install_lua_to_steam(
            self.steam_path,
            str(parsed_lua.app_id),
            lua_manager.saved_lua / f"{parsed_lua.app_id}.lua",
        )
        print(Fore.YELLOW + "\nACF Writing:" + Style.RESET_ALL)
        acf.write_acf(parsed_lua)
        ensure_library_has_app(self.steam_path, lib_path, str(parsed_lua.app_id))
        print(Fore.YELLOW + "\nDownloading Manifests:" + Style.RESET_ALL)
        use_parallel = get_setting(Settings.USE_PARALLEL_DOWNLOADS)
        if use_parallel:
            downloader.download_manifests_parallel(parsed_lua, auto_manifest=True)
        else:
            downloader.download_manifests(parsed_lua, auto_manifest=True)
        duration = time.time() - start_time
        self.analytics_tracker.record_operation(
            "process_lua_full",
            app_id=int(parsed_lua.app_id),
            success=True,
            duration=duration
        )
        self.notification_service.show_success(
            "Processing Complete",
            f"Successfully processed {parsed_lua.app_id}"
        )
        
        if steam_proc:
            auto_launch = steam_proc.prompt_launch_or_restart()
        else:
            auto_launch = False
        extra_msg = (
            "Close Steam and run DLLInjector again "
            "(or not depending on how you installed Greenluma). "
        ) if not auto_launch else ""
        print(
            Fore.GREEN
            + f"\nSuccess! {extra_msg}"
            + 'Your game should show up in the library ready to "update"'
            + Style.RESET_ALL
        )
        return MainReturnCode.LOOP

    def manage_context_menu(self) -> MainReturnCode:
        choice: Optional[ContextMenuOptions] = prompt_select(
            "Select an operation for the context menu:",
            list(ContextMenuOptions),
            cancellable=True,
        )
        if choice is None:
            return MainReturnCode.LOOP_NO_PROMPT
        if choice == ContextMenuOptions.INSTALL:
            install_context_menu()
        elif choice == ContextMenuOptions.UNINSTALL:
            uninstall_context_menu()
        return MainReturnCode.LOOP_NO_PROMPT

    def check_updates(self, os_type: OSType, test: bool = False) -> MainReturnCode:
        print("Checking for updates (GitHub releases)...", end="", flush=True)
        is_newer, resp = Updater.update_available()
        print(" Done!")
        if resp is None:
            print("Could not fetch latest release (check your connection or the releases page).")
            return MainReturnCode.LOOP_NO_PROMPT
        remote_version = (resp.get("tag_name") or "").strip()
        print(f"Your version: {VERSION}")
        print(f"Latest version: {remote_version}")
        if not is_newer and not test:
            print(Fore.GREEN + "You're already on the latest version." + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT
        if not is_newer and test:
            print(Fore.GREEN + "Version check only: no newer release." + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT
        print(Fore.YELLOW + "A newer version is available." + Style.RESET_ALL)
        release_url = resp.get("html_url") or RELEASE_PAGE_URL
        is_frozen = getattr(sys, "frozen", False)
        assets = resp.get("assets") or []
        # Prefer OS-specific package for frozen Windows; else use any release .zip (e.g. SMD_2-vX.Y.Z.zip)
        download_url = None
        asset_name = None
        use_os_package = False
        if os_type == OSType.WINDOWS:
            target_prefix = WINDOWS_RELEASE_PREFIX
        elif os_type == OSType.LINUX:
            target_prefix = LINUX_RELEASE_PREFIX
        else:
            target_prefix = ""
        for asset in assets:
            name = asset.get("name") or ""
            url = asset.get("browser_download_url")
            if not url:
                continue
            name_lower = name.lower()
            if is_frozen and os_type == OSType.WINDOWS and (
                name_lower.startswith(target_prefix.lower()) or target_prefix.lower() in name_lower
            ):
                download_url = url
                asset_name = name
                use_os_package = True
                break
        if not use_os_package:
            for asset in assets:
                name = asset.get("name") or ""
                url = asset.get("browser_download_url")
                if url and name.lower().endswith(".zip"):
                    download_url = url
                    asset_name = name
                    break

        app_dir = root_folder(outside_internal=True)
        update_zip = app_dir / "update.zip"
        tmp_update = app_dir / "tmp_update"

        def _do_auto_update() -> bool:
            """Download zip, extract to tmp_update, run updater script that replaces app dir and relaunches. Returns True if started."""
            if not download_url or not asset_name:
                return False
            print(f"Downloading {asset_name}...")
            if not download_to_path(download_url, update_zip):
                return False
            print("Extracting...")
            if tmp_update.exists():
                shutil.rmtree(tmp_update, ignore_errors=True)
            tmp_update.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(update_zip) as zf:
                zf.extractall(tmp_update)
            # If zip had a single top-level folder (e.g. SMD_2-v4.5.3/), flatten so copy source is the contents
            entries = list(tmp_update.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                inner = entries[0]
                for p in inner.iterdir():
                    shutil.move(str(p), str(tmp_update / p.name))
                inner.rmdir()
            # Now tmp_update has Main.py, smd/, etc. at top level. Updater script copies to app_dir.
            if sys.platform == "win32":
                # When frozen (EXE), do not relaunch EXE—user must rebuild for updates to take effect.
                main_py = app_dir / "Main.py"
                run_cmd = app_dir / "update_run.cmd"
                if is_frozen:
                    post_update = (
                        "echo Update complete. Rebuild the EXE to use the new version.\n"
                        "pause\n"
                    )
                else:
                    run_cmd.write_text(
                        f'start "" "{sys.executable}" "{main_py.resolve()}"',
                        encoding="utf-8",
                    )
                    post_update = (
                        "call " + subprocess.list2cmdline([str(run_cmd)]) + "\n"
                        "del /q " + subprocess.list2cmdline([str(run_cmd)]) + " 2>nul\n"
                    )
                updater_bat = app_dir / "tmp_updater.bat"
                updater_bat.write_text(
                    "@echo off\n"
                    "cd /d " + subprocess.list2cmdline([str(app_dir.resolve())]) + "\n"
                    "timeout /t 2 /nobreak >nul\n"
                    "robocopy " + subprocess.list2cmdline([str(tmp_update), str(app_dir)]) + " /E /MOVE >nul 2>&1\n"
                    "rmdir /s /q " + subprocess.list2cmdline([str(tmp_update)]) + " 2>nul\n"
                    "del /q " + subprocess.list2cmdline([str(update_zip)]) + " 2>nul\n"
                    + post_update +
                    '(goto) 2>nul & del "%~f0"\n',
                    encoding="utf-8",
                )
                subprocess.Popen(
                    ["cmd", "/c", str(updater_bat)],
                    creationflags=subprocess.DETACHED_PROCESS,
                    cwd=str(app_dir),
                )
            else:
                # When frozen, do not relaunch—user must rebuild. Otherwise relaunch via python Main.py.
                if is_frozen:
                    launcher_shell = "echo 'Update complete. Rebuild the executable to use the new version.'\n"
                else:
                    launcher_shell = "exec " + " ".join(shutil.quote(str(x)) for x in [sys.executable, str(app_dir / "Main.py")]) + "\n"
                updater_sh = app_dir / "tmp_updater.sh"
                updater_sh.write_text(
                    "#!/bin/sh\n"
                    "cd " + shutil.quote(str(app_dir.resolve())) + "\n"
                    "sleep 2\n"
                    "cp -r tmp_update/. .\n"
                    "rm -rf tmp_update update.zip\n"
                    + launcher_shell,
                    encoding="utf-8",
                )
                updater_sh.chmod(0o700)
                subprocess.Popen(
                    ["/bin/sh", str(updater_sh)],
                    cwd=str(app_dir),
                    start_new_session=True,
                )
            print(Fore.GREEN + "Update will apply and the app will restart. Exiting..." + Style.RESET_ALL)
            sys.exit(0)

        if not is_frozen:
            if download_url and prompt_confirm("Download and update automatically?"):
                _do_auto_update()
            if prompt_confirm("Open the release page in your browser?"):
                webbrowser.open(release_url)
            return MainReturnCode.LOOP_NO_PROMPT
        if self.os_type == OSType.LINUX:
            if download_url and prompt_confirm("Download and update automatically?"):
                _do_auto_update()
            if prompt_confirm("Open the release page in your browser?"):
                webbrowser.open(release_url)
            return MainReturnCode.LOOP_NO_PROMPT
        if not prompt_confirm("Would you like to update now? (Otherwise you can open the release page to download.)"):
            if prompt_confirm("Open the release page in your browser?"):
                webbrowser.open(release_url)
            return MainReturnCode.LOOP_NO_PROMPT
        if use_os_package and download_url and asset_name:
            # Frozen Windows with OS-specific package: full in-place update (aria2c + extract + bat)
            print(f"Download URL: {download_url}")
            aria2c_exe = root_folder() / "third_party/aria2c/aria2c.exe"
            subprocess.run(
                [
                    aria2c_exe,
                    "-x",
                    "64",
                    "-k",
                    "1K",
                    "-s",
                    "64",
                    "-d",
                    str(Path.cwd().resolve()),
                    download_url,
                ]
            )
            zip_name = Path(download_url).name
            print(
                Fore.GREEN
                + "\n\nThe cursed update is about to begin. Prepare yourself."
                + Style.RESET_ALL
            )
            tmp_dir = Path.cwd() / "tmp"
            zip_path = Path.cwd() / zip_name
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
            zip_path.unlink(missing_ok=True)
            updater = Path.cwd() / "tmp_updater.bat"
            with updater.open("w", encoding="utf-8") as f:
                nul = [">", "NUL"]
                internal_dir = str(Path.cwd() / "_internal")
                sff_exe = str(Path.cwd() / "SFF.exe")
                tmp_dir = str(Path.cwd() / "tmp")
                convert = subprocess.list2cmdline
                f.writelines(
                    [
                        "@echo off\n",
                        "echo Killing SFF...\n",
                        f"taskkill /F /PID {os.getpid()}\n",
                        "echo SFF killed. Deleting old files...\n",
                        convert(["rmdir", "/s", "/q", internal_dir, *nul]) + "\n",
                        convert(["del", "/q", sff_exe, *nul]) + "\n",
                        "echo Old files deleted. Moving in new files...\n",
                        convert(["robocopy", "/E", "/MOVE", tmp_dir, str(Path.cwd()), *nul])
                        + "\n",
                        "echo UPDATE COMPLETE!!!! You can close this now\n",
                        '(goto) 2>nul & del "%~f0"',
                    ]
                )
            command = convert(["cmd", "/k", str(updater.resolve())])
            subprocess.Popen(
                command, creationflags=subprocess.DETACHED_PROCESS, shell=True  # type:ignore
            )
            return MainReturnCode.LOOP_NO_PROMPT
        if download_url:
            _do_auto_update()
        print("No update package found. Opening release page.")
        if prompt_confirm("Open the release page in your browser?"):
            webbrowser.open(release_url)
        return MainReturnCode.LOOP_NO_PROMPT

    def update_all_manifests(self) -> MainReturnCode:
        applist_ids = self._get_applist_ids()
        if applist_ids is None:
            print("This OS is not supported for this action.")
            return MainReturnCode.LOOP_NO_PROMPT
        steam_libs = get_steam_libs(self.steam_path)

        lua_manager = LuaManager(self.os_type)
        downloader = ManifestDownloader(self.provider, self.steam_path)
        steam_proc = (
            SteamProcess(self.steam_path, self.app_list_man.applist_folder)
            if self.app_list_man
            else None
        )
        explored_ids: list[int] = []
        for lib in steam_libs:
            steamapps = lib / "steamapps"
            acf_files = steamapps.glob("*.acf")
            for acf_file in acf_files:
                acf = ACFParser(acf_file)
                if not acf.needs_update():
                    continue
                if acf.id not in applist_ids:
                    continue
                if acf.id in explored_ids:
                    continue
                print(
                    Fore.YELLOW + f"\n{acf.name} needs an update!\n" + Style.RESET_ALL
                )
                explored_ids.append(acf.id)
                in_backup = str(acf.id) in lua_manager.named_ids
                # TODO: DRY this
                parsed_lua = lua_manager.fetch_lua(
                    LuaChoice.ADD_LUA,
                    lua_manager.saved_lua / f"{acf.id}.lua" if in_backup else None,
                )
                if parsed_lua is None:
                    return MainReturnCode.LOOP_NO_PROMPT
                if not in_backup:
                    lua_manager.backup_lua(parsed_lua)
                install_lua_to_steam(
                    self.steam_path,
                    str(parsed_lua.app_id),
                    lua_manager.saved_lua / f"{parsed_lua.app_id}.lua",
                )
                print(
                    Fore.YELLOW
                    + "\nDownloading Manifests:"
                    + Style.RESET_ALL
                )
                downloader.download_manifests(parsed_lua, auto_manifest=True)
        if steam_proc:
            steam_proc.prompt_launch_or_restart()
        print(
            Fore.GREEN + "\nSuccess! All game manifests have been updated!\n"
            "Try updating them via Steam."
            + Style.RESET_ALL
        )
        return MainReturnCode.LOOP

    def export_applist_ids(self, export_path: Path) -> MainReturnCode:
        """Export AppList IDs to a file"""
        try:
            ids = self._get_applist_ids()
            if ids is None:
                print(Fore.RED + "This OS is not supported for this action." + Style.RESET_ALL)
                return MainReturnCode.EXIT
            
            with export_path.open("w", encoding="utf-8") as f:
                for app_id in ids:
                    f.write(f"{app_id}\n")
            
            print(Fore.GREEN + f"✓ Exported {len(ids)} IDs to: {export_path}" + Style.RESET_ALL)
            return MainReturnCode.EXIT
            
        except Exception as e:
            print(Fore.RED + f"✗ Failed to export IDs: {e}" + Style.RESET_ALL)
            logger.error(f"Failed to export IDs: {e}", exc_info=True)
            return MainReturnCode.EXIT
    
    def process_batch_lua_files(self, file_paths: list[str], dry_run: bool = False) -> MainReturnCode:
        """Process multiple lua files in batch mode"""
        print(Fore.CYAN + f"\n=== Batch Processing {len(file_paths)} files ===" + Style.RESET_ALL)
        
        if dry_run:
            print(Fore.YELLOW + "DRY RUN MODE: No changes will be made" + Style.RESET_ALL)
        
        success_count = 0
        failed_files = []
        
        for i, file_path_str in enumerate(file_paths, 1):
            file_path = Path(file_path_str)
            print(Fore.CYAN + f"\n[{i}/{len(file_paths)}] Processing: {file_path.name}" + Style.RESET_ALL)
            
            if not file_path.exists():
                print(Fore.RED + f"✗ File not found: {file_path}" + Style.RESET_ALL)
                failed_files.append((file_path, "File not found"))
                continue
            
            if dry_run:
                print(Fore.YELLOW + f"Would process: {file_path}" + Style.RESET_ALL)
                success_count += 1
                continue
            
            try:
                result = self.process_lua_full(file_path)
                if result == MainReturnCode.EXIT:
                    print(Fore.RED + f"✗ Failed to process: {file_path.name}" + Style.RESET_ALL)
                    failed_files.append((file_path, "Processing failed"))
                else:
                    print(Fore.GREEN + f"✓ Successfully processed: {file_path.name}" + Style.RESET_ALL)
                    success_count += 1
            except Exception as e:
                print(Fore.RED + f"✗ Error processing {file_path.name}: {e}" + Style.RESET_ALL)
                logger.error(f"Batch processing error for {file_path}: {e}", exc_info=True)
                failed_files.append((file_path, str(e)))
        
        # Summary
        print(Fore.CYAN + "\n=== Batch Processing Summary ===" + Style.RESET_ALL)
        print(f"Total files: {len(file_paths)}")
        print(Fore.GREEN + f"Successful: {success_count}" + Style.RESET_ALL)
        print(Fore.RED + f"Failed: {len(failed_files)}" + Style.RESET_ALL)
        
        if failed_files:
            print(Fore.RED + "\nFailed files:" + Style.RESET_ALL)
            for file_path, reason in failed_files:
                print(f"  - {file_path.name}: {reason}")
        
        return MainReturnCode.EXIT
    
    def auto_update_manifests(self) -> MainReturnCode:
        """Automatically update manifests without user interaction"""
        print(Fore.CYAN + "\n=== Auto-Update Manifests ===" + Style.RESET_ALL)

        applist_ids = self._get_applist_ids()
        if applist_ids is None:
            print(Fore.RED + "This OS is not supported for this action." + Style.RESET_ALL)
            return MainReturnCode.EXIT

        steam_libs = get_steam_libs(self.steam_path)

        lua_manager = LuaManager(self.os_type)
        downloader = ManifestDownloader(self.provider, self.steam_path)
        
        updated_count = 0
        explored_ids: list[int] = []
        
        for lib in steam_libs:
            steamapps = lib / "steamapps"
            acf_files = steamapps.glob("*.acf")
            for acf_file in acf_files:
                acf = ACFParser(acf_file)
                if not acf.needs_update():
                    continue
                if acf.id not in applist_ids:
                    continue
                if acf.id in explored_ids:
                    continue
                
                print(f"Updating {acf.name}...")
                explored_ids.append(acf.id)
                in_backup = str(acf.id) in lua_manager.named_ids
                
                parsed_lua = lua_manager.fetch_lua(
                    LuaChoice.ADD_LUA,
                    lua_manager.saved_lua / f"{acf.id}.lua" if in_backup else None,
                )
                if parsed_lua is None:
                    print(Fore.RED + f"✗ Failed to fetch lua for {acf.name}" + Style.RESET_ALL)
                    continue
                    
                if not in_backup:
                    lua_manager.backup_lua(parsed_lua)
                install_lua_to_steam(
                    self.steam_path,
                    str(parsed_lua.app_id),
                    lua_manager.saved_lua / f"{parsed_lua.app_id}.lua",
                )
                downloader.download_manifests(parsed_lua, auto_manifest=True)
                updated_count += 1
        
        print(Fore.GREEN + f"\n✓ Updated {updated_count} games" + Style.RESET_ALL)
        return MainReturnCode.EXIT
    
    @music_toggle_decorator
    def recent_files_menu(self) -> MainReturnCode:
        """Display and process recent lua files"""
        recent_files = self.recent_files_manager.get_all()
        
        if not recent_files:
            print(Fore.YELLOW + "No recent files found." + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT
        
        print(Fore.CYAN + "\n=== Recent Files ===" + Style.RESET_ALL)
        
        # Create menu options with file names and paths
        options = []
        for file_path in recent_files:
            options.append((f"{file_path.name} ({file_path.parent})", file_path))
        
        options.append(("Clear recent files", "CLEAR"))
        
        choice = prompt_select(
            "Select a recent file to process:",
            options,
            cancellable=True
        )
        
        if choice is None:
            return MainReturnCode.LOOP_NO_PROMPT
        
        if choice == "CLEAR":
            if prompt_confirm("Clear all recent files?"):
                self.recent_files_manager.clear()
                print(Fore.GREEN + "✓ Recent files cleared" + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT
        
        # Process the selected file
        return self.process_lua_full(choice)
    
    @music_toggle_decorator
    def scan_library_menu(self) -> MainReturnCode:
        """Scan game library and generate report"""
        print(Fore.CYAN + "\n=== Library Scanner ===" + Style.RESET_ALL)
        
        lua_manager = LuaManager(self.os_type)
        scanner = LibraryScanner(self.steam_path, lua_manager.saved_lua)
        
        # Scan all games
        games = scanner.scan_all_games()
        
        if not games:
            print(Fore.YELLOW + "No games found in library." + Style.RESET_ALL)
            return MainReturnCode.LOOP_NO_PROMPT
        
        # Display report
        report = scanner.generate_report_text(games)
        print(report)
        
        # Ask what to do next
        needs_manifest = scanner.filter_needs_manifest(games)
        
        if needs_manifest:
            print(Fore.YELLOW + f"\n{len(needs_manifest)} games need manifest updates." + Style.RESET_ALL)
            
            choice = prompt_select(
                "What would you like to do?",
                [
                    ("Export report to JSON", "json"),
                    ("Export report to text", "text"),
                    ("Batch process games needing manifests", "batch"),
                ],
                cancellable=True
            )
            
            if choice == "json":
                output_path = root_folder(outside_internal=True) / "library_scan.json"
                if scanner.export_report(games, output_path, "json"):
                    print(Fore.GREEN + f"✓ Report exported to: {output_path}" + Style.RESET_ALL)
            elif choice == "text":
                output_path = root_folder(outside_internal=True) / "library_scan.txt"
                if scanner.export_report(games, output_path, "text"):
                    print(Fore.GREEN + f"✓ Report exported to: {output_path}" + Style.RESET_ALL)
            elif choice == "batch":
                print(Fore.YELLOW + "Batch processing not yet implemented." + Style.RESET_ALL)
        
        return MainReturnCode.LOOP_NO_PROMPT
    
    @music_toggle_decorator
    def analytics_dashboard_menu(self) -> MainReturnCode:
        """Display analytics dashboard"""
        print(Fore.CYAN + "\n=== Analytics Dashboard ===" + Style.RESET_ALL)
        
        dashboard = self.analytics_tracker.generate_dashboard_text()
        print(dashboard)
        
        choice = prompt_select(
            "\nWhat would you like to do?",
            [
                ("Export analytics to JSON", "export"),
            ],
            cancellable=True
        )
        
        if choice == "export":
            output_path = root_folder(outside_internal=True) / "analytics_export.json"
            if self.analytics_tracker.export_to_json(output_path):
                print(Fore.GREEN + f"✓ Analytics exported to: {output_path}" + Style.RESET_ALL)
        
        return MainReturnCode.LOOP_NO_PROMPT
