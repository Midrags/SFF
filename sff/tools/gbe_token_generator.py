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
GBE Token Generator — generates full Goldberg emulator config packages.

Fetches achievements (with icons), depots, DLCs, languages, and generates
a complete steam_settings/ package that can be zipped and shared.

Mirrors Solus GoldbergLogic.cs (410 lines).
"""

import os
import json
import shutil
import logging
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

STEAM_WEB_API_URL = "https://api.steampowered.com"
STEAMCMD_API_URL = "https://steamcmd.morrenus.net/api"
STEAM_CDN_ICONS = "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps"


class GBETokenGenerator:
    """
    Generates a complete Goldberg emulator configuration package.

    Output contents:
    - steam_settings/
        - steam_appid.txt
        - configs.app.ini (DLC list)
        - configs.main.ini
        - configs.overlay.ini
        - achievements.json
        - stats.json
        - supported_languages.txt
        - depots.txt
        - achievement_images/ (downloaded icons)
        - controller/controls.txt
    """

    def __init__(self, steam_web_api_key):
        self.api_key = steam_web_api_key

    def generate(
        self,
        app_id: int,
        output_path: str,
        language = "english",
        player_name = "Player",
        steam_id = "76561198001737783",
        download_icons = True,
        create_zip = True,
        log_func=None,
    ):
        """
        Generate a full GBE config package.
        If create_zip=True, creates {output_path}/{app_id}_gbe_config.zip
        Otherwise creates {output_path}/steam_settings/
        Returns True on success.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        out_dir = Path(output_path)
        settings_dir = out_dir / "steam_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        try:
            # steam_appid.txt
            (settings_dir / "steam_appid.txt").write_text(str(app_id), encoding="utf-8")
            log(f"✓ steam_appid.txt ({app_id})")
            # achievements + stats
            achievements = self._fetch_achievements(app_id, log)
            if achievements:
                (settings_dir / "achievements.json").write_text(
                    json.dumps(achievements, indent=2), encoding="utf-8"
                )
                log(f"✓ {len(achievements)} achievements")
                # download achievement icons
                if download_icons:
                    self._download_achievement_icons(app_id, achievements, settings_dir, log)
            stats = self._fetch_stats(app_id, log)
            if stats:
                (settings_dir / "stats.json").write_text(
                    json.dumps(stats, indent=2), encoding="utf-8"
                )
                log(f"✓ {len(stats)} stats")
            # DLC list
            dlcs = self._fetch_dlcs(app_id, log)
            if dlcs:
                dlc_lines = ["[app::dlcs]", "unlock_all=0"]
                for dlc_id, dlc_name in dlcs.items():
                    dlc_lines.append(f"{dlc_id}={dlc_name}")
                # write as part of configs.app.ini
                app_config = "\n".join([
                    "[app::general]", f"build_id=0", "",
                    *dlc_lines
                ])
                (settings_dir / "configs.app.ini").write_text(app_config, encoding="utf-8")
                log(f"✓ {len(dlcs)} DLCs")
            else:
                (settings_dir / "configs.app.ini").write_text(
                    "[app::general]\nbuild_id=0\n\n[app::dlcs]\nunlock_all=0\n",
                    encoding="utf-8"
                )
            # configs.overlay.ini — experimental overlay OFF by default (crashes DX9/32-bit games)
            (settings_dir / "configs.overlay.ini").write_text(
                "[overlay::general]\nenable_experimental_overlay=0\n", encoding="utf-8"
            )
            log("✓ configs.overlay.ini")
            log("⚠ configs.main.ini not written per-game — lives in global GSE Saves/settings/. Copy it to steam_settings/ manually if per-game network customisation is needed. Note: some games (e.g. YuGiOh) break if configs.main.ini is present in steam_settings/.")
            # languages
            languages = self._fetch_languages(app_id, log)
            (settings_dir / "supported_languages.txt").write_text(
                "\n".join(languages), encoding="utf-8"
            )
            log(f"✓ {len(languages)} languages")
            # depots
            depots = self._fetch_depots(app_id, log)
            if depots:
                (settings_dir / "depots.txt").write_text(
                    "\n".join(depots), encoding="utf-8"
                )
                log(f"✓ {len(depots)} depots")
            # controller
            controller_dir = settings_dir / "controller"
            controller_dir.mkdir(exist_ok=True)
            (controller_dir / "controls.txt").write_text(
                "AxisL=LJOY=joystick_move\nAxisR=RJOY=joystick_move\n"
                "AnalogL=LTRIGGER=trigger\nAnalogR=RTRIGGER=trigger\n"
                "LUp=DUP\nLDown=DDOWN\nLLeft=DLEFT\nLRight=DRIGHT\n"
                "RUp=Y\nRDown=A\nRLeft=X\nRRight=B\n"
                "CLeft=BACK\nCRight=START\n"
                "LStickPush=LSTICK\nRStickPush=RSTICK\n"
                "LTrigTop=LBUMPER\nRTrigTop=RBUMPER\n",
                encoding="utf-8"
            )
            # create zip if requested
            if create_zip:
                zip_path = out_dir / f"{app_id}_gbe_config.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for f in settings_dir.rglob("*"):
                        if f.is_file():
                            arcname = f.relative_to(out_dir)
                            zf.write(f, arcname)
                log(f"✓ Created {zip_path.name}")
                # cleanup settings dir after zipping
                shutil.rmtree(settings_dir, ignore_errors=True)
            log("GBE config generation complete")
            return True
        except Exception as e:
            logger.error("GBE token generation failed: %s", e)
            log(f"Error: {e}")
            return False

    def _fetch_achievements(self, app_id, log):
        """fetch achievement definitions from Steam Web API"""
        url = (f"{STEAM_WEB_API_URL}/ISteamUserStats/GetSchemaForGame/v2/"
               f"?key={self.api_key}&appid={app_id}&l=english")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            return data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
        except Exception as e:
            log(f"Could not fetch achievements: {e}")
            return []

    def _fetch_stats(self, app_id, log):
        """fetch stat definitions from Steam Web API"""
        url = (f"{STEAM_WEB_API_URL}/ISteamUserStats/GetSchemaForGame/v2/"
               f"?key={self.api_key}&appid={app_id}&l=english")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            return data.get("game", {}).get("availableGameStats", {}).get("stats", [])
        except Exception as e:
            log(f"Could not fetch stats: {e}")
            return []

    def _fetch_dlcs(self, app_id, log):
        """fetch DLC list + names from SteamCMD API + Steam Store"""
        dlcs = {}
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()
            dlc_str = (data.get("data", {}).get(str(app_id), {})
                       .get("extended", {}).get("listofdlc", ""))
            if dlc_str:
                dlc_ids = [d.strip() for d in dlc_str.split(",") if d.strip().isdigit()]
                # try to get names from store API
                with httpx.Client(timeout=30.0) as client:
                    for dlc_id in dlc_ids:
                        try:
                            resp = client.get(
                                "https://store.steampowered.com/api/appdetails",
                                params={"appids": dlc_id},
                            )
                            if resp.status_code == 200:
                                dlc_data = resp.json().get(dlc_id, {}).get("data", {})
                                dlcs[dlc_id] = dlc_data.get("name", f"DLC {dlc_id}")
                            else:
                                dlcs[dlc_id] = f"DLC {dlc_id}"
                        except Exception:
                            dlcs[dlc_id] = f"DLC {dlc_id}"
        except Exception as e:
            log(f"Could not fetch DLCs: {e}")
        return dlcs

    def _fetch_languages(self, app_id, log):
        """fetch supported languages"""
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()
            lang_str = (data.get("data", {}).get(str(app_id), {})
                        .get("depots", {}).get("baselanguages", ""))
            if lang_str:
                return [l.strip() for l in lang_str.split(",") if l.strip()]
        except Exception as e:
            log(f"Could not fetch languages: {e}")
        return ["english"]

    def _fetch_depots(self, app_id, log):
        """fetch depot IDs"""
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()
            depots = data.get("data", {}).get(str(app_id), {}).get("depots", {})
            return [k for k in depots.keys() if k.isdigit()]
        except Exception as e:
            log(f"Could not fetch depots: {e}")
            return []

    def _download_achievement_icons(self, app_id, achievements, settings_dir, log):
        """download achievement icons to steam_settings/achievement_images/"""
        icons_dir = settings_dir / "achievement_images"
        icons_dir.mkdir(exist_ok=True)
        downloaded = 0
        try:
            with httpx.Client(timeout=10.0) as client:
                for ach in achievements:
                    name = ach.get("name", "")
                    icon = ach.get("icon", "")
                    icon_gray = ach.get("icongray", "")
                    if icon:
                        url = f"{STEAM_CDN_ICONS}/{app_id}/{icon}"
                        try:
                            resp = client.get(url)
                            if resp.status_code == 200:
                                (icons_dir / f"{name}.jpg").write_bytes(resp.content)
                                downloaded += 1
                        except Exception:
                            pass
                    if icon_gray:
                        url = f"{STEAM_CDN_ICONS}/{app_id}/{icon_gray}"
                        try:
                            resp = client.get(url)
                            if resp.status_code == 200:
                                (icons_dir / f"{name}_locked.jpg").write_bytes(resp.content)
                        except Exception:
                            pass
            log(f"✓ Downloaded {downloaded} achievement icons")
        except Exception as e:
            log(f"Icon download error: {e}")
