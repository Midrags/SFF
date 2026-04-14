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
import logging
from pathlib import Path
from typing import Optional
from enum import Enum

import httpx

from sff.fix_game.cache import FixGameCache
from sff.fix_game.goldberg_updater import GoldbergUpdater
from sff.fix_game.config_generator import GoldbergConfigGenerator
from sff.fix_game.steamstub_unpacker import SteamStubUnpacker
from sff.fix_game.goldberg_applier import GoldbergApplier

logger = logging.getLogger(__name__)

STEAM_STORE_API = "https://store.steampowered.com/api"


class EmuMode(Enum):
    """which Goldberg mode to use"""
    REGULAR = "regular"
    COLDCLIENT_LOADER = "coldclient_loader"
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
        steam_web_api_key: Optional[str] = None,
        language: str = "english",
        steam_id: str = "76561198001737783",
        player_name: str = "Player",
        emu_mode: str = "regular",
        skip_drm_check: bool = False,
        skip_steamstub: bool = False,
        skip_goldberg_update: bool = False,
        log_func=None,
    ) -> bool:
        """
        Run the full Fix Game pipeline.
        
        Args:
            app_id: Steam app ID
            game_dir: path to the game directory
            steam_web_api_key: optional Steam Web API key for achievements
            language: game language
            steam_id: Steam64 ID
            player_name: display name
            emu_mode: "regular", "coldclient_loader", or "coldloader_dll"
            skip_drm_check: skip DRM detection step
            skip_steamstub: skip SteamStub unpacking
            log_func: callback for status updates
        
        Returns True on success.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        log(f"=== Fix Game Pipeline: App {app_id} ===")
        log(f"Game directory: {game_dir}")
        log(f"Mode: {emu_mode}")

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
                    emu_mode = "coldclient_loader"

        # --- Step 1: Goldberg Auto-Update ---
        log("\n--- Step 1: Goldberg Update ---")
        if not skip_goldberg_update:
            if not self.updater.ensure_goldberg(log_func=log):
                log("WARNING: Could not update Goldberg — using cached/bundled version")
                if not self.cache.has_goldberg_dlls():
                    log("ABORT: No Goldberg DLLs available")
                    return False
        else:
            log("Goldberg auto-update skipped")
            if not self.cache.has_goldberg_dlls():
                log("ABORT: No Goldberg DLLs available and auto-update is disabled")
                return False

        # --- Step 2: Config Generation ---
        log("\n--- Step 2: Config Generation ---")
        cached_info = self.cache.load_app_info(app_id)
        generator = GoldbergConfigGenerator(steam_web_api_key)
        generator.generate(
            app_id=app_id,
            target_dir=game_dir,
            language=language,
            steam_id=steam_id,
            player_name=player_name,
            dlc_list=cached_info.dlc_list if cached_info else None,
            cloud_save_paths=cached_info.cloud_save_paths if cached_info else None,
            log_func=log,
        )

        # --- Step 3: SteamStub Unpacking ---
        if not skip_steamstub:
            log("\n--- Step 3: SteamStub Unpacking ---")
            if self.unpacker.is_available():
                count = self.unpacker.unpack_directory(game_dir, log_func=log)
                if count > 0:
                    log(f"Unpacked {count} SteamStub-protected file(s)")
                else:
                    log("No SteamStub protection detected")
            else:
                log("Steamless not available — skipping SteamStub check")

        # --- Step 4: Goldberg Application ---
        log("\n--- Step 4: Goldberg Application ---")
        mode = EmuMode(emu_mode)

        if mode == EmuMode.REGULAR:
            success, msg = self.applier.apply(game_dir, log_func=log)
        elif mode == EmuMode.COLDCLIENT_LOADER:
            success, msg = self.applier.apply_coldclient_loader(game_dir, app_id, log_func=log)
        elif mode == EmuMode.COLDLOADER_DLL:
            success, msg = self.applier.apply_coldloader_dll(game_dir, app_id, log_func=log)
        else:
            success, msg = False, f"Unknown mode: {emu_mode}"

        log(msg)

        if not success:
            return False

        # --- Step 5: Launch.bat Generation ---
        log("\n--- Step 5: Launch Script ---")
        self._generate_launch_script(app_id, game_dir, emu_mode, log)

        log("\n=== Fix Game Complete ===")
        return True

    def restore_game(self, game_dir: str, log_func=None) -> tuple[bool, str]:
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

    def check_drm(self, app_id: int, log_func=None) -> DrmCheckResult:
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

    def _generate_launch_script(self, app_id: int, game_dir: str, emu_mode: str, log):
        """generate Launch.bat from PICS data or by finding the main exe"""
        game_path = Path(game_dir)

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

                    bat_name = f"Launch{'_' + desc.replace(' ', '_') if i > 0 else ''}.bat"
                    bat_content = f'@echo off\ncd /d "%~dp0{workdir}"\nstart "" "{exe}" {args}\n'
                    (game_path / bat_name).write_text(bat_content, encoding="utf-8")
                    log(f"✓ Created {bat_name} ({exe})")
                return

        # fallback: ColdClient loader mode
        if emu_mode in ("coldclient_loader",):
            for loader in ["steamclient_loader_x64.exe", "steamclient_loader_x32.exe"]:
                if (game_path / loader).exists():
                    bat_content = f'@echo off\ncd /d "%~dp0"\nstart "" "{loader}"\n'
                    (game_path / "Launch.bat").write_text(bat_content, encoding="utf-8")
                    log(f"✓ Created Launch.bat (via {loader})")
                    return

        # fallback: find largest exe
        main_exe = self.applier.find_main_exe(game_dir)
        if main_exe:
            exe_rel = os.path.relpath(main_exe, game_dir)
            bat_content = f'@echo off\ncd /d "%~dp0"\nstart "" "{exe_rel}"\n'
            (game_path / "Launch.bat").write_text(bat_content, encoding="utf-8")
            log(f"✓ Created Launch.bat ({Path(main_exe).name})")
        else:
            log("Could not determine main executable for Launch.bat")

    def _extract_launch_configs(self, pics_data: dict) -> list[dict]:
        """extract Windows launch configs from PICS data"""
        configs = []
        launch_data = pics_data.get("config", {}).get("launch", {})

        for key, value in launch_data.items():
            oslist = value.get("config", {}).get("oslist", "windows")
            if "windows" not in oslist.lower():
                continue

            configs.append({
                "executable": value.get("executable", ""),
                "arguments": value.get("arguments", ""),
                "workingdir": value.get("workingdir", ""),
                "description": value.get("description", ""),
            })

        return configs

    def cache_from_lua(self, lua_content: str, app_id: int):
        """cache app info parsed from lua content"""
        info = self.cache.parse_lua_for_cache(lua_content, app_id)
        self.cache.save_app_info(info)
        logger.info("Cached app info for %d from lua", app_id)
