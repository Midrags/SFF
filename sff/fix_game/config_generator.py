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
- configs.overlay.ini
- %APPDATA%/GSE Saves/settings/configs.user.ini  (global identity — all games)
- %APPDATA%/GSE Saves/settings/configs.main.ini  (global connectivity — all games)
- %APPDATA%/GSE Saves/settings/account_avatar.*  (global avatar — all games)
- achievements.json (from Steam Web API)
- stats.json
- supported_languages.txt
- depots.txt
- controller/controls.txt

Mirrors Solus GoldbergConfigGenerator.cs + GoldbergLogic.cs
"""

import os
import sys
import json
import logging
import shutil
from pathlib import Path

import httpx

from sff.steam_store import get_dlc_list_from_store, get_dlc_names_from_store

logger = logging.getLogger(__name__)


def _get_gbe_saves_root() -> Path:
    """Return the platform-aware GSE Saves root directory.
    Matches the official gbe_fork README:
      Windows: %APPDATA%\\GSE Saves
      Linux:   $XDG_DATA_HOME/GSE Saves  (if set)
               ~/.local/share/GSE Saves  (default)
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "GSE Saves"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "GSE Saves"
    return Path.home() / ".local" / "share" / "GSE Saves"


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

    def __init__(self, steam_web_api_key = None):
        self.steam_web_api_key = steam_web_api_key

    def generate(
        self,
        app_id: int,
        target_dir: str,
        language = "english",
        steam_id = "76561198001737783",
        player_name = "Player",
        dlc_list = None,
        cloud_save_paths = None,
        log_func=None,
        avatar_path = None,
        simple_mode = False,
    ):
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
            avatar_path: optional path to avatar image (.png/.jpg/.jpeg)
            simple_mode: if True, skip all API calls (fast offline generation)
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
            # configs.app.ini (DLC + cloud saves — always fetched, even in simple mode)
            self._write_app_config(app_id, settings_dir, dlc_list, cloud_save_paths, log,
                                   skip_api=False)
            # configs.overlay.ini (per-game — experimental overlay off by default; on by default crashes DX9/32-bit games)
            self._write_overlay_config(settings_dir, log, enable_overlay=False)
            if not simple_mode:
                # achievements.json
                if self.steam_web_api_key:
                    self._fetch_achievements(app_id, settings_dir, log)
                else:
                    log("No Steam Web API key - skipping achievements")
                # supported_languages.txt
                self._fetch_languages(app_id, settings_dir, log)
                # depots.txt
                self._fetch_depots(app_id, settings_dir, log)
            else:
                log("Simple mode: skipping API calls (achievements/languages/depots)")
            # controller/controls.txt
            self._write_controller_config(settings_dir, log)
            # global GBE identity settings (%APPDATA%\GSE Saves\settings\) — applied to all games
            global_dir = _get_gbe_saves_root() / "settings"
            self._write_global_settings(global_dir, player_name, steam_id, language, avatar_path, log)
            log("Config generation complete")
            return True
        except Exception as e:
            logger.error("Config generation failed: %s", e)
            log(f"Error: {e}")
            return False

    def _write_appid(self, app_id, target_dir, log):
        """write steam_appid.txt to the game root"""
        path = Path(target_dir) / "steam_appid.txt"
        path.write_text(str(app_id), encoding="utf-8")
        log("\u2713 Created steam_appid.txt")

    def _write_app_config(self, app_id, settings_dir, dlc_list, cloud_save_paths, log,
                          skip_api = False):
        """write configs.app.ini with DLC and cloud save directories"""
        # DLC entries fetched/provided — listed FIRST before unlock_all (GoldbergGUI format)
        dlc_lines = []
        if dlc_list:
            for dlc_id, dlc_name in dlc_list.items():
                dlc_lines.append(f"{dlc_id}={dlc_name}")
            log(f"\u2713 Added {len(dlc_list)} DLCs to config")
        elif not skip_api:
            fetched = self._fetch_dlcs(app_id, log)
            if fetched:
                for dlc_id, dlc_name in fetched.items():
                    dlc_lines.append(f"{dlc_id}={dlc_name}")
                log(f"\u2713 Fetched {len(fetched)} DLCs from API")
            else:
                log("No DLCs found (game may have none, or all APIs failed)")
        lines = [
            "# ################################################################################ #",
            "# you do not have to specify everything, pick and choose the options you need only #",
            "# ################################################################################ #",
            "",
            "[app::general]",
            "# by default the emu will report a 'non-beta' branch when the game calls `Steam_Apps::GetCurrentBetaName()`",
            "# 1=make the game/app think we're playing on a beta branch",
            "# default=0",
            "is_beta_branch=0",
            "# the name of the current branch, this must also exist in 'branches.json'",
            "# otherwise will be ignored by the emu and the default 'public' branch will be used",
            "# default=public",
            "branch_name=public",
            "",
            "[app::dlcs]",
            *dlc_lines,
            "",
            "# 1=report all DLCs as unlocked",
            "# 0=report only the DLCs mentioned",
            "# some games check for 'hidden' DLCs, hence this should be set to 1 in that case",
            "# but other games detect emus by querying for a fake/bad DLC, hence this should be set to 0 in that case",
            "# default=1",
            "unlock_all=1",
            "# format: ID=name",
            "#   1234=DLCNAME",
            "#   56789=This is another example DLC name",
            "",
            "[app::controller]",
            "# 1=Enable SteamInput (auto-enabled when action sets exist in steam_settings/controller/)",
            "# default=0",
            "steam_input=0",
            "# Controller type: XBOX360 (default) | XBOXONE | PS3 | PS4 | PS5 | SWITCH",
            "type=XBOX360",
            "",
            "[app::cloud_save::general]",
            "# should the emu create the default userdata dir on startup",
            "# default=0",
            "create_default_dir=0",
            "# should the emu create the dirs specified below on startup",
            "# default=0",
            "create_specific_dirs=0",
        ]
        if cloud_save_paths:
            for platform, paths in cloud_save_paths.items():
                lines.append("")
                lines.append(f"[app::cloud_save::{platform}]")
                for p in paths:
                    lines.append(f"dir1={p}")
            log("\u2713 Added cloud save paths")
        else:
            lines += [
                "",
                "# Example cloud save paths (edit as needed):",
                "# [app::cloud_save::win]",
                "# dir1={::WinAppDataRoaming::}/PublisherName/GameName",
                "# dir2={::WinMyDocuments::}/PublisherName/GameName/{::Steam3AccountID::}",
                "# [app::cloud_save::linux]",
                "# dir1={::LinuxXdgDataHome::}/PublisherName/GameName",
            ]
        path = settings_dir / "configs.app.ini"
        path.write_text("\n".join(lines), encoding="utf-8")
        log("\u2713 Created configs.app.ini")

    def _write_user_config(self, settings_dir, steam_id, player_name, language, log):
        """write configs.user.ini with account settings"""
        content = f"""# ##############################################################################
# you do not have to specify everything, pick and choose the options you need only
# ##############################################################################

[user::general]
# user account name displayed in-game
# default=gse orca
account_name={player_name}
# your account ID in Steam64 format
# if invalid, the emu will ignore it and generate a proper one
# default=randomly generated once and saved in global settings
account_steamid={steam_id}
# language reported to the app/game
# must exist in 'supported_languages.txt', otherwise ignored
# see: https://partner.steamgames.com/doc/store/localization/languages
# default=english
language={language}
# report a country IP if the game queries it (ISO 3166-1-alpha-2)
# default=US
ip_country=US

[user::saves]
# force the emu to use this path instead of the default global location
# path is relative to the .dll location (or absolute)
# when set, global settings folder is completely ignored (portable mode)
# default= (empty = use global GSE Saves folder)
# local_save_path=./saves
# name of the base save folder (only used when local_save_path is NOT set)
# default=GSE Saves
saves_folder_name=GSE Saves
"""
        (settings_dir / "configs.user.ini").write_text(content, encoding="utf-8")
        log("\u2713 Created configs.user.ini")

    def _write_main_config(self, settings_dir, log, enable_avatar = False):
        """write configs.main.ini with full commented template"""
        avatar_val = "1" if enable_avatar else "0"
        content = f"""# ##############################################################################

[main::general]
# use new app ticket format (recommended)
# default=1
new_app_ticket=1

# generate GC token
# default=1
gc_token=1

# block unknown/unrecognized clients from connecting
# default=0
block_unknown_clients=0

# report as Steam Deck
# default=0
steam_deck=0

# enable account avatar (requires account_avatar.png/jpg in steam_settings/)
# default=0
enable_account_avatar={avatar_val}

# enable voice chat (experimental)
# default=0
enable_voice_chat=0

[main::stats]
# disable creation of unknown leaderboards
# default=0
disable_leaderboards_create_unknown=0

# allow stats not defined in stats.json to be set/read
# default=0
allow_unknown_stats=0

# track achievement progress (fraction displayed in overlay)
# default=1
stat_achievement_progress_functionality=1

# only save higher value for progress stats
# default=1
save_only_higher_stat_achievement_progress=1

[main::connectivity]
# 1=disable LAN-only networking (allows internet-style connections)
# default=0
disable_lan_only=1

# completely disable all networking
# default=0
disable_networking=0

# UDP listen port for local network features
# default=47584
listen_port=47584

# run in offline mode (no network at all)
# default=0
offline=0

# do not share stats with game servers
# default=0
disable_sharing_stats_with_gameserver=0

# share leaderboard data over local network
# default=0
share_leaderboards_over_network=0

# disable lobby creation
# default=0
disable_lobby_creation=0

[main::misc]
# bypass achievements (mark all as unlocked)
# default=0
achievements_bypass=0

# force SteamHTTP to always return success
# default=0
force_steamhttp_success=0

# allow downloading real HTTP requests via steamHTTP
# default=0
download_steamhttp_requests=0
"""
        (settings_dir / "configs.main.ini").write_text(content, encoding="utf-8")
        log("\u2713 Created configs.main.ini")

    def _write_overlay_config(self, settings_dir, log, enable_overlay = True):
        """write configs.overlay.ini — full GoldbergGUI template"""
        content = f"""\
# ################################################################################ #
#                                                                                  #
#    USE AT YOUR OWN RISK :: This feature might cause crashes or other problems    #
#                                                                                  #
# ################################################################################ #
# you do not have to specify everything, pick and choose the options you need only #
# ################################################################################ #

[overlay::general]
# 1=enable the experimental overlay, might cause crashes
# default=0
enable_experimental_overlay={"1" if enable_overlay else "0"}
# amount of time to wait before attempting to detect and hook the renderer (DirectX, OpenGL, Vulkan, etc...)
# default=0
hook_delay_sec=0
# timeout for the renderer detector
# default=15
renderer_detector_timeout_sec=15
# 1=disable the achievements notifications
# default=0
disable_achievement_notification=0
# 1=disable friends invitations and messages notifications
# default=0
disable_friend_notification=0
# 1=disable showing notifications for achievements progress
# default=0
disable_achievement_progress=0
# 1=disable any warning in the overlay
# default=0
disable_warning_any=0
# 1=disable the bad app ID warning in the overlay
# default=0
disable_warning_bad_appid=0
# 1=disable the local_save warning in the overlay
# default=0
disable_warning_local_save=0
# by default the overlay will attempt to upload the achievements icons to the GPU
# so that they are displayed, in rare cases this might keep failing and cause FPS drop
# 0=prevent the overlay from attempting to upload the icons periodically,
#   in that case achievements icons won't be displayed
# default=1
upload_achievements_icons_to_gpu=1
# amount of frames to accumulate, to eventually calculate the average frametime (in milliseconds)
# lower values would result in instantaneous frametime/fps, but the FPS would be erratic
# higher values would result in a more stable frametime/fps, but will be inaccurate due to averaging over long time
# minimum allowed value=1
# default=10
fps_averaging_window=10

[overlay::appearance]
# load custom TrueType font from a path, it could be absolute, or relative
# relative paths will be looked up inside the local folder 'steam_settings/fonts/' first,
# if that wasn't found, it will be looked up inside the global folder 'GSE Saves/settings/fonts/'
# default=
Font_Override=
# global font size
# for built-in font, multiple of 16 is recommended, e.g. 16 32...
# default=16.0
Font_Size=16.0

# achievement icon size
Icon_Size=64.0

# spacing between characters
Font_Glyph_Extra_Spacing_x=1.0
Font_Glyph_Extra_Spacing_y=0.0

# background for all types of notifications
Notification_R=0.12
Notification_G=0.14
Notification_B=0.21
Notification_A=1.0

# notifications corners roundness
Notification_Rounding=10.0
# horizontal (x) and vertical (y) margins for the notifications
Notification_Margin_x=5.0
Notification_Margin_y=5.0

# duration/timing for various notification types (in seconds)
# duration of notification animation in seconds. Set to 0 to disable
Notification_Animation=0.35
# duration of achievement progress indication
Notification_Duration_Progress=6.0
# duration of achievement unlocked
Notification_Duration_Achievement=7.0
# duration of friend invitation
Notification_Duration_Invitation=8.0
# duration of chat message
Notification_Duration_Chat=4.0

# format for the achievement unlock date/time, limited to 79 characters
# if the output formatted string exceeded this limit, the builtin format will be used
# look for the format here: https://en.cppreference.com/w/cpp/chrono/c/strftime
# default=%Y/%m/%d - %H:%M:%S
Achievement_Unlock_Datetime_Format=%Y/%m/%d - %H:%M:%S

# main background when you press shift+tab
Background_R=0.12
Background_G=0.11
Background_B=0.11
Background_A=0.55

Element_R=0.30
Element_G=0.32
Element_B=0.40
Element_A=1.0

ElementHovered_R=0.278
ElementHovered_G=0.393
ElementHovered_B=0.602
ElementHovered_A=1.0

ElementActive_R=-1.0
ElementActive_G=-1.0
ElementActive_B=-1.0
ElementActive_A=-1.0

# ############################# #
# available options:
# top_left
# top_center
# top_right
# bot_left
# bot_center
# bot_right
# position of achievements
PosAchievement=bot_right
# position of invitations
PosInvitation=top_right
# position of chat messages
PosChatMsg=top_center
# ############################# #
# ############################# #
# FPS background color
Stats_Background_R=0.0
Stats_Background_G=0.0
Stats_Background_B=0.0
Stats_Background_A=0.6

# FPS text color
Stats_Text_R=0.8
Stats_Text_G=0.7
Stats_Text_B=0.0
Stats_Text_A=1.0

# FPS position in percentage [0.0, 1.0]
# X=0.0 : left
# X=1.0 : right
Stats_Pos_x=0.0

# Y=0.0 : up
# Y=1.0 : down
Stats_Pos_y=0.0
# ############################# #
"""
        (settings_dir / "configs.overlay.ini").write_text(content, encoding="utf-8")
        log("\u2713 Created configs.overlay.ini")

    def _deploy_avatar(self, avatar_path, settings_dir, log):
        """copy avatar image to steam_settings/account_avatar.{ext}"""
        src = Path(avatar_path)
        if not src.exists():
            log(f"Warning: avatar file not found: {avatar_path}")
            return
        ext = src.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            log(f"Warning: unsupported avatar format '{ext}' — skipping (use .png/.jpg/.jpeg)")
            return
        dst = settings_dir / f"account_avatar{ext}"
        shutil.copy2(src, dst)
        log(f"✓ Deployed avatar → {dst.name}")

    def _write_global_settings(
        self,
        global_dir: Path,
        player_name: str,
        steam_id: str,
        language: str,
        avatar_path,
        log,
    ):
        """Create/update %APPDATA%\\GSE Saves\\settings\\ — global GBE identity applied to all games.
        Avatar priority rule: NEVER put avatar in per-game steam_settings.
        - Explicit avatar_path → always copy to global.
        - No avatar_path + existing global avatar → leave it alone (preserve user custom).
        - No avatar_path + no global avatar → copy SFF.png as first-time default.
        """
        global_dir.mkdir(parents=True, exist_ok=True)
        # --- avatar (global only, never per-game) ---
        if avatar_path:
            src = Path(avatar_path)
            if src.exists():
                ext = src.suffix.lower()
                if ext in (".png", ".jpg", ".jpeg"):
                    shutil.copy2(src, global_dir / f"account_avatar{ext}")
                    log("\u2713 Deployed custom avatar \u2192 global settings")
        else:
            global_has_avatar = any(
                (global_dir / f"account_avatar{e}").exists()
                for e in (".png", ".jpg", ".jpeg")
            )
            if not global_has_avatar:
                from sff.utils import root_folder
                default = root_folder() / "SFF.png"
                if default.exists():
                    shutil.copy2(default, global_dir / "account_avatar.png")
                    log("\u2713 Deployed default avatar (SFF.png) \u2192 global settings")
        has_avatar = any(
            (global_dir / f"account_avatar{e}").exists()
            for e in (".png", ".jpg", ".jpeg")
        )
        # --- configs.main.ini (minimal, matching GoldbergGUI) ---
        main_content = (
            "[main::general]\n"
            f"enable_account_avatar={'1' if has_avatar else '0'}\n\n"
            "[main::connectivity]\n"
            "listen_port=47584\n"
        )
        (global_dir / "configs.main.ini").write_text(main_content, encoding="utf-8")
        log("\u2713 Updated global configs.main.ini")
        # --- configs.user.ini (minimal, matching GoldbergGUI) ---
        user_content = (
            "[user::general]\n\n"
            "# user account name\n"
            f"account_name={player_name}\n\n"
            "# Steam64 format\n"
            f"account_steamid={steam_id}\n\n"
            "# the language reported to the game, default is 'english', check 'API language code' in\n"
            "# https://partner.steamgames.com/doc/store/localization/languages\n"
            f"language={language}\n\n"
            "# ISO 3166-1-alpha-2 format, use this link to get the 'Alpha-2' country code:\n"
            "# https://www.iban.com/country-codes\n"
            "ip_country=US\n"
        )
        (global_dir / "configs.user.ini").write_text(user_content, encoding="utf-8")
        log("\u2713 Updated global configs.user.ini")

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

    def _fetch_dlcs(self, app_id, log):
        """Fetch DLC list with real names.
        Priority:
        1. SteamCMD API (morrenus.net) — mirrors Steam CM product info structure.
           Uses BOTH sources identical to GBE/GSE fork generate_emu_config.py:
             a) extended.listofdlc  — comma-separated DLC app IDs
             b) depots[*].dlcappid  — DLC IDs registered only through depot entries
           (see Detanup01/gbe_fork_tools and alex47exe/gse_fork_tools get_depots_infos())
        2. Steam Store API via sff.steam_store module — fallback; individual
           requests per DLC ID, no URL-encoding issues.
        """
        # --- Source 1: SteamCMD API (GBE/GSE-identical two-pass DLC collection) ---
        try:
            log(f"  DLC: trying SteamCMD API for {app_id}...")
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{STEAMCMD_API_URL}/{app_id}")
                resp.raise_for_status()
                data = resp.json()
            data_raw = data.get("data", {}).get(str(app_id), {})
            dlc_ids = set()
            # Pass A: extended.listofdlc (same as GBE/GSE Source 1)
            dlc_str = data_raw.get("extended", {}).get("listofdlc", "")
            if dlc_str:
                for d in dlc_str.split(","):
                    d = d.strip()
                    if d.isdigit():
                        dlc_ids.add(int(d))
            # Pass B: depots[*].dlcappid (same as GBE/GSE Source 2)
            for dep_key, depot_info in data_raw.get("depots", {}).items():
                if isinstance(depot_info, dict) and "dlcappid" in depot_info:
                    try:
                        dlc_ids.add(int(depot_info["dlcappid"]))
                    except (ValueError, TypeError):
                        pass
            if dlc_ids:
                log(f"  DLC: SteamCMD found {len(dlc_ids)} IDs (listofdlc+depots) — fetching names...")
                names = get_dlc_names_from_store(list(dlc_ids))
                return {str(k): v for k, v in names.items()}
            else:
                log(f"  DLC: SteamCMD API returned no DLC IDs for {app_id}")
        except Exception as e:
            logger.debug("SteamCMD DLC fetch failed for %s: %s", app_id, e)
            log(f"  DLC: SteamCMD API failed ({e})")
        # --- Source 2: Steam Store API (sff.steam_store — same as download pipeline) ---
        try:
            log(f"  DLC: trying Steam Store API for {app_id}...")
            result = get_dlc_list_from_store(app_id)
            if result:
                _, dlc_ids = result
                if dlc_ids:
                    log(f"  DLC: Steam Store found {len(dlc_ids)} IDs — fetching names...")
                    names = get_dlc_names_from_store(dlc_ids)
                    return {str(k): v for k, v in names.items()}
                else:
                    log(f"  DLC: Steam Store returned empty DLC list for {app_id}")
            else:
                log(f"  DLC: Steam Store returned no data for {app_id}")
        except Exception as e:
            logger.debug("Steam Store DLC fetch failed for %s: %s", app_id, e)
            log(f"  DLC: Steam Store API failed ({e})")
        return {}
