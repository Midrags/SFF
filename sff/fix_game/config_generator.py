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
Goldberg emulator config generator.

Creates the steam_settings/ folder with all config files:
- steam_appid.txt
- configs.app.ini (DLC, cloud save dirs)
- configs.user.ini (account name, steamid, language)
- configs.main.ini (connectivity settings)
- configs.overlay.ini
- achievements.json (from Steam Web API)
- stats.json
- supported_languages.txt
- depots.txt
- controller/controls.txt

Mirrors Solus GoldbergConfigGenerator.cs + GoldbergLogic.cs
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

STEAMCMD_API_URL = "https://steamcmd.morrenus.net/api"
STEAM_WEB_API_URL = "https://api.steampowered.com"
STEAM_STORE_API_URL = "https://store.steampowered.com/api"

# default language list if we can't fetch from API
DEFAULT_LANGUAGES = [
    "english", "french", "italian", "german", "spanish",
    "arabic", "japanese", "koreana", "polish", "brazilian",
    "russian", "schinese", "latam", "tchinese",
]

# default controller mappings (same as Solus GoldbergLogic.cs)
DEFAULT_CONTROLLER_MAPPINGS = """AxisL=LJOY=joystick_move
AxisR=RJOY=joystick_move
AnalogL=LTRIGGER=trigger
AnalogR=RTRIGGER=trigger
LUp=DUP
LDown=DDOWN
LLeft=DLEFT
LRight=DRIGHT
RUp=Y
RDown=A
RLeft=X
RRight=B
CLeft=BACK
CRight=START
LStickPush=LSTICK
RStickPush=RSTICK
LTrigTop=LBUMPER
RTrigTop=RBUMPER"""


class GoldbergConfigGenerator:
    """
    Generates the steam_settings/ folder for the Goldberg emulator.
    
    Uses Steam Web API for achievements/stats and SteamCMD API for
    depot/DLC/language info.
    """

    def __init__(self, steam_web_api_key: Optional[str] = None):
        self.steam_web_api_key = steam_web_api_key

    def generate(
        self,
        app_id: int,
        target_dir: str,
        language: str = "english",
        steam_id: str = "76561198001737783",
        player_name: str = "Player",
        dlc_list: Optional[dict] = None,
        cloud_save_paths: Optional[dict] = None,
        log_func=None,
    ) -> bool:
        """
        Generate the full steam_settings/ folder.
        
        Args:
            app_id: Steam app ID
            target_dir: game directory where steam_settings/ will be created
            language: game language
            steam_id: Steam64 ID for configs.user.ini
            player_name: player name for configs.user.ini
            dlc_list: optional pre-fetched DLC dict {id: name}
            cloud_save_paths: optional pre-fetched cloud save paths
            log_func: optional callback for status messages
        
        Returns True on success.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        settings_dir = Path(target_dir) / "steam_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)

        try:
            # steam_appid.txt
            self._write_appid(app_id, target_dir, log)

            # configs.app.ini (DLC + cloud saves)
            self._write_app_config(app_id, settings_dir, dlc_list, cloud_save_paths, log)

            # configs.user.ini (account name, steamid, language)
            self._write_user_config(settings_dir, steam_id, player_name, language, log)

            # configs.main.ini (connectivity settings)
            self._write_main_config(settings_dir, log)

            # configs.overlay.ini
            self._write_overlay_config(settings_dir, log)

            # achievements.json
            if self.steam_web_api_key:
                self._fetch_achievements(app_id, settings_dir, log)
            else:
                log("No Steam Web API key - skipping achievements")

            # supported_languages.txt
            self._fetch_languages(app_id, settings_dir, log)

            # depots.txt
            self._fetch_depots(app_id, settings_dir, log)

            # controller/controls.txt
            self._write_controller_config(settings_dir, log)

            log("Config generation complete")
            return True

        except Exception as e:
            logger.error("Config generation failed: %s", e)
            log(f"Error: {e}")
            return False

    def _write_appid(self, app_id: int, target_dir: str, log):
        """write steam_appid.txt to the game root"""
        path = Path(target_dir) / "steam_appid.txt"
        path.write_text(str(app_id), encoding="utf-8")
        log("✓ Created steam_appid.txt")

    def _write_app_config(self, app_id, settings_dir, dlc_list, cloud_save_paths, log):
        """write configs.app.ini with DLC and cloud save directories"""
        lines = ["[app::general]", f"build_id=0", ""]

        # DLC section
        lines.append("[app::dlcs]")
        lines.append("unlock_all=0")

        if dlc_list:
            for dlc_id, dlc_name in dlc_list.items():
                lines.append(f"{dlc_id}={dlc_name}")
            log(f"✓ Added {len(dlc_list)} DLCs to config")
        else:
            # try to fetch from SteamCMD API
            fetched = self._fetch_dlcs(app_id)
            if fetched:
                for dlc_id, dlc_name in fetched.items():
                    lines.append(f"{dlc_id}={dlc_name}")
                log(f"✓ Fetched {len(fetched)} DLCs from API")
            else:
                log("No DLCs found")

        # cloud save section
        if cloud_save_paths:
            lines.append("")
            for platform, paths in cloud_save_paths.items():
                lines.append(f"[app::cloud_save::{platform}]")
                for path in paths:
                    lines.append(f"path={path}")
            log("✓ Added cloud save paths")

        path = settings_dir / "configs.app.ini"
        path.write_text("\n".join(lines), encoding="utf-8")
        log("✓ Created configs.app.ini")

    def _write_user_config(self, settings_dir, steam_id, player_name, language, log):
        """write configs.user.ini with account settings"""
        content = f"""[user::general]
