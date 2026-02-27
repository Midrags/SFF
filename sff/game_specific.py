"""gbe_fork and Steamless stuff in here"""

import hashlib
import logging
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Literal, NamedTuple, Optional, overload

from colorama import Fore, Style

from sff.app_injector.base import AppInjectionManager
from sff.manifest.downloader import ManifestDownloader
from sff.manifest.ugc_resolver import (
    DirectDownloadUrl,
    IUgcIdStrategy,
    StandardUgcIdStrategy,
    UgcIDResolver,
    WorkshopItemContext,
)
from sff.online_fix import apply_multiplayer_fix as apply_online_fix
from sff.prompts import (
    prompt_confirm,
    prompt_file,
    prompt_secret,
    prompt_select,
    prompt_text,
)
from sff.steam_client import SteamInfoProvider, get_product_info
from sff.steam_store import get_app_details_from_store
from sff.storage.settings import get_setting, set_setting
from sff.storage.vdf import vdf_load
from sff.structs import (
    GameSpecificChoices,
    GenEmuMode,
    MainMenu,
    MainReturnCode,
    ProductInfo,
    Settings,
)
from sff.utils import enter_path, root_folder

logger = logging.getLogger(__name__)


class ACFInfo(NamedTuple):
    app_id: str
    path: Path


AppName = str


