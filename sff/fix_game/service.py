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
Fix Game orchestrator — the main pipeline that makes games playable.

Pipeline steps:
0. DRM Detection (check Steam Store API for Denuvo, etc)
1. Goldberg Auto-Update (download latest gbe_fork if needed)
2. Config Generation (steam_settings/: achievements, DLC, cloud saves, etc)
3. SteamStub Unpacking (remove SteamStub DRM from .exe files)
4. Goldberg Application (replace steam_api DLLs or deploy ColdClient)
5. Launch.bat Generation (create launch scripts from PICS data)

Mirrors Solus FixGameService.cs (588 lines).
"""

import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path
from enum import Enum

import httpx

from sff.fix_game.cache import FixGameCache
from sff.fix_game.goldberg_updater import GoldbergUpdater
from sff.fix_game.config_generator import GoldbergConfigGenerator, _get_gbe_saves_root
from sff.fix_game.steamstub_unpacker import SteamStubUnpacker
from sff.fix_game.goldberg_applier import GoldbergApplier

logger = logging.getLogger(__name__)

STEAM_STORE_API = "https://store.steampowered.com/api"


class EmuMode(Enum):
    """which Goldberg mode to use"""
    REGULAR = "regular"
    COLDCLIENT_LOADER = "coldclient_loader"   # kept for backward compatibility
    COLDCLIENT_SIMPLE = "coldclient_simple"   # Python-based config, no credentials
    COLDCLIENT_ADVANCED = "coldclient_advanced"  # GSE Fork tool, anon or login
    COLDLOADER_DLL = "coldloader_dll"


class DrmCheckResult(Enum):
    """result of DRM detection"""
    CLEAN = "clean"                    # no DRM → regular mode OK
    DRM_DETECTED = "drm_detected"      # some DRM → force ColdClient
    DENUVO = "denuvo"                  # Denuvo → ABORT
    THIRD_PARTY = "third_party"        # needs 3rd party account → ABORT
    ERROR = "error"                    # couldn't check


class FixGameService:
    """
    Orchestrates the full Fix Game pipeline.

    Usage:
        service = FixGameService()
        success = service.fix_game(
            app_id=12345,
            game_dir="C:/Games/MyGame",
            steam_web_api_key="...",
        )
    """

    def __init__(self):
        self.cache = FixGameCache()
        self.updater = GoldbergUpdater(self.cache.goldberg_dir)
        self.unpacker = SteamStubUnpacker()
        self.applier = GoldbergApplier(self.cache.goldberg_dir)

    def fix_game(
        self,
        app_id: int,
        game_dir: str,
        steam_web_api_key = None,
        language = "english",
        steam_id = "76561198001737783",
        player_name = "Player",
        emu_mode = "regular",
        skip_drm_check = False,
        skip_steamstub = False,
        steamless_experimental: bool = True,
        skip_goldberg_update = False,
        create_launch_bat = True,
        log_func=None,
        avatar_path = None,
        simple_settings = False,
        gse_auth_mode = "anonymous",
        gse_username = "",
        gse_password = "",
        linux_native: bool = False,
    ):
        """
        Run the full Fix Game pipeline.
        Args:
            app_id: Steam app ID
            game_dir: path to the game directory
            steam_web_api_key: optional Steam Web API key for achievements
            language: game language
            steam_id: Steam64 ID
            player_name: display name
            emu_mode: "regular", "coldclient_simple", "coldclient_advanced", or "coldloader_dll"
            skip_drm_check: skip DRM detection step
            skip_steamstub: skip SteamStub unpacking
            log_func: callback for status updates
            avatar_path: optional path to avatar image (.png/.jpg/.jpeg)
            simple_settings: if True, generate minimal configs without API calls
            linux_native: True = native Linux game (use libsteam_api.so); False = Proton/Wine (use .dll)
        Returns True on success.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        log(f"=== Fix Game Pipeline: App {app_id} ===")
        log(f"Game directory: {game_dir}")
        log(f"Mode: {emu_mode}")
        if sys.platform != "win32":
            log(f"Platform: Linux ({'native' if linux_native else 'Proton/Wine'})")
        # --- Step 0: DRM Detection ---
        if not skip_drm_check:
            log("\n--- Step 0: DRM Detection ---")
            drm_result = self.check_drm(app_id, log)
            if drm_result == DrmCheckResult.DENUVO:
                log("ABORT: Denuvo DRM detected — cannot be bypassed by Goldberg")
                return False
            if drm_result == DrmCheckResult.THIRD_PARTY:
                log("ABORT: Game requires third-party account — may not work with Goldberg")
                return False
            if drm_result == DrmCheckResult.DRM_DETECTED:
                log("DRM detected — forcing ColdClient mode")
                if emu_mode == "regular":
                    emu_mode = "coldclient_simple"
        # --- Step 1: Goldberg Auto-Update ---
        log("\n--- Step 1: Goldberg Update ---")
        if not skip_goldberg_update:
            if not self.updater.ensure_goldberg(log_func=log, linux_native=linux_native):
                log("WARNING: Could not update Goldberg — using cached/bundled version")
                if not self.cache.has_goldberg_dlls(linux_native=linux_native):
                    log("ABORT: No Goldberg files available")
                    return False
        else:
            log("Goldberg auto-update skipped")
            if not self.cache.has_goldberg_dlls(linux_native=linux_native):
                log("No cached files found — copying from bundled third_party...")
                if not self.updater._copy_bundled_fallback(log, linux_native=linux_native):
                    log("ABORT: No Goldberg files available (cache empty and bundled fallback failed)")
                    return False
        # --- Step 2: Config Generation ---
        log("\n--- Step 2: Config Generation ---")
        cached_info = self.cache.load_app_info(app_id)
        generator = GoldbergConfigGenerator(steam_web_api_key)
        if emu_mode == EmuMode.COLDCLIENT_ADVANCED.value:
            gse_ok = self._run_gse_config(
                app_id=app_id,
                game_dir=game_dir,
                auth_mode=gse_auth_mode,
                username=gse_username,
                password=gse_password,
                log=log,
            )
            if not gse_ok:
                log("⚠ GSE tool unavailable — falling back to Python config generator")
                generator.generate(
                    app_id=app_id,
                    target_dir=game_dir,
                    language=language,
                    steam_id=steam_id,
                    player_name=player_name,
                    dlc_list=cached_info.dlc_list if cached_info else None,
                    cloud_save_paths=cached_info.cloud_save_paths if cached_info else None,
                    log_func=log,
                    avatar_path=avatar_path,
                    simple_mode=False,
                )
            # always write global GBE identity settings regardless of which path was taken
            global_dir = _get_gbe_saves_root() / "settings"
            generator._write_global_settings(
                global_dir=global_dir,
                player_name=player_name,
                steam_id=steam_id,
                language=language,
                avatar_path=avatar_path,
                log=log,
            )
        else:
            generator.generate(
                app_id=app_id,
                target_dir=game_dir,
                language=language,
                steam_id=steam_id,
                player_name=player_name,
                dlc_list=cached_info.dlc_list if cached_info else None,
                cloud_save_paths=cached_info.cloud_save_paths if cached_info else None,
                log_func=log,
                avatar_path=avatar_path,
                simple_mode=simple_settings,
            )
        # create and report the GSE Saves folder so users know where saves go
        gse_saves = _get_gbe_saves_root() / str(app_id)
        gse_saves.mkdir(parents=True, exist_ok=True)
        log(f"Save data: {gse_saves}")
        # --- Step 3: SteamStub Unpacking ---
        if not skip_steamstub:
            log("\n--- Step 3: SteamStub Unpacking ---")
            if self.unpacker.is_available():
                count = self.unpacker.unpack_directory(game_dir, log_func=log, use_experimental=steamless_experimental)
                if count > 0:
                    log(f"Unpacked {count} SteamStub-protected file(s)")
                else:
                    log("No SteamStub protection detected")
            else:
                log("Steamless not available — skipping SteamStub check")
        # --- Step 4: Goldberg Application ---
        log("\n--- Step 4: Goldberg Application ---")
        mode = EmuMode(emu_mode)
        if sys.platform != "win32" and linux_native:
            success, msg = self.applier.apply_linux(game_dir, log_func=log)
        elif mode == EmuMode.REGULAR:
            success, msg = self.applier.apply(game_dir, log_func=log)
        elif mode in (EmuMode.COLDCLIENT_LOADER, EmuMode.COLDCLIENT_SIMPLE, EmuMode.COLDCLIENT_ADVANCED):
            if sys.platform != "win32":
                log("ColdClient mode is Windows-only — falling back to regular mode on Linux")
                success, msg = self.applier.apply(game_dir, log_func=log)
            else:
                success, msg = self.applier.apply_coldclient_loader(game_dir, app_id, log_func=log)
        elif mode == EmuMode.COLDLOADER_DLL:
            if sys.platform != "win32":
                log("ColdLoader DLL mode is Windows-only — falling back to regular mode on Linux")
                success, msg = self.applier.apply(game_dir, log_func=log)
            else:
                success, msg = self.applier.apply_coldloader_dll(game_dir, app_id, log_func=log)
        else:
            success, msg = False, f"Unknown mode: {emu_mode}"
        log(msg)
        if not success:
            return False
        # --- Step 5: Launch.bat Generation ---
        if create_launch_bat:
            log("\n--- Step 5: Launch Script ---")
            self._generate_launch_script(app_id, game_dir, emu_mode, log, linux_native=linux_native)
        else:
            log("\n--- Step 5: Launch Script (skipped) ---")
        log("\n=== Fix Game Complete ===")
        return True

    def restore_game(self, game_dir, log_func=None):
        """
        Undo all Fix Game changes — restore originals, delete configs.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        log("=== Restoring Game ===")
        # restore SteamStub backups
        self.unpacker.restore_directory(game_dir, log_func=log)
        # restore Goldberg changes
        success, msg = self.applier.restore(game_dir, log_func=log)
        # delete launch scripts
        game_path = Path(game_dir)
        for bat in game_path.glob("Launch*.bat"):
            bat.unlink()
            log(f"Deleted {bat.name}")
        log("=== Restore Complete ===")
        return success, msg

    def check_drm(self, app_id, log_func=None):
        """
        Check Steam Store API for DRM information.
        Checks the 'drm_notice' and 'ext_user_account_notice' fields
        from store.steampowered.com/api/appdetails.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{STEAM_STORE_API}/appdetails",
                    params={"appids": str(app_id)},
                )
                resp.raise_for_status()
                data = resp.json()
            app_data = data.get(str(app_id), {})
            if not app_data.get("success"):
                log("Could not fetch store data")
                return DrmCheckResult.ERROR
            details = app_data.get("data", {})
            # check Denuvo
            drm_notice = details.get("drm_notice", "")
            if "denuvo" in drm_notice.lower():
                log(f"DRM: Denuvo detected ({drm_notice})")
                return DrmCheckResult.DENUVO
            # check third-party account requirement
            ext_account = details.get("ext_user_account_notice", "")
            if ext_account:
                log(f"Third-party account required: {ext_account}")
                return DrmCheckResult.THIRD_PARTY
            # check for other DRM
            if drm_notice:
                log(f"DRM notice: {drm_notice}")
                return DrmCheckResult.DRM_DETECTED
            log("No DRM detected")
            return DrmCheckResult.CLEAN
        except Exception as e:
            logger.warning("DRM check failed: %s", e)
            log(f"DRM check failed: {e}")
            return DrmCheckResult.ERROR

    def _generate_launch_script(self, app_id, game_dir, emu_mode, log, linux_native: bool = False):
        """generate Launch.bat (Windows) or launch.sh / launch_wine.sh (Linux) from PICS data or main exe"""
        game_path = Path(game_dir)
        is_linux = sys.platform != "win32"
        is_wine_mode = is_linux and not linux_native
        # try to get launch configs from PICS cache
        pics_data = self.cache.load_pics_data(app_id)
        if pics_data:
            launch_configs = self._extract_launch_configs(pics_data)
            if launch_configs:
                for i, config in enumerate(launch_configs):
                    exe = config.get("executable", "")
                    args = config.get("arguments", "")
                    workdir = config.get("workingdir", "")
                    desc = config.get("description", f"Config {i}")
                    if is_linux:
                        sh_suffix = "_wine" if is_wine_mode else ""
                        sh_name = f"launch{sh_suffix}{'_' + desc.replace(' ', '_') if i > 0 else ''}.sh"
                        exec_cmd = f'wine "{exe}" {args}' if is_wine_mode else f'"{exe}" {args}'
                        sh_content = f'#!/bin/sh\ncd "$(dirname "$0"){("/" + workdir) if workdir else ""}"\nexec {exec_cmd}\n'
                        script_path = game_path / sh_name
                        script_path.write_text(sh_content, encoding="utf-8")
                        script_path.chmod(0o755)
                        log(f"✓ Created {sh_name} ({exe})")
                    else:
                        bat_name = f"Launch{'_' + desc.replace(' ', '_') if i > 0 else ''}.bat"
                        bat_content = f'@echo off\ncd /d "%~dp0{workdir}"\nstart "" "{exe}" {args}\n'
                        (game_path / bat_name).write_text(bat_content, encoding="utf-8")
                        log(f"✓ Created {bat_name} ({exe})")
                if is_wine_mode:
                    self._write_lutris_setup(game_path, launch_configs[0].get("executable", "game.exe"), log)
                return
        # fallback: ColdClient loader (Windows native or Linux Proton/Wine)
        is_coldclient = emu_mode in ("coldclient_loader", "coldclient_simple", "coldclient_advanced")
        if is_coldclient:
            for loader in ["steamclient_loader_x64.exe", "steamclient_loader_x32.exe"]:
                if (game_path / loader).exists():
                    if is_wine_mode:
                        sh_content = f'#!/bin/sh\ncd "$(dirname \"$0\")"\nexec wine "{loader}"\n'
                        script_path = game_path / "launch_wine.sh"
                        script_path.write_text(sh_content, encoding="utf-8")
                        script_path.chmod(0o755)
                        log(f"\u2713 Created launch_wine.sh (wine {loader})")
                        self._write_lutris_setup(game_path, loader, log)
                    elif not is_linux:
                        bat_content = f'@echo off\ncd /d "%~dp0"\nstart "" "{loader}"\n'
                        (game_path / "Launch.bat").write_text(bat_content, encoding="utf-8")
                        log(f"\u2713 Created Launch.bat (via {loader})")
                    return
        # fallback: find largest executable
        if is_wine_mode:
            # Proton/Wine: find main .exe and wrap with wine
            main_exe = self.applier.find_main_exe(game_dir)
            if main_exe:
                exe_name = Path(main_exe).name
                sh_content = f'#!/bin/sh\ncd "$(dirname \"$0\")"\nexec wine "{exe_name}"\n'
                script_path = game_path / "launch_wine.sh"
                script_path.write_text(sh_content, encoding="utf-8")
                script_path.chmod(0o755)
                log(f"\u2713 Created launch_wine.sh (wine {exe_name})")
                self._write_lutris_setup(game_path, exe_name, log)
        elif is_linux:
            main_bin = self.applier.find_main_binary_linux(game_dir)
            if main_bin:
                bin_rel = os.path.relpath(main_bin, game_dir)
                sh_content = f'#!/bin/sh\ncd "$(dirname \"$0\")"\nexec "{bin_rel}"\n'
                script_path = game_path / "launch.sh"
                script_path.write_text(sh_content, encoding="utf-8")
                script_path.chmod(0o755)
                log(f"\u2713 Created launch.sh ({bin_rel})")
        else:
            main_exe = self.applier.find_main_exe(game_dir)
            if main_exe:
                exe_rel = os.path.relpath(main_exe, game_dir)
                bat_content = f'@echo off\ncd /d "%~dp0"\nstart "" "{exe_rel}"\n'
                (game_path / "Launch.bat").write_text(bat_content, encoding="utf-8")
                log(f"\u2713 Created Launch.bat ({exe_rel})")

    @staticmethod
    def _write_lutris_setup(game_path: Path, exe_name: str, log):
        """write LUTRIS_SETUP.txt with Lutris + Wine setup instructions for Proton/Wine mode"""
        content = f"""To launch this game on Linux with Lutris:

1. Open Lutris, click "+" (top-left), choose Wine as runner.
2. Game Options:
   - Executable: {exe_name}
   - Wine prefix: Create a folder called 'prefix' in this game directory and select it.
3. Runner Options:
   - Wine version: select the latest 'lutris-*' Wine build.
   - Optionally enable fsync / esync if your kernel supports it.
4. Save and launch.

Note: On first launch, saves will be in:
  prefix/drive_c/users/<name>/AppData/Roaming/GSE Saves/

For LAN multiplayer, use ZeroTier or similar VPN.
Default Goldberg port: 47584 — make sure it is open in your firewall.
"""
        txt_path = game_path / "LUTRIS_SETUP.txt"
        txt_path.write_text(content, encoding="utf-8")
        log("\u2713 Created LUTRIS_SETUP.txt with Lutris/Wine instructions")

    @staticmethod
    def _find_gse_exe():
        """
        Locate generate_emu_config.exe in priority order (Windows only).
        1. sys._MEIPASS (frozen single-file EXE — bundled data lives here,
           NOT in Path(sys.executable).parent which is the EXE's own folder)
        2. Next to the EXE / project root (dev mode or one-folder distribution)
        3. %APPDATA%/SteaMidra/gse_tool/ (previously staged persistent copy)
        Returns None on Linux (binary is Windows-only).
        """
        if sys.platform != "win32":
            return None
        rel = (Path("third_party") / "gbe_fork_tools"
               / "generate_emu_config" / "generate_emu_config.exe")
        # 1. Frozen single-file EXE: bundled files are in sys._MEIPASS
        if getattr(sys, "frozen", False):
            meipass = Path(getattr(sys, "_MEIPASS", ""))
            p = meipass / rel
            if p.exists():
                return p
        # 2. Dev mode or one-folder distribution: next to the project root
        try:
            from sff.utils import root_folder
            p = root_folder() / rel
            if p.exists():
                return p
        except Exception:
            pass
        # 3. Persistent APPDATA staged copy (written on first successful run)
        appdata = Path(os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"))
        p = appdata / "SteaMidra" / "gse_tool" / "generate_emu_config.exe"
        if p.exists():
            return p
        return None

    def _run_gse_config(
        self,
        app_id: int,
        game_dir: str,
        auth_mode: str,
        username: str,
        password: str,
        log,
    ):
        """
        Run generate_emu_config.exe (GSE Fork) to build steam_settings.
        Locates the tool via _find_gse_exe() (checks sys._MEIPASS first so the
        bundled version inside the frozen EXE is found correctly).
        Copies the tool to %APPDATA%/SteaMidra/gse_tool/ before running so it
        has a writable persistent directory for output and its own state files.
        auth_mode: "anonymous" or "login" (username + password via env vars).
        Runs with CREATE_NO_WINDOW + stdin=DEVNULL so no console ever appears.
        Returns True if config was generated successfully.
        """
        config_exe = self._find_gse_exe()
        if not config_exe:
            log("generate_emu_config.exe not found in any search location")
            log("  Searched: sys._MEIPASS, project root, %APPDATA%/SteaMidra/gse_tool/")
            return False
        log(f"GSE tool found: {config_exe}")
        # Copy the entire tool folder to a persistent writable APPDATA location.
        # This ensures the tool can write output/ and keep its own state files,
        # and avoids issues with sys._MEIPASS being a read-constrained temp dir.
        appdata = Path(os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"))
        run_dir = appdata / "SteaMidra" / "gse_tool"
        run_exe = run_dir / "generate_emu_config.exe"
        try:
            src_dir = config_exe.parent
            run_dir.mkdir(parents=True, exist_ok=True)
            # copy EXE
            shutil.copy2(config_exe, run_exe)
            # copy _internal/ folder (PyInstaller dependencies for the tool)
            src_internal = src_dir / "_internal"
            if src_internal.is_dir():
                dst_internal = run_dir / "_internal"
                shutil.copytree(src_internal, dst_internal, dirs_exist_ok=True)
            # copy any support files (jpg, txt examples, etc.) — skip output/
            for f in src_dir.iterdir():
                if f.is_file() and f.name != "generate_emu_config.exe":
                    shutil.copy2(f, run_dir / f.name)
            log(f"✓ GSE tool staged to {run_dir}")
        except Exception as e:
            log(f"Warning: could not stage GSE tool to APPDATA ({e}) — running in-place")
            run_dir = config_exe.parent
            run_exe = config_exe
        env = os.environ.copy()
        if auth_mode == "login" and username and password:
            env["GSE_CFG_USERNAME"] = username
            env["GSE_CFG_PASSWORD"] = password
            log(f"GSE Fork: login as {username}")
            try:
                from sff.storage.settings import set_setting
                from sff.structs import Settings
                set_setting(Settings.STEAM_USER, username)
                set_setting(Settings.STEAM_PASS, password)
            except Exception:
                pass
        else:
            log("GSE Fork: anonymous mode")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            log(f"Running generate_emu_config.exe for app {app_id}...")
            result = subprocess.run(
                [str(run_exe), str(app_id)],
                env=env,
                cwd=str(run_dir),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=creation_flags,
            )
            if result.stdout:
                for line in result.stdout.strip().splitlines()[-15:]:
                    log(f"  [gse] {line}")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-5:]:
                    log(f"  [gse-err] {line}")
            if result.returncode != 0:
                log(f"generate_emu_config.exe exited with code {result.returncode}")
                return False
            else:
                log("\u2713 GSE Fork config generation complete")
        except subprocess.TimeoutExpired:
            log("generate_emu_config.exe timed out after 120 s")
            return False
        except Exception as e:
            log(f"Error running generate_emu_config.exe: {e}")
            return False
        # copy generated steam_settings to game dir
        src_settings = run_dir / "output" / str(app_id) / "steam_settings"
        if src_settings.exists():
            dst_settings = Path(game_dir) / "steam_settings"
            dst_settings.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_settings, dst_settings, dirs_exist_ok=True)
            log("\u2713 Copied steam_settings from GSE Fork output")
        else:
            log(f"GSE Fork output not found — expected {src_settings}")
            log("  Config generation may have failed silently; check [gse] lines above")
            return False
        # ensure configs.user.ini has saves_folder_name (GSE tool may omit it)
        user_ini = Path(game_dir) / "steam_settings" / "configs.user.ini"
        if user_ini.exists():
            content = user_ini.read_text(encoding="utf-8", errors="replace")
            if "saves_folder_name" not in content:
                content += "\n[user::saves]\nsaves_folder_name=GSE Saves\n"
                user_ini.write_text(content, encoding="utf-8")
        else:
            user_ini.parent.mkdir(parents=True, exist_ok=True)
            user_ini.write_text("[user::saves]\nsaves_folder_name=GSE Saves\n", encoding="utf-8")
        return True

    @staticmethod
    def _extract_launch_configs(pics_data):
        """extract platform-appropriate launch configs from PICS data"""
        configs = []
        launch_data = pics_data.get("config", {}).get("launch", {})
        target_os = "linux" if sys.platform != "win32" else "windows"
        for key, value in launch_data.items():
            oslist = value.get("config", {}).get("oslist", "").lower()
            if oslist and target_os not in oslist:
                continue
            configs.append({
                "executable": value.get("executable", ""),
                "arguments": value.get("arguments", ""),
                "workingdir": value.get("workingdir", ""),
                "description": value.get("description", ""),
            })
        return configs

    def cache_from_lua(self, lua_content, app_id):
        """cache app info parsed from lua content"""
        info = self.cache.parse_lua_for_cache(lua_content, app_id)
        self.cache.save_app_info(info)
        logger.info("Cached app info for %d from lua", app_id)