account_name={player_name}
account_steamid={steam_id}
language={language}
"""
        (settings_dir / "configs.user.ini").write_text(content, encoding="utf-8")
        log("✓ Created configs.user.ini")

    def _write_main_config(self, settings_dir, log):
        """write configs.main.ini with connectivity settings"""
        content = """[main::connectivity]
disable_lan_only=1
"""
        (settings_dir / "configs.main.ini").write_text(content, encoding="utf-8")
        log("✓ Created configs.main.ini")

    def _write_overlay_config(self, settings_dir, log):
        """write configs.overlay.ini"""
        content = "[overlay::general]\nenable_experimental_overlay=0\n"
        (settings_dir / "configs.overlay.ini").write_text(content, encoding="utf-8")
        log("✓ Created configs.overlay.ini")

    def _write_controller_config(self, settings_dir, log):
        """write default controller mappings"""
        controller_dir = settings_dir / "controller"
        controller_dir.mkdir(exist_ok=True)
        (controller_dir / "controls.txt").write_text(DEFAULT_CONTROLLER_MAPPINGS, encoding="utf-8")
        log("✓ Created controller/controls.txt")

    def _fetch_achievements(self, app_id, settings_dir, log):
        """fetch achievements from Steam Web API and save as JSON"""
        url = (f"{STEAM_WEB_API_URL}/ISteamUserStats/GetSchemaForGame/v2/"
               f"?key={self.steam_web_api_key}&appid={app_id}&l=english")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            achievements = data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
            if achievements:
                (settings_dir / "achievements.json").write_text(
                    json.dumps(achievements, indent=2), encoding="utf-8"
                )
                log(f"✓ Saved {len(achievements)} achievements")
            else:
                log("No achievements found for this game")

            # also save stats if available
            stats = data.get("game", {}).get("availableGameStats", {}).get("stats", [])
            if stats:
                (settings_dir / "stats.json").write_text(
                    json.dumps(stats, indent=2), encoding="utf-8"
                )
                log(f"✓ Saved {len(stats)} stats")

        except Exception as e:
            log(f"Could not fetch achievements: {e}")

    def _fetch_languages(self, app_id, settings_dir, log):
        """fetch supported languages from SteamCMD API"""
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()

            lang_str = (data.get("data", {}).get(str(app_id), {})
                        .get("depots", {}).get("baselanguages", ""))
            if lang_str:
                languages = [l.strip() for l in lang_str.split(",") if l.strip()]
                (settings_dir / "supported_languages.txt").write_text(
                    "\n".join(languages), encoding="utf-8"
                )
                log(f"✓ Fetched {len(languages)} languages")
                return
        except Exception as e:
            log(f"Could not fetch languages: {e}")

        # fallback to defaults
        (settings_dir / "supported_languages.txt").write_text(
            "\n".join(DEFAULT_LANGUAGES), encoding="utf-8"
        )
        log("✓ Created languages file with defaults")

    def _fetch_depots(self, app_id, settings_dir, log):
        """fetch depot IDs from SteamCMD API"""
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()

            depots = data.get("data", {}).get(str(app_id), {}).get("depots", {})
            depot_ids = [k for k in depots.keys() if k.isdigit()]
            if depot_ids:
                (settings_dir / "depots.txt").write_text(
                    "\n".join(depot_ids), encoding="utf-8"
                )
                log(f"✓ Fetched {len(depot_ids)} depots")
        except Exception as e:
            log(f"Could not fetch depots: {e}")

    def _fetch_dlcs(self, app_id) -> dict:
        """fetch DLC list from SteamCMD API"""
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()

            dlc_str = (data.get("data", {}).get(str(app_id), {})
                       .get("extended", {}).get("listofdlc", ""))
            if dlc_str:
                dlc_ids = [d.strip() for d in dlc_str.split(",") if d.strip() and d.strip().isdigit()]
                return {dlc_id: "DLC" for dlc_id in dlc_ids}
        except Exception as e:
            logger.warning("Could not fetch DLCs: %s", e)
        return {}
