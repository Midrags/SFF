import argparse
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from colorama import Fore, Style
from colorama import init as color_init
from steam.client import SteamClient  # type: ignore

from InquirerPy import inquirer
from smd.prompts import prompt_confirm, prompt_select
from smd.steam_client import SteamInfoProvider
from smd.steam_path import init_steam_path
from smd.storage.settings import resolve_advanced_mode
from smd.strings import VERSION
from smd.structs import GAME_SPECIFIC_CHOICES, MainMenu, MainReturnCode, OSType
from smd.ui import UI
from smd.utils import root_folder

logger = logging.getLogger("smd")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler("debug.log")
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s::%(name)s::%(levelname)s::%(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
    )
)
logger.addHandler(fh)


def dump_crash():
    print("There was an error. You can also find this in crash.log:\n" + Fore.RED)
    with Path("crash.log").open("w+", encoding="utf-8") as f:
        traceback.print_exc(file=f)
        f.seek(0)
        print(f.read())
    print(Style.RESET_ALL, end="")


def main(ui: UI, args: argparse.Namespace) -> MainReturnCode:

    logger.debug(f"Root folder is {root_folder()}")

    logger.debug(f"Steam path is {ui.steam_path.resolve()}")

    if ui.app_list_man:
        logger.debug(f"AppList path is {ui.app_list_man.applist_folder.resolve()}")
    elif ui.sls_man:
        logger.debug(
            f"SLSSteam config file path is {ui.sls_man.sls_config_path.resolve()}"
        )
    
    # Handle --export-ids flag
    if args.export_ids:
        return ui.export_applist_ids(Path(args.export_ids))
    
    # Handle --batch flag
    if args.batch:
        return ui.process_batch_lua_files(args.batch, args.dry_run)
    
    # Handle --auto-update flag
    if args.auto_update:
        return ui.auto_update_manifests()

    print("\n==========================================\n")
    advanced_mode = resolve_advanced_mode()
    if ui.os_type == OSType.WINDOWS:
        exclude = [MainMenu.DL_MANIFEST_ONLY] if not advanced_mode else []
    elif ui.os_type == OSType.LINUX:
        exclude = [
            MainMenu.MANAGE_LUA,
            MainMenu.UPDATE_ALL_MANIFESTS,
            MainMenu.DLC_CHECK,
            MainMenu.INSTALL_MENU,
            MainMenu.CHECK_UPDATES,
            MainMenu.CRACK_GAME,
            MainMenu.REMOVE_DRM,
            MainMenu.DL_USER_GAME_STATS,
            MainMenu.OFFLINE_FIX
        ]
    else:
        exclude = []

    if first_launch:
        logger.debug(f"Took {time.time() - start_time}s to start")
    if args.file and first_launch:
        menu_choice = MainMenu.MANAGE_LUA
    else:
        menu_choice: MainMenu = prompt_select(
            "Choose:", list(MainMenu), exclude=exclude
        )

    if menu_choice == MainMenu.EXIT:
        return MainReturnCode.EXIT

    if menu_choice == MainMenu.SETTINGS:
        return ui.edit_settings_menu()
    
    if menu_choice == MainMenu.RECENT_FILES:
        return ui.recent_files_menu()
    
    if menu_choice == MainMenu.SCAN_LIBRARY:
        return ui.scan_library_menu()
    
    if menu_choice == MainMenu.ANALYTICS:
        return ui.analytics_dashboard_menu()

    if menu_choice == MainMenu.OFFLINE_FIX:
        return ui.offline_fix_menu()

    if menu_choice == MainMenu.MANAGE_APPLIST:
        return ui.applist_menu()

    if menu_choice in GAME_SPECIFIC_CHOICES:
        return ui.handle_game_specific(menu_choice)

    if menu_choice == MainMenu.CHECK_UPDATES:
        return ui.check_updates(ui.os_type)

    if menu_choice == MainMenu.DL_MANIFEST_ONLY:
        return ui.process_lua_minimal()

    if menu_choice == MainMenu.INSTALL_MENU:
        return ui.manage_context_menu()

    if menu_choice == MainMenu.SYNC_LUA_TO_STEAM:
        return ui.sync_lua_to_steam_menu()

    remove_game_opt = getattr(MainMenu, "REMOVE_GAME", None)
    if remove_game_opt and menu_choice == remove_game_opt:
        return ui.remove_game_menu()

    if menu_choice == MainMenu.UPDATE_ALL_MANIFESTS:
        return ui.update_all_manifests()

    if TYPE_CHECKING:  # For pyright to complain when i add shit to MainMenu
        _x: Literal[MainMenu.MANAGE_LUA] = menu_choice  # noqa: F841

    if args.file:
        path = Path(args.file)
        print(
            f"You have provided: {Fore.YELLOW + str(path.resolve()) + Style.RESET_ALL}"
        )
        return ui.process_lua_full(path)
    return ui.process_lua_full()