class GameHandler:

    def __init__(
        self,
        steam_root: Path,
        library_path: Path,
        provider: SteamInfoProvider,
        injection_manager: AppInjectionManager,
    ):
        self.steam_root = steam_root
        self.steamapps_path = library_path / "steamapps"
        self.provider = provider
        self.injection_manager = injection_manager

    def _scan_games(self) -> list[tuple[AppName, ACFInfo]]:
        """Scan all Steam libraries and return list of (name, ACFInfo). No prompts."""
        games: list[tuple[AppName, ACFInfo]] = []
        seen_app_ids: set[str] = set()
        
        # Get all Steam libraries (including from all drives)
        try:
            from sff.storage.vdf import get_steam_libs
            steam_libs = get_steam_libs(self.steam_root)
            
            # Also scan all drives for additional libraries
            if os.name == 'nt':  # Windows
                from string import ascii_uppercase
                for drive_letter in ascii_uppercase:
                    drive = Path(f"{drive_letter}:/")
                    if not drive.exists():
                        continue
                    
                    potential_paths = [
                        drive / "SteamLibrary",
                        drive / "Steam",
                        drive / "Program Files (x86)" / "Steam",
                        drive / "Program Files" / "Steam",
                        drive / "Games" / "Steam",
                    ]
                    
                    for path in potential_paths:
                        steamapps = path / "steamapps"
                        if steamapps.exists() and path not in steam_libs:
                            steam_libs.append(path)
            
            # Scan all libraries
            for lib in steam_libs:
                steamapps = lib / "steamapps"
                if not steamapps.exists():
                    continue
                
                for acf_path in steamapps.glob("*.acf"):
                    try:
                        app_acf = vdf_load(acf_path)
                        app_state = app_acf.get("AppState", {})
                        name = app_state.get("name")
                        installdir = app_state.get("installdir")
                        app_id = app_state.get("appid")
                        
                        # Skip games with missing required fields
                        if not app_id or not installdir:
                            logger.warning(f"Skipping {acf_path.name}: missing appid or installdir")
                            continue
                        
                        # Skip duplicates (same game in multiple libraries)
                        if app_id in seen_app_ids:
                            continue
                        
                        seen_app_ids.add(app_id)
                        
                        # Check if game is actually installed
                        game_path = steamapps / "common" / installdir
                        if not game_path.exists():
                            continue
                        
                        games.append(
                            (name, ACFInfo(app_id, game_path))
                        )
                    except Exception as e:
                        logger.debug(f"Failed to parse {acf_path}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to scan Steam libraries: {e}")
            # Fallback to original behavior
            for path in self.steamapps_path.glob("*.acf"):
                try:
                    app_acf = vdf_load(path)
                    app_state = app_acf.get("AppState", {})
                    name = app_state.get("name")
                    installdir = app_state.get("installdir")
                    app_id = app_state.get("appid")
                    
                    if not app_id or not installdir:
                        logger.warning(f"Skipping {path.name}: missing appid or installdir")
                        continue
                    
                    games.append(
                        (name, ACFInfo(app_id, self.steamapps_path / "common" / installdir))
                    )
                except Exception as e:
                    logger.debug(f"Failed to parse {path}: {e}")
        
        return games

    def get_game_list(self) -> list[tuple[AppName, ACFInfo]]:
        """Return list of (name, ACFInfo) for all installed games. Used by GUI."""
        return self._scan_games()

    def get_game(self) -> Optional[ACFInfo]:
        """Get game from all Steam libraries across all drives (interactive prompt)."""
        games = self._scan_games()
        if not games:
            print(Fore.RED + "No games found in any Steam library!" + Style.RESET_ALL)
            return None
        return prompt_select(
            "Select a game (You can type btw)",
            games,
            fuzzy=True,
            max_height=10,
            cancellable=True,
        )

    def find_steam_dll(self, game_path: Path) -> Optional[Path]:
        files = list(game_path.rglob("steam_api*.dll"))
        if len(files) > 1:
            return prompt_select(
                "More than one DLL found. Pick one:",
                [(str(x.relative_to(game_path)), x) for x in files],
            )
        if len(files) == 1:
            return files[0]
        return None

    @overload
    def run_gen_emu(
        self, app_id: str, mode: Literal[GenEmuMode.USER_GAME_STATS]
    ) -> None: ...

    @overload
    def run_gen_emu(
        self,
        app_id: str,
        mode: Literal[GenEmuMode.STEAM_SETTINGS, GenEmuMode.ALL],
        dst_steam_settings_folder: Path,
    ) -> None: ...

    def run_gen_emu(
        self,
        app_id: str,
        mode: GenEmuMode,
        dst_steam_settings_folder: Optional[Path] = None,
    ):
        if mode in (GenEmuMode.STEAM_SETTINGS, GenEmuMode.ALL):
            if dst_steam_settings_folder is None:
                raise ValueError(
                    "dst_steam_settings_folder is required for STEAM_SETTINGS or ALL."
                )

        tools_folder = root_folder() / "third_party/gbe_fork_tools/generate_emu_config/"
        config_exe = tools_folder / "generate_emu_config.exe"
        if (
            (user := get_setting(Settings.STEAM_USER)) is None
            or (password := get_setting(Settings.STEAM_PASS)) is None
            or (steam32_id := get_setting(Settings.STEAM32_ID)) is None
        ):
            print(
                "No steam credentials saved. Please provide them. "
                "This is all stored locally."
            )
            user = prompt_text("Username:")
            password = prompt_secret("Password:")
            steam32_id = prompt_text(
                "Your Steam32 ID:",
                long_instruction="You can try visiting https://steamid.xyz/ "
                "to find it.",
            )
            set_setting(Settings.STEAM_USER, user)
            set_setting(Settings.STEAM_PASS, password)
            set_setting(Settings.STEAM32_ID, steam32_id)

        env = os.environ.copy()
        env["GSE_CFG_USERNAME"] = user
        env["GSE_CFG_PASSWORD"] = password

        extra_args: list[str] = []
        if mode == GenEmuMode.USER_GAME_STATS:
            extra_args.extend(["-skip_con", "-skip_inv"])
        cmds = [str(config_exe.absolute()), "-clean", *extra_args, app_id]
        logger.debug(f"Running {shlex.join(cmds)}")
        subprocess.run(
            cmds,
            env=env,
            cwd=str(tools_folder.absolute()),
        )
        backup_folder = tools_folder / f"backup/{app_id}"
        src_steam_settings = tools_folder / f"output/{app_id}/steam_settings"

        steam_stats_folder = self.steam_root / "appcache/stats"

        if mode == GenEmuMode.USER_GAME_STATS or mode == GenEmuMode.ALL:
            bin_files = backup_folder.glob("*.bin")
            bin_file_count = 0
            for bin_file in bin_files:
                bin_file_count += 1
                shutil.copy(bin_file, steam_stats_folder)
                print(f"{bin_file.name} copied to {str(steam_stats_folder)}")

            if bin_file_count == 0:
                id_64 = prompt_text(
                    "No .bin files found. Go to https://steamladder.com/ and "
                    "find the game you want, "
                    "then paste in here the Steam64 ID of a "
                    "random user that owns that game:",
                    long_instruction="Make sure the game actually HAS "
                    "Steam achievements!!"
                    " Type a blank if you want to exit",
                ).strip()
                if not id_64:
                    return
                with Path(
                    r"third_party\gbe_fork_tools\generate_emu_config\top_owners_ids.txt"
                ).open("w", encoding="utf-8") as f:
                    f.write(id_64)
                self.run_gen_emu(app_id, GenEmuMode.USER_GAME_STATS)

            src_user_stats = root_folder() / "static/UserGameStats_steamid_appid.bin"
            dst_user_stats = (
                steam_stats_folder / f"UserGameStats_{steam32_id}_{app_id}.bin"
            )
            if not dst_user_stats.exists():
                shutil.copy(src_user_stats, dst_user_stats)
                print(
                    f"{str(src_user_stats.relative_to(root_folder()))} copied to "
                    + str(dst_user_stats)
                )
            else:
                print(f"{dst_user_stats.name} already exists. Skipping this step.")

        if mode == GenEmuMode.STEAM_SETTINGS or mode == GenEmuMode.ALL:
            assert dst_steam_settings_folder is not None
            shutil.copytree(
                src_steam_settings, dst_steam_settings_folder, dirs_exist_ok=True
            )
            print(
                f"{str(src_steam_settings.relative_to(root_folder()))} copied to "
                + str(dst_steam_settings_folder)
            )

    def _crack_dll_core(self, app_id: str, dll_path: Path):
        gbe_fork_folder = root_folder() / "third_party/gbe_fork/"
        with dll_path.open("rb") as f:
            target_hash = hashlib.md5(f.read()).hexdigest()
        with (gbe_fork_folder / dll_path.name).open("rb") as f:
            source_hash = hashlib.md5(f.read()).hexdigest()
        if source_hash == target_hash:
            print("DLL already cracked.")
            return
        print("DLL has not been cracked")

        api_folder = dll_path.parent

        gse_app_folder = Path.home() / f"AppData/Roaming/GSE Saves/{app_id}"

        if not gse_app_folder.exists():
            print("GSE Saves folder doesn't exist. Creating...")
            gse_app_folder.mkdir(parents=True)

        backup_name = dll_path.parent / ("OG_" + dll_path.name)
        if backup_name.exists():
            backup_name.unlink()
        dll_path.rename(backup_name)

        def ignore_other_dll(dir: str, files: list[str]) -> set[str]:
            if dll_path.name in files:
                api_files = {"steam_api.dll", "steam_api64.dll"}
                api_files.remove(dll_path.name)
                return api_files
            return set()  # type: ignore

        shutil.copytree(
            gbe_fork_folder, api_folder, dirs_exist_ok=True, ignore=ignore_other_dll
        )
        (api_folder / "steam_appid.txt").write_text(app_id, "utf-8")

    def crack_dll(self, app_id: str, dll_path: Path):
        self._crack_dll_core(app_id, dll_path)
        gen_achievements = prompt_confirm(
            "Would you like to generate config files for gbe_fork? "
            "(Contains achievement data)"
        )
        if gen_achievements:
            self.run_gen_emu(
                app_id, GenEmuMode.STEAM_SETTINGS, dll_path.parent / "steam_settings"
            )

    def apply_steamless(self, app_info: ACFInfo):
        game_exe = self.select_executable(app_info)

        steamless_exe = root_folder() / "third_party/steamless/Steamless.CLI.exe"

        output = subprocess.run(
            [str(steamless_exe.absolute()), str(game_exe.absolute())],
            encoding="utf-8",
            capture_output=True,
        )
        if "Successfully unpacked file!" in output.stdout:
            print("Steamless applied!")
            unpacked = game_exe.parent / (game_exe.name + ".unpacked.exe")
            game_exe.unlink()
            unpacked.rename(game_exe)

        else:
            print(output.stdout)
            print("Steamless failed...")

    def _prompt_manual_exe(self, app_info: ACFInfo):
        subprocess.run(["explorer", app_info.path])
        game_exe = prompt_file(
            "Drag the game .exe here and press Enter:",
        )
        return game_exe

    def _get_windows_execs(self, info: ProductInfo, app_id: int) -> list[str]:
        launches = enter_path(info, "apps", app_id, "config", "launch")
        return [
            launch["executable"]
            for launch in launches.values()
            if enter_path(launch, "config", "oslist") == "windows"
        ]

    def select_executable(self, app_info: ACFInfo) -> Path:
        """Selects EXE to get used for Steamless"""
        info = get_product_info(self.provider, [int(app_info.app_id)])

        windows_exes = self._get_windows_execs(info, int(app_info.app_id))
        if not windows_exes:
            return self._prompt_manual_exe(app_info)

        if len(windows_exes) == 1:
            return app_info.path / windows_exes[0]

        chosen = prompt_select("Choose the exe:", windows_exes)
        return app_info.path / chosen

    def download_workshop_manifest(self, app_id: str):
        strats: list[IUgcIdStrategy] = [StandardUgcIdStrategy()]
        ugc_resolver = UgcIDResolver(strats)
        regex = re.compile(
            r"(?<=steamcommunity.com\/sharedfiles\/filedetails\/\?id=)\d+|^\d+$"
        )

        def validate(x: str) -> bool:
            return bool(regex.search(x))

        def filter(x: str) -> int:
            match = regex.search(x)
            assert match is not None  # lmao
            return int(match.group())

        workshop_id: int = prompt_text(
            "Paste workshop item URL or item ID:",
            validator=validate,
            filter=filter
        )
        ctx = WorkshopItemContext(self.provider.client, workshop_id)
        content, method = ugc_resolver.resolve(ctx)
        if isinstance(content, DirectDownloadUrl):
            print("This is a legacy workshop item. "
                  "It can be directly downloaded through"
                  " the following URL. It's just a ZIP file:\n"
                  f"{Fore.BLUE + content.url + Style.RESET_ALL}")
        else:  # HContentFile type
            print(f"Found UGC ID via {method} method: {content.ugc_id}")
            downloader = ManifestDownloader(self.provider, self.steam_root)
            downloader.download_workshop_item(app_id, str(content.ugc_id))
            print(
                Fore.GREEN
                + "Workshop item manifest downloaded! Try downloading it now."
                + Style.RESET_ALL
            )

    def apply_multiplayer_fix(self, app_info: ACFInfo) -> None:
        """Apply multiplayer fix from online-fix.me"""
        print("\n" + Fore.CYAN + "Multiplayer Fix (online-fix.me)" + Style.RESET_ALL)
        print("This will download and apply a multiplayer fix for the selected game.")
        print("The fix will be extracted directly to the game folder.\n")

        # Get game name: ACF from the same library as the game folder (not default steamapps)
        game_name = "Unknown"
        steamapps_for_game = app_info.path.parent.parent  # path is .../steamapps/common/GameName
        acf_path = steamapps_for_game / f"appmanifest_{app_info.app_id}.acf"
        if acf_path.exists():
            try:
                acf_data = vdf_load(acf_path)
                game_name = acf_data.get("AppState", {}).get("name", "Unknown")
            except Exception as e:
                logger.warning(f"Failed to read game name from ACF: {e}")

        # Fallback: fetch official name from Steam Store API so search finds the right game
        if not game_name or game_name == "Unknown":
            try:
                details = get_app_details_from_store(int(app_info.app_id))
                if details and details.get("name"):
                    game_name = details["name"].strip()
            except Exception as e:
                logger.debug("Steam Store API fallback for game name: %s", e)

        print(f"Game: {Fore.YELLOW}{game_name}{Style.RESET_ALL}")
        print(f"Folder: {Fore.YELLOW}{app_info.path}{Style.RESET_ALL}\n")

        if not prompt_confirm("Continue with multiplayer fix?"):
            return

        # Apply the fix
        success = apply_online_fix(game_name, app_info.path)
        
        if success:
            print("\n" + Fore.GREEN + "Multiplayer fix applied successfully!" + Style.RESET_ALL)
            print("You can now launch the game and try multiplayer features.")
        else:
            print("\n" + Fore.RED + "Failed to apply multiplayer fix." + Style.RESET_ALL)
            print("Check the error messages above for details.")

    def manage_dlc_unlockers(self, app_info: ACFInfo) -> None:
        """Manage DLC unlockers (CreamInstaller-compatible) for a game.
        
        For Steam: Installs SmokeAPI OR CreamAPI (user preference). Koaloader proxy mode
        is optional. Matches CreamInstaller behavior exactly.
        """
        from sff.dlc_unlockers.manager import UnlockerManager
        from sff.dlc_unlockers.downloader import GitHubReleaseDownloader
        from sff.dlc_unlockers.base import Platform, UnlockerType
        from sff.storage.settings import get_setting, set_setting
        import asyncio
        
        # Resolve settings with defaults (CreamInstaller: UseSmokeAPI=True, Proxy=optional)
        use_smokeapi = get_setting(Settings.USE_SMOKEAPI)
        if use_smokeapi is None or isinstance(use_smokeapi, str):
            use_smokeapi = True
            set_setting(Settings.USE_SMOKEAPI, True)
        
        use_koaloader = get_setting(Settings.USE_KOALOADER_PROXY)
        if use_koaloader is None or isinstance(use_koaloader, str):
            use_koaloader = False
            set_setting(Settings.USE_KOALOADER_PROXY, False)
        
        print(f"\n{Fore.CYAN}=== DLC Unlockers (CreamInstaller) ==={Style.RESET_ALL}")
        print(f"Game: {app_info.path.name}  |  App ID: {app_info.app_id}")
        print(f"Mode: {Fore.YELLOW}{'SmokeAPI' if use_smokeapi else 'CreamAPI'}{Style.RESET_ALL}  |  "
              f"Proxy: {Fore.YELLOW}{'Koaloader ON' if use_koaloader else 'Direct (off)'}{Style.RESET_ALL}\n")
        
        manager = UnlockerManager(self.steam_root)
        platform = manager.detect_platform(app_info.path)
        print(f"Platform: {Fore.GREEN}{platform.value.upper()}{Style.RESET_ALL}\n")
        
        compatible_unlockers = manager.get_compatible_unlockers(platform)
        if not compatible_unlockers:
            print(Fore.RED + "No compatible unlockers for this platform." + Style.RESET_ALL)
            return
        
        installed_unlockers = [u for u in compatible_unlockers if u.is_installed(app_info.path)]
        if installed_unlockers:
            print(f"{Fore.YELLOW}Installed:{Style.RESET_ALL} " + ", ".join(u.display_name for u in installed_unlockers))
            print()
        
        # Build menu
        menu_options = ["Install DLC Unlockers", "Uninstall DLC Unlockers", "Configure (SmokeAPI/CreamAPI, Koaloader)", "Go back"]
        choice = prompt_select("Select:", menu_options)
        
        if choice == "Go back":
            return
        
        if choice == "Configure (SmokeAPI/CreamAPI, Koaloader)":
            use_smokeapi = prompt_confirm(
                "Use SmokeAPI? (No = CreamAPI)",
                true_msg="SmokeAPI",
                false_msg="CreamAPI",
                default=use_smokeapi
            )
            set_setting(Settings.USE_SMOKEAPI, use_smokeapi)
            use_koaloader = prompt_confirm(
                "Use Koaloader proxy mode? (No = direct mode)",
                true_msg="Yes (proxy)",
                false_msg="No (direct)",
                default=use_koaloader
            )
            set_setting(Settings.USE_KOALOADER_PROXY, use_koaloader)
            print(Fore.GREEN + "Settings saved. Run Install again to apply." + Style.RESET_ALL)
            return
        
        if choice == "Uninstall DLC Unlockers":
            if not installed_unlockers:
                print(Fore.YELLOW + "Nothing to uninstall." + Style.RESET_ALL)
                return
            print(f"\n{Fore.CYAN}Uninstalling...{Style.RESET_ALL}\n")
            success_count = 0
            for unlocker in installed_unlockers:
                print(f"  Uninstalling {unlocker.display_name}...", end=" ")
                if unlocker.uninstall(app_info.path):
                    print(Fore.GREEN + "✓" + Style.RESET_ALL)
                    success_count += 1
                else:
                    print(Fore.RED + "✗" + Style.RESET_ALL)
            if success_count > 0:
                print(Fore.GREEN + f"\nUninstalled {success_count} unlocker(s)." + Style.RESET_ALL)
            return
        
        # Install DLC Unlockers
        print(f"\n{Fore.CYAN}Installing DLC unlockers...{Style.RESET_ALL}")
        steam_unlocker = UnlockerType.SMOKEAPI if use_smokeapi else UnlockerType.CREAMAPI
        
        if platform == Platform.STEAM:
            if use_koaloader:
                to_install = [UnlockerType.KOALOADER, UnlockerType.SMOKEAPI]
                print(f"Mode: Koaloader + SmokeAPI (proxy)")
            else:
                to_install = [steam_unlocker]
                print(f"Mode: {steam_unlocker.value} (direct)")
        else:
            to_install = [u.unlocker_type for u in compatible_unlockers]
        
        cache_dir_val = get_setting(Settings.DLC_UNLOCKER_CACHE_DIR)
        cache_dir = Path(cache_dir_val) if cache_dir_val and str(cache_dir_val) != "(unset)" else root_folder() / "dlc_unlocker_cache"
        
        downloader = GitHubReleaseDownloader(cache_dir)
        print(f"\n{Fore.CYAN}Downloading...{Style.RESET_ALL}")
        
        unlocker_dirs = {}
        for utype in to_install:
            if utype == UnlockerType.SMOKEAPI and not use_smokeapi:
                continue
            if utype == UnlockerType.CREAMAPI and use_smokeapi and not use_koaloader:
                continue
            print(f"  {utype.value}...", end=" ")
            try:
                dll_dir = asyncio.run(downloader.download_latest(utype))
                if dll_dir:
                    unlocker_dirs[utype] = dll_dir
                    print(Fore.GREEN + "✓" + Style.RESET_ALL)
                else:
                    print(Fore.RED + "✗" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"✗ {e}" + Style.RESET_ALL)
        
        if platform == Platform.STEAM:
            needed = UnlockerType.SMOKEAPI if use_smokeapi else UnlockerType.CREAMAPI
            if use_koaloader:
                needed = [UnlockerType.KOALOADER, UnlockerType.SMOKEAPI]
            else:
                needed = [needed]
            if not all(u in unlocker_dirs for u in needed):
                print(Fore.RED + "\nDownload failed. Aborting." + Style.RESET_ALL)
                return
        
        print(f"\n{Fore.CYAN}Installing...{Style.RESET_ALL}")
        # Fetch game's DLC list from Steam so unlocker config includes all DLCs (avoids "removing" DLCs that were added via LUA/GreenLuma)
        dlc_ids = []
        try:
            base_info = get_product_info(self.provider, [int(app_info.app_id)])
            base_trimmed = enter_path(base_info, "apps", int(app_info.app_id))
            listofdlc = enter_path(base_trimmed, "extended", "listofdlc")
            if listofdlc and isinstance(listofdlc, str):
                dlc_ids = [int(x.strip()) for x in listofdlc.split(",") if x.strip().isdigit()]
                if dlc_ids:
                    logger.info(f"Including {len(dlc_ids)} DLC(s) in unlocker config so they remain visible")
        except Exception as e:
            logger.debug(f"Could not fetch DLC list for unlocker config: {e}")
        success_count = 0
        
        if platform == Platform.STEAM:
            if use_koaloader:
                koaloader = manager.get_unlocker_by_type(UnlockerType.KOALOADER)
                smokeapi = manager.get_unlocker_by_type(UnlockerType.SMOKEAPI)
                if koaloader and smokeapi and UnlockerType.KOALOADER in unlocker_dirs and UnlockerType.SMOKEAPI in unlocker_dirs:
                    print(f"  Koaloader + SmokeAPI...", end=" ")
                    success = koaloader.install(
                        app_info.path, dlc_ids, int(app_info.app_id),
                        koaloader_dir=unlocker_dirs[UnlockerType.KOALOADER],
                        smokeapi_dir=unlocker_dirs[UnlockerType.SMOKEAPI]
                    )
                    if success:
                        print(Fore.GREEN + "✓" + Style.RESET_ALL)
                        success_count = 1
                    else:
                        print(Fore.RED + "✗" + Style.RESET_ALL)
            else:
                unlocker = manager.get_unlocker_by_type(steam_unlocker)
                if unlocker and steam_unlocker in unlocker_dirs:
                    print(f"  {unlocker.display_name}...", end=" ")
                    if steam_unlocker == UnlockerType.SMOKEAPI:
                        success = unlocker.install(
                            app_info.path, dlc_ids, int(app_info.app_id),
                            smokeapi_dir=unlocker_dirs[UnlockerType.SMOKEAPI]
                        )
                    else:
                        unlocker.downloader = downloader
                        success = unlocker.install(app_info.path, dlc_ids, int(app_info.app_id))
                    if success:
                        print(Fore.GREEN + "✓" + Style.RESET_ALL)
                        success_count = 1
                    else:
                        print(Fore.RED + "✗" + Style.RESET_ALL)
        else:
            for unlocker in compatible_unlockers:
                if unlocker.unlocker_type in [UnlockerType.UPLAY_R1, UnlockerType.UPLAY_R2]:
                    dll_dir = unlocker_dirs.get(unlocker.unlocker_type)
                    if dll_dir:
                        print(f"  {unlocker.display_name}...", end=" ")
                        if unlocker.install(app_info.path, dlc_ids, int(app_info.app_id), dll_dir):
                            print(Fore.GREEN + "✓" + Style.RESET_ALL)
                            success_count += 1
                        else:
                            print(Fore.RED + "✗" + Style.RESET_ALL)
        
        print(f"\n{Fore.CYAN}{'='*45}{Style.RESET_ALL}")
        if success_count > 0:
            print(Fore.GREEN + f"✓ Installed {success_count} unlocker(s)!" + Style.RESET_ALL)
        else:
            print(Fore.RED + "✗ Installation failed." + Style.RESET_ALL)
        print(f"{Fore.CYAN}{'='*45}{Style.RESET_ALL}\n")

    def execute_choice(
        self, choice: GameSpecificChoices, *, override_game: Optional[ACFInfo] = None
    ) -> MainReturnCode:
        app_info = override_game if override_game is not None else self.get_game()
        if app_info is None:
            return MainReturnCode.LOOP_NO_PROMPT
        
        # Validate app_id is not None
        if app_info.app_id is None:
            print(Fore.RED + "Error: Game has no App ID. The ACF file may be corrupted." + Style.RESET_ALL)
            return MainReturnCode.LOOP
            
        if choice == MainMenu.CRACK_GAME:
            dll = self.find_steam_dll(app_info.path)
            if dll is None:
                print(
                    "Could not find steam_api DLL. "
                    "Maybe you haven't downloaded the game yet..."
                )
            else:
                self.crack_dll(app_info.app_id, dll)
        elif choice == MainMenu.REMOVE_DRM:
            self.apply_steamless(app_info)
        elif choice == MainMenu.DL_USER_GAME_STATS:
            self.run_gen_emu(app_info.app_id, GenEmuMode.USER_GAME_STATS)
        elif choice == MainMenu.DLC_CHECK:
            self.injection_manager.dlc_check(self.provider, int(app_info.app_id))
        elif choice == MainMenu.DL_WORKSHOP_ITEM:
            self.download_workshop_manifest(app_info.app_id)
        elif choice == MainMenu.MULTIPLAYER_FIX:
            self.apply_multiplayer_fix(app_info)
        elif choice == MainMenu.MANAGE_DLC_UNLOCKERS:
            self.manage_dlc_unlockers(app_info)
        return MainReturnCode.LOOP
