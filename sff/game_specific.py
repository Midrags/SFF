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

"""gbe_fork and Steamless stuff in here"""

import hashlib
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from colorama import Fore, Style

from sff.app_injector.base import AppInjectionManager
from sff.manifest.collections import get_collection_children
from sff.manifest.downloader import ManifestDownloader
from sff.manifest.workshop_tracker import add as tracker_add
from sff.manifest.workshop_tracker import get_all as tracker_get_all
from sff.manifest.workshop_tracker import update_time as tracker_update_time
from sff.manifest.ugc_resolver import (
    DirectDownloadUrl,
    IUgcIdStrategy,
    StandardUgcIdStrategy,
    UgcIDResolver,
    WorkshopItemContext,
    get_workshop_time_updated,
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
from sff.strings import STEAM_WEB_API_KEY
from sff.utils import enter_path, root_folder
from typing import Literal, NamedTuple, Optional, overload


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

    def _scan_games(self):
        games = []
        seen_app_ids = set()
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
                        if not app_id or not installdir:
                            logger.warning(f"Skipping {acf_path.name}: missing appid or installdir")
                            continue
                        if app_id in seen_app_ids:
                            continue
                        seen_app_ids.add(app_id)
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

    def get_game_list(self):
        return self._scan_games()

    def get_game(self):
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

    def find_steam_dll(self, game_path):
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
    ): ...

    @overload
    def run_gen_emu(
        self,
        app_id: str,
        mode: Literal[GenEmuMode.STEAM_SETTINGS, GenEmuMode.ALL],
        dst_steam_settings_folder: Path,
    ): ...

    def run_gen_emu(
        self,
        app_id: str,
        mode: GenEmuMode,
        dst_steam_settings_folder = None,
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
        extra_args = []
        if mode == GenEmuMode.USER_GAME_STATS:
            extra_args.extend(["-skip_con", "-skip_inv"])
        cmds = [str(config_exe.absolute()), "-clean", *extra_args, app_id]
        logger.debug(f"Running {shlex.join(cmds)}")
        _run_kwargs = {
            "env": env,
            "cwd": str(tools_folder.absolute()),
        }
        if sys.platform == "win32":
            _run_kwargs["creationflags"] = 0x08000000

        subprocess.run(cmds, **_run_kwargs)
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

    def _crack_dll_core(self, app_id, dll_path):
        """Swap steam_api DLL with Goldberg. Returns False if already cracked."""
        gbe_fork_folder = root_folder() / "third_party/gbe_fork/"
        gbe_dll = gbe_fork_folder / dll_path.name
        if not gbe_dll.exists():
            print(f"Goldberg DLL not found: {gbe_dll}")
            return False
        with dll_path.open("rb") as f:
            target_hash = hashlib.md5(f.read()).hexdigest()
        with gbe_dll.open("rb") as f:
            source_hash = hashlib.md5(f.read()).hexdigest()
        if source_hash == target_hash:
            print("DLL already cracked.")
            return False
        print("DLL has not been cracked")
        api_folder = dll_path.parent
        gse_app_folder = Path.home() / "AppData" / "Roaming" / "GSE Saves" / app_id
        if not gse_app_folder.exists():
            gse_app_folder.mkdir(parents=True)
        print(f"Save data: {gse_app_folder}")
        backup_name = dll_path.parent / ("OG_" + dll_path.name)
        if backup_name.exists():
            backup_name.unlink()
        dll_path.rename(backup_name)
        shutil.copy2(gbe_dll, dll_path)
        (api_folder / "steam_appid.txt").write_text(app_id, "utf-8")
        return True

    def crack_dll(self, app_id, dll_path):
        swapped = self._crack_dll_core(app_id, dll_path)
        if not swapped:
            return
        game_dir = str(dll_path.parent)
        settings_dir = dll_path.parent / "steam_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        # scan steam interfaces from the original backup DLL
        from sff.fix_game.goldberg_applier import GoldbergApplier
        from sff.fix_game.cache import FixGameCache
        backup_dll = dll_path.parent / ("OG_" + dll_path.name)
        if backup_dll.exists():
            GoldbergApplier(FixGameCache().goldberg_dir).generate_interfaces_file(
                str(backup_dll), str(settings_dir)
            )
            print("✓ Generated steam_interfaces.txt")
        # generate steam_settings (configs, languages, depots) — no credentials needed
        from sff.fix_game.config_generator import GoldbergConfigGenerator
        GoldbergConfigGenerator().generate(
            app_id=int(app_id),
            target_dir=game_dir,
            player_name="Player",
            log_func=print,
        )
        print(f"\nCrack complete. Run the game — saves go to: "
              f"{Path.home() / 'AppData' / 'Roaming' / 'GSE Saves' / app_id}")

    def apply_steamless(self, app_info, exe_path = None):
        """Run Steamless on a game executable to strip Steam DRM.

        Returns a (success, message) tuple so callers can surface a clear
        result in the GUI instead of having to scrape stdout.
        """
        game_exe = exe_path if exe_path is not None else self.select_executable(app_info)
        if game_exe is None:
            msg = "Steamless: no executable selected"
            print(Fore.RED + msg + Style.RESET_ALL)
            return False, msg

        game_exe = Path(game_exe)
        if not game_exe.exists():
            msg = f"Steamless: file not found — {game_exe}"
            print(Fore.RED + msg + Style.RESET_ALL)
            return False, msg
        if game_exe.suffix.lower() != ".exe":
            msg = (
                f"Steamless: '{game_exe.name}' is not a .exe file. "
                "Pick the game's main executable (the one Steam launches)."
            )
            print(Fore.RED + msg + Style.RESET_ALL)
            return False, msg
        # Quick PE magic check so we fail with a clear message instead of
        # the cryptic "Invalid input file" Steamless prints for non-PE input.
        try:
            with game_exe.open("rb") as f:
                if f.read(2) != b"MZ":
                    msg = (
                        f"Steamless: '{game_exe.name}' is not a Windows PE binary "
                        "(no MZ header). The file is corrupted or not actually an exe."
                    )
                    print(Fore.RED + msg + Style.RESET_ALL)
                    return False, msg
        except OSError as e:
            msg = f"Steamless: cannot read '{game_exe.name}': {e}"
            print(Fore.RED + msg + Style.RESET_ALL)
            return False, msg

        # Steamless dispatch:
        #   * Windows           : Steamless.CLI.exe directly
        #   * Linux + .NET 9    : `dotnet Steamless.CLI.dll` (preferred)
        #   * Linux + Wine only : `wine Steamless.CLI.exe`   (fallback)
        steamless_path = None
        steamless_dir = None
        run_env = None
        run_cmd_prefix: list[str] = []

        if sys.platform != "win32":
            dll_candidates = [
                root_folder() / "third_party" / "linux" / "deps" / "Steamless" / "Steamless.CLI.dll",
                root_folder() / "third_party" / "Steamless" / "Steamless.CLI.dll",
                root_folder() / "third_party" / "Steamless.CLI.dll",
            ]
            for c in dll_candidates:
                if c.exists():
                    steamless_path = c
                    steamless_dir = c.parent
                    break
            if steamless_path is not None:
                from sff.dotnet_utils import get_dotnet_path
                dotnet_exe = get_dotnet_path()
                if not dotnet_exe:
                    msg = "Steamless: .NET 9 not found. Run Linux Tools Setup."
                    print(Fore.RED + msg + Style.RESET_ALL)
                    return False, msg
                run_cmd_prefix = [dotnet_exe]
                import os as _os_env
                run_env = _os_env.environ.copy()
                run_env.setdefault("DOTNET_ROOT", str(Path(dotnet_exe).parent))

        if steamless_path is None:
            steamless_exe = root_folder() / "third_party/steamless/Steamless.CLI.exe"
            if not steamless_exe.exists():
                # Fall back to the layout the Fix Game pipeline ships with.
                alt = root_folder() / "third_party/Steamless/Steamless.CLI.exe"
                if alt.exists():
                    steamless_exe = alt
                else:
                    msg = f"Steamless not found at {steamless_exe}"
                    print(Fore.RED + msg + Style.RESET_ALL)
                    return False, msg
            steamless_path = steamless_exe
            steamless_dir = steamless_exe.parent
            if sys.platform != "win32":
                if shutil.which("wine") is None:
                    msg = "Steamless: Wine not installed. Install Wine or .NET 9 (Linux Tools Setup)."
                    print(Fore.RED + msg + Style.RESET_ALL)
                    return False, msg
                run_cmd_prefix = ["wine"]

        # --exp turns on experimental variants for newer SteamStub
        # revisions (Teardown, Doom Eternal, modern UE5 / Unity titles).
        # --realign and --recalcchecksum keep section alignment / file
        # checksum valid on x64 binaries that ship with mismatched layout
        # after the wrapper strip. Same flag set SteamAutoCrack uses.
        cmd = run_cmd_prefix + [
            str(steamless_path.absolute()),
            "--exp",
            "--realign",
            "--recalcchecksum",
            str(game_exe.absolute()),
        ]
        print(Fore.CYAN + f"Steamless: running on {game_exe.name}..." + Style.RESET_ALL)
        # Don't pop a console window for the steamless run on Windows.
        # The cmd window flickering on top of SteaMidra was confusing
        # users into thinking the app froze, and capturing stdout means
        # we already forward the steamless output through the live log.
        _popen_extra: dict = {}
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            _popen_extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            output = subprocess.run(
                cmd,
                encoding="utf-8",
                capture_output=True,
                cwd=str(steamless_dir),
                timeout=120,
                env=run_env,
                **_popen_extra,
            )
        except subprocess.TimeoutExpired:
            msg = f"Steamless timed out on {game_exe.name}"
            print(Fore.RED + msg + Style.RESET_ALL)
            return False, msg

        stdout_text = (output.stdout or "").strip()
        stderr_text = (output.stderr or "").strip()
        unpacked = game_exe.parent / (game_exe.name + ".unpacked.exe")

        if unpacked.exists() and "Successfully unpacked file!" in stdout_text:
            backup = game_exe.with_suffix(game_exe.suffix + ".steamlocked.bak")
            backup_ok = True
            try:
                if backup.exists():
                    backup.unlink()
                game_exe.rename(backup)
            except OSError as e:
                # File was held by the launcher / a running game process.
                # Don't try the unpacked-rename below, that would leave
                # both .exe AND .exe.unpacked.exe on disk and confuse the
                # user. Surface what happened so they can close the game
                # / launcher and click Remove DRM again.
                backup_ok = False
                msg = (
                    f"Steamless: unpacked {game_exe.name} but couldn't back "
                    f"up the original ({e}). Close the game / launcher "
                    "process, delete the .unpacked.exe leftover, and run "
                    "Remove DRM again."
                )
                print(Fore.YELLOW + msg + Style.RESET_ALL)
                return False, msg
            try:
                unpacked.rename(game_exe)
            except OSError as e:
                # Backup succeeded but unpacked-to-original rename failed.
                # Restore the backup so the user isn't left with the game
                # missing its main .exe entirely.
                msg = (
                    f"Steamless: backed up {game_exe.name} but couldn't "
                    f"replace it with the unpacked version ({e}). Restoring "
                    "the original."
                )
                print(Fore.YELLOW + msg + Style.RESET_ALL)
                try:
                    backup.rename(game_exe)
                except OSError:
                    pass
                return False, msg
            msg = (
                f"Steamless: unpacked {game_exe.name}. "
                f"Original saved as {backup.name}."
            )
            print(Fore.GREEN + msg + Style.RESET_ALL)
            return True, msg

        # Surface what Steamless actually said, then map known failure
        # signatures to user-friendly messages.
        if stdout_text:
            print(stdout_text)
        if stderr_text:
            print(Fore.YELLOW + stderr_text + Style.RESET_ALL)

        combined = stdout_text + "\n" + stderr_text
        if "Invalid input file given" in combined:
            msg = (
                f"Steamless rejected '{game_exe.name}' as an invalid input file. "
                "This usually means the exe is not a Steam-DRM-wrapped binary, "
                "or it has been packed by something other than SteamStub. "
                "Pick the game's main launcher exe and try again."
            )
        elif "All unpackers failed" in combined:
            msg = (
                f"Steamless found Steam-DRM markers in '{game_exe.name}' but "
                "none of the bundled unpackers can handle this wrapper variant. "
                "This typically means the game uses a newer SteamStub release "
                "that atom0s hasn't published a plugin for yet. "
                "Last-resort options: try SteamAutoCrack from the Library tab, "
                "or wait for an updated Steamless build."
            )
        else:
            msg = (
                f"Steamless did not produce {unpacked.name}. "
                f"The exe is either not Steam-DRM-wrapped, or it uses a "
                f"wrapper variant Steamless cannot unpack yet."
            )
        print(Fore.YELLOW + msg + Style.RESET_ALL)
        return False, msg

    def _prompt_manual_exe(self, app_info):
        # Open a single file dialog rooted at the game's install folder.
        # The classic Library button already does this directly via QFileDialog;
        # this fallback path covers cases where Steam App Info has no launcher
        # info (e.g. games not in your library).
        try:
            game_exe = prompt_file(
                "Pick the game .exe:",
                start_dir=str(app_info.path),
            )
        except TypeError:
            # Older prompt_file signatures had no start_dir kwarg.
            game_exe = prompt_file("Pick the game .exe:")
        return game_exe

    def _get_windows_execs(self, info, app_id):
        launches = enter_path(info, "apps", app_id, "config", "launch")
        return [
            launch["executable"]
            for launch in launches.values()
            if enter_path(launch, "config", "oslist") == "windows"
        ]

    def select_executable(self, app_info):
        info = get_product_info(self.provider, [int(app_info.app_id)])
        windows_exes = self._get_windows_execs(info, int(app_info.app_id))
        if not windows_exes:
            return self._prompt_manual_exe(app_info)
        if len(windows_exes) == 1:
            return app_info.path / windows_exes[0]
        chosen = prompt_select("Choose the exe:", windows_exes)
        return app_info.path / chosen

    def download_workshop_manifest(self, app_id):
        strats = [StandardUgcIdStrategy()]
        ugc_resolver = UgcIDResolver(strats)
        regex = re.compile(
            r"(?<=steamcommunity.com\/sharedfiles\/filedetails\/\?id=)\d+|^\d+$"
        )
        def validate(x):
            return bool(regex.search(x))
        def filter_id(x):
            match = regex.search(x)
            assert match is not None
            return int(match.group())
        workshop_id = prompt_text(
            "Paste workshop item or collection URL, or item ID:",
            validator=validate,
            filter=filter_id,
        )
        api_key = get_setting(Settings.STEAM_WEB_API_KEY) or STEAM_WEB_API_KEY
        children = get_collection_children(workshop_id, api_key or "")
        if children:
            print(f"Collection with {len(children)} items. Downloading...")
            downloader = ManifestDownloader(self.provider, self.steam_root)
            ok = 0
            for i, child_id in enumerate(children, 1):
                try:
                    ctx = WorkshopItemContext(self.provider.client, child_id)
                    content, method, details = ugc_resolver.resolve_with_details(ctx)
                    if isinstance(content, DirectDownloadUrl):
                        print(
                            f"  [{i}/{len(children)}] Item {child_id}: legacy (direct URL) - skip"
                        )
                        continue
                    downloader.download_workshop_item(app_id, str(content.ugc_id))
                    if details and hasattr(details, "time_updated"):
                        tracker_add(app_id, child_id, details.time_updated)
                    ok += 1
                    print(f"  [{i}/{len(children)}] Item {child_id}: OK")
                except Exception as e:
                    print(f"  [{i}/{len(children)}] Item {child_id}: {e}")
            print(
                Fore.GREEN
                + f"Collection download complete. {ok}/{len(children)} items."
                + Style.RESET_ALL
            )
        else:
            ctx = WorkshopItemContext(self.provider.client, workshop_id)
            content, method, details = ugc_resolver.resolve_with_details(ctx)
            if isinstance(content, DirectDownloadUrl):
                print(
                    "This is a legacy workshop item. "
                    "It can be directly downloaded through"
                    " the following URL. It's just a ZIP file:\n"
                    f"{Fore.BLUE + content.url + Style.RESET_ALL}"
                )
            else:
                print(f"Found UGC ID via {method} method: {content.ugc_id}")
                downloader = ManifestDownloader(self.provider, self.steam_root)
                downloader.download_workshop_item(app_id, str(content.ugc_id))
                if details and hasattr(details, "time_updated"):
                    tracker_add(app_id, workshop_id, details.time_updated)
                print(
                    Fore.GREEN
                    + "Workshop item manifest downloaded! Try downloading it now."
                    + Style.RESET_ALL
                )

    def check_mod_updates(self, app_id):
        items = [(a, w, t) for a, w, t in tracker_get_all() if a == app_id]
        if not items:
            print("No tracked workshop items for this game. Download items first to track them.")
            return
        print(f"Checking {len(items)} tracked workshop item(s) for updates...")
        downloader = ManifestDownloader(self.provider, self.steam_root)
        ugc_resolver = UgcIDResolver([StandardUgcIdStrategy()])
        updated = 0
        for _app_id, workshop_id, stored_time in items:
            ctx = WorkshopItemContext(self.provider.client, workshop_id)
            current = get_workshop_time_updated(ctx)
            if current is None:
                print(f"  Item {workshop_id}: could not fetch (skip)")
                continue
            if current <= stored_time:
                print(f"  Item {workshop_id}: up to date")
                continue
            try:
                content, _method, details = ugc_resolver.resolve_with_details(ctx)
                if isinstance(content, DirectDownloadUrl):
                    print(f"  Item {workshop_id}: legacy item (skip)")
                    continue
                downloader.download_workshop_item(app_id, str(content.ugc_id))
                if details and hasattr(details, "time_updated"):
                    tracker_update_time(app_id, workshop_id, details.time_updated)
                updated += 1
                print(f"  Item {workshop_id}: updated")
            except Exception as e:
                print(f"  Item {workshop_id}: {e}")
        print(
            Fore.GREEN
            + f"Done. {updated} item(s) updated."
            + Style.RESET_ALL
        )

    def _resolve_game_name(self, app_info):
        """Helper: resolve game name from ACF or Steam Store fallback."""
        game_name = "Unknown"
        # Outside-Steam mode uses app_id "0" — skip ACF/Store lookups and use folder name
        if not app_info.app_id or str(app_info.app_id).strip() == "0":
            return app_info.path.name or "Unknown"
        steamapps_for_game = app_info.path.parent.parent
        acf_path = steamapps_for_game / f"appmanifest_{app_info.app_id}.acf"
        if acf_path.exists():
            try:
                acf_data = vdf_load(acf_path)
                game_name = acf_data.get("AppState", {}).get("name", "Unknown")
            except Exception as e:
                logger.warning(f"Failed to read game name from ACF: {e}")
        if not game_name or game_name == "Unknown":
            try:
                details = get_app_details_from_store(int(app_info.app_id))
                if details and details.get("name"):
                    game_name = details["name"].strip()
            except Exception as e:
                logger.debug("Steam Store API fallback for game name: %s", e)
        return game_name

    def apply_multiplayer_fix(self, app_info):
        print("\n" + Fore.CYAN + "Multiplayer Fix (online-fix.me)" + Style.RESET_ALL)
        print("This will download and apply a multiplayer fix for the selected game.")
        print("The fix will be extracted directly to the game folder.\n")
        game_name = self._resolve_game_name(app_info)
        print(f"Game: {Fore.YELLOW}{game_name}{Style.RESET_ALL}")
        print(f"Folder: {Fore.YELLOW}{app_info.path}{Style.RESET_ALL}\n")
        if not prompt_confirm("Continue with multiplayer fix via online-fix.me?"):
            return
        success = apply_online_fix(game_name, app_info.path)
        if success:
            print("\n" + Fore.GREEN + "Multiplayer fix applied successfully!" + Style.RESET_ALL)
            print("You can now launch the game and try multiplayer features.")
        else:
            print("\n" + Fore.RED + "Failed to apply multiplayer fix." + Style.RESET_ALL)
            print("Check the error messages above for details.")

    def apply_crack_fix(self, app_info):
        print("\n" + Fore.CYAN + "Fixes & Bypasses" + Style.RESET_ALL)
        print("This will search and apply a game fix or bypass.")
        print("The fix will be extracted directly to the game folder.\n")
        game_name = self._resolve_game_name(app_info)
        print(f"Game: {Fore.YELLOW}{game_name}{Style.RESET_ALL}")
        print(f"Folder: {Fore.YELLOW}{app_info.path}{Style.RESET_ALL}\n")
        from sff.crack_fix import apply_crack_fix as _apply_crack
        success = _apply_crack(game_name, app_info.path)
        if success:
            print("\n" + Fore.GREEN + "Fix applied successfully!" + Style.RESET_ALL)
            print("You can now launch the game.")
        else:
            print("\n" + Fore.RED + "Failed to apply fix." + Style.RESET_ALL)
            print("Check the error messages above for details.")

    def apply_hv_fix(self, app_info):
        # 6.2.4 hotfix: HV Auto temporarily disabled. HVAuto's downloads
        # are hosted on buzzheavier, which is currently serving malware
        # ad pop-ups and fake download buttons. Bail before any prompt
        # or temp-dir activity so users can't accidentally hit the bad
        # ads. Re-enable once HVAuto switches to a safer host.
        print("\n" + Fore.CYAN + "HyperVisor Bypasses (HVAuto)" + Style.RESET_ALL)
        print(Fore.YELLOW
              + "HV Auto is temporarily disabled.\n"
              + "  HVAuto's downloads are hosted on buzzheavier, which "
              + "is currently serving malware ads and fake download "
              + "buttons. We've blocked the integration in SteaMidra "
              + "until the fixes move to a safer host (pixeldrain, "
              + "mediafire, or similar). Sorry for the inconvenience."
              + Style.RESET_ALL)
        return

    def _apply_hv_fix_real(self, app_info):
        import time
        if not get_setting(Settings.HV_FIRST_USE_WARNED):
            warning = (
                "=" * 60 + "\n"
                " HYPERVISOR CRACKS — READ BEFORE CONTINUING\n"
                "=" * 60 + "\n\n"
                "HyperVisor (HV) cracks bypass Denuvo by running a custom driver\n"
                "that sits below Windows and intercepts CPU-level checks.\n\n"
                "TO USE THEM YOU MUST:\n"
                "  1. Disable Memory Integrity (HVCI)\n"
                "  2. Disable Virtualization-based Security (VBS)\n"
                "  3. Disable Credential Guard\n"
                "  4. Disable Driver Signature Enforcement for one boot cycle\n"
                "  5. Run VBS.cmd (bundled in the game folder after install)\n"
                "  6. Reboot when prompted, press F7 / 7 at Startup Settings\n\n"
                "SECURITY IMPLICATIONS:\n"
                "  - These changes lower Windows kernel protections.\n"
                "  - Only do this on a personal PC you control.\n"
                "  - Revert changes after each play session using VBS.cmd > Revert Changes.\n"
                "  - Scan your system with an AV before running the crack.\n"
                "  - Most kernel anti-cheats (FACEIT, Vanguard) will not work while DSE is off.\n\n"
                "The included VBS.cmd handles all security setting changes\n"
                "and includes a Revert Changes option. Run it as Administrator.\n\n"
                "For full details, read the cs.rin.ru guide:\n"
                "  https://cs.rin.ru/forum/viewtopic.php?f=10&t=156407\n"
            )
            print(Fore.RED + warning + Style.RESET_ALL)
            print(Fore.YELLOW + "This dialog closes in 20 seconds..." + Style.RESET_ALL)
            for i in range(20, 0, -1):
                print(f"\r  {i}s remaining ", end="", flush=True)
                time.sleep(1)
            print()
            set_setting(Settings.HV_FIRST_USE_WARNED, True)

        game_name = self._resolve_game_name(app_info)
        print("\n" + Fore.CYAN + "HyperVisor Bypasses (HVAuto)" + Style.RESET_ALL)
        print(f"Game:   {Fore.YELLOW}{game_name}{Style.RESET_ALL}")
        print(f"Folder: {Fore.YELLOW}{app_info.path}{Style.RESET_ALL}\n")

        build_id = None
        if app_info.app_id and str(app_info.app_id).strip() != "0":
            steamapps_dir = app_info.path.parent.parent
            acf_path = steamapps_dir / f"appmanifest_{app_info.app_id}.acf"
            if acf_path.exists():
                try:
                    acf_data = vdf_load(acf_path)
                    build_id = acf_data.get("AppState", {}).get("buildid")
                except Exception:
                    pass

        from sff.hv_fix import apply_hv_fix as _apply_hv
        success = _apply_hv(game_name, app_info.path, build_id=build_id)
        if success:
            print("\n" + Fore.GREEN + "HV fix applied. Run VBS.cmd as Administrator before launching the game." + Style.RESET_ALL)
        else:
            print("\n" + Fore.RED + "HV fix not applied. Check the output above." + Style.RESET_ALL)

    def manage_dlc_unlockers(self, app_info):
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
        print(f"\n{Fore.CYAN}=== DLC Unlockers (CreamInstaller) ==={Style.RESET_ALL}")
        print(f"Game: {app_info.path.name}  |  App ID: {app_info.app_id}")
        print(f"Mode: {Fore.YELLOW}{'SmokeAPI' if use_smokeapi else 'CreamAPI'}{Style.RESET_ALL}\n")
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
        menu_options = ["Install DLC Unlockers", "Uninstall DLC Unlockers", "Configure (SmokeAPI/CreamAPI)", "Go back"]
        choice = prompt_select("Select:", menu_options)
        if choice == "Go back":
            return
        if choice == "Configure (SmokeAPI/CreamAPI)":
            use_smokeapi = prompt_confirm(
                "Use SmokeAPI? (No = CreamAPI)",
                true_msg="SmokeAPI",
                false_msg="CreamAPI",
                default=use_smokeapi
            )
            set_setting(Settings.USE_SMOKEAPI, use_smokeapi)
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
        print(f"\n{Fore.CYAN}Installing DLC unlockers...{Style.RESET_ALL}")
        steam_unlocker = UnlockerType.SMOKEAPI if use_smokeapi else UnlockerType.CREAMAPI
        if platform == Platform.STEAM:
            to_install = [steam_unlocker]
            print(f"Mode: {steam_unlocker.value} (direct)")
        else:
            to_install = [u.unlocker_type for u in compatible_unlockers]
        cache_dir_val = get_setting(Settings.DLC_UNLOCKER_CACHE_DIR)
        cache_dir = Path(cache_dir_val) if cache_dir_val and str(cache_dir_val) != "(unset)" else root_folder(outside_internal=True) / "dlc_unlocker_cache"
        downloader = GitHubReleaseDownloader(cache_dir)
        print(f"\n{Fore.CYAN}Downloading...{Style.RESET_ALL}")
        unlocker_dirs = {}
        for utype in to_install:
            if utype == UnlockerType.SMOKEAPI and not use_smokeapi:
                continue
            if utype == UnlockerType.CREAMAPI and use_smokeapi:
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
            needed = [UnlockerType.SMOKEAPI if use_smokeapi else UnlockerType.CREAMAPI]
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
    ):
        app_info = override_game if override_game is not None else self.get_game()
        if app_info is None:
            return MainReturnCode.LOOP_NO_PROMPT
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
            return self.apply_steamless(app_info)
        elif choice == MainMenu.DL_USER_GAME_STATS:
            self.run_gen_emu(app_info.app_id, GenEmuMode.USER_GAME_STATS)
        elif choice == MainMenu.DLC_CHECK:
            self.injection_manager.dlc_check(self.provider, int(app_info.app_id))
        elif choice == MainMenu.DL_WORKSHOP_ITEM:
            self.download_workshop_manifest(app_info.app_id)
        elif choice == MainMenu.CHECK_MOD_UPDATES:
            self.check_mod_updates(app_info.app_id)
        elif choice == MainMenu.MULTIPLAYER_FIX:
            self.apply_multiplayer_fix(app_info)
        elif choice == MainMenu.CRACK_FIX:
            self.apply_crack_fix(app_info)
        elif choice == MainMenu.HV_FIX:
            self.apply_hv_fix(app_info)
        elif choice == MainMenu.MANAGE_DLC_UNLOCKERS:
            self.manage_dlc_unlockers(app_info)
        return MainReturnCode.LOOP