def _show_crash_gui(msg: str) -> None:
    """Show error in a message box when running as frozen exe (no console)."""
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0, msg[:3000], "SFF Error", 0x10
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        os.chdir(root_folder(outside_internal=True))
    except Exception as e:
        dump_crash()
        _show_crash_gui(f"Failed to set working directory:\n{e}\n\nSee crash.log")
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
        sys.exit(1)
    try:
        logger.debug(f"CWD is {str(Path.cwd().resolve())}")
        logger.debug(f"exe is {sys.executable}")
        start_time = time.time()
        parser = argparse.ArgumentParser(
                            prog='SFF',
                            description='SteamForge Fetcher - set up games for Steam with Lua scripts, manifests, and GreenLuma',
                            epilog='Modified from original SMD by jericjan. https://github.com/Midrags/SFF')
        parser.add_argument(
            "-f", "--file", help="A .lua file or ZIP file you want to process"
        )
        parser.add_argument(
            "-v", "--version", action="store_true", help="Show version and exit"
        )
        parser.add_argument(
            "-b", "--batch", nargs="+", help="Process multiple lua files in batch mode"
        )
        parser.add_argument(
            "-q", "--quiet", action="store_true", help="Suppress non-error output"
        )
        parser.add_argument(
            "--auto-update", action="store_true", help="Automatically update manifests without user interaction"
        )
        parser.add_argument(
            "--export-ids", help="Export AppList IDs to specified file"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Preview operations without executing them"
        )
        args = parser.parse_args()
        
        # Handle --version flag
        if args.version:
            print(f"SteamForge Fetcher (SFF) version {VERSION}")
            sys.exit(0)
        
        logger.debug(f"Received args: {args}")
        
        # Setup quiet mode if requested
        if args.quiet:
            # Redirect stdout to null, but keep stderr for errors
            sys.stdout = open(os.devnull, 'w')
        
        color_init()
        version_txt = f"Version: {VERSION}"
        print(
            Fore.GREEN
            + f"""  ____  _____  _____
 / ___|  \\ \\  / / __|
 \\___ \\   \\ \\/ /| _|
  ___) |   \\  / | |__
 |____/     \\/   \\___/

  SteamForge Fetcher (SFF)

┌────────────────────────────────────────┐
│{version_txt.center(40)}│
└────────────────────────────────────────┘ """
            + Style.RESET_ALL
        )
        sys.stdout.flush()
        sys.stderr.flush()
        # When running as frozen exe, console/prompt may not show until focused
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                hwnd = kernel32.GetConsoleWindow()
                if hwnd:
                    user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

        os_type = (
            OSType.WINDOWS
            if sys.platform == "win32"
            else (OSType.LINUX if sys.platform == "linux" else OSType.OTHER)
        )

        try:
            client = SteamClient()
            logger.debug(f"Steam client init in {time.time() - start_time}s")
            provider = SteamInfoProvider(client)
            steam_path = init_steam_path(os_type)
            logger.debug(f"Steam path init in {time.time() - start_time}s")
            ui = UI(provider, steam_path, os_type)
        except Exception:
            dump_crash()
            with Path("crash.log").open("r", encoding="utf-8") as f:
                _show_crash_gui(f.read())
            try:
                input("Press Enter to exit the program...")
            except EOFError:
                pass
            sys.exit(1)
        logger.debug(f"Init finished in {time.time() - start_time}s")
        return_code = None
        first_launch = True
        while True:
            try:
                return_code = main(ui, args)
                first_launch = False
            except KeyboardInterrupt:
                print(Fore.RED + "\nWait, don't go—\n" + Style.RESET_ALL)
                return_code = None
                break
            except Exception:
                dump_crash()
                input("Press Enter to restart the program...")
                continue

            if return_code == MainReturnCode.EXIT:
                break
            elif return_code == MainReturnCode.LOOP_NO_PROMPT:
                continue
            elif return_code == MainReturnCode.LOOP:
                # Use native confirm to avoid WNDPROC/WPARAM error (prompt_select cleanup on Windows)
                go_back = inquirer.confirm(
                    message="Go back to the Main Menu?",
                    default=True,
                    transformer=lambda x: "Yes" if x else "No (Exit)",
                ).execute()
                if not go_back:
                    break
        if return_code is not None:
            print(Fore.GREEN + "\nSee You Next Time!\n" + Style.RESET_ALL)
    except Exception:
        dump_crash()
        try:
            with Path("crash.log").open("r", encoding="utf-8") as f:
                _show_crash_gui(f.read())
        except Exception:
            _show_crash_gui(traceback.format_exc())
        try:
            input("Press Enter to exit the program...")
        except EOFError:
            pass  # No console (e.g. double-clicked exe); message box was already shown
        sys.exit(1)
