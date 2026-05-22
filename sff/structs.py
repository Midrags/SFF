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

"""Aliases, Enums, NamedTuples, etc go here"""

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from sff.utils import root_folder
from typing import Any, Literal, NamedTuple, NewType, Optional, Union


class LuaChoice(Enum):
    AUTO_DOWNLOAD = "Download .lua from server"
    SELECT_SAVED_LUA = "Choose from saved .lua files"
    ADD_LUA = "Import your own .lua / .zip file"


class LuaChoiceReturnCode(Enum):
    GO_BACK = auto()
    "Exit and go back to the LuaChoice selection screen"
    LOOP = auto()
    "Doesn't actually get read, but basically retry if chosen lua method fails"


class MainMenu(Enum):
    MANAGE_LUA = "Process a .lua file"
    RECENT_FILES = "Process recent .lua file"
    UPDATE_ALL_MANIFESTS = "Update manifests for all outdated games"
    SCAN_LIBRARY = "Scan game library"
    if sys.platform == "win32":
        DL_MANIFEST_ONLY = "Download manifests ONLY from a .lua file"
    else:
        DL_MANIFEST_ONLY = "Download manifests"
    DL_WORKSHOP_ITEM = "Download workshop item manifest"
    CHECK_MOD_UPDATES = "Check for mod updates"
    DLC_CHECK = "Check DLC status of a game"
    MANAGE_DLC_UNLOCKERS = "DLC Unlockers (CreamInstaller)"
    CRACK_GAME = "Crack a game (gbe_fork)"
    REMOVE_DRM = "Remove SteamStub DRM (Steamless)"
    DL_USER_GAME_STATS = "Download UserGameStatsSchema (achievements w/o gbe_fork)"
    MULTIPLAYER_FIX = "Apply multiplayer fix (online-fix.me)"
    CRACK_FIX = "Fixes & Bypasses"
    HV_FIX = "HyperVisor bypasses (HVAuto)"
    if sys.platform == "win32":
        MANAGE_INJECTION = "Manage Injected IDs"
        REMOVE_GAME = "Remove a game from library (stplug-in)"
    elif sys.platform == "linux":
        MANAGE_INJECTION = "Manage SLSSteam IDs"
    else:
        MANAGE_INJECTION = "Manage injected IDs"
    if sys.platform == "linux":
        LINUX_SETUP = "Set up Linux tools (SLSsteam + .NET 9)"
        LINUX_DOWNLOAD = "Download a game (Linux)"
        LINUX_ACHIEVEMENTS = "Generate achievements (SLScheevo)"
    ANALYTICS = "View analytics dashboard"
    CHECK_UPDATES = "Check for updates"
    INSTALL_MENU = "Install/Uninstall Context Menu"
    STEAM_AUTO = "SteamAutoCrack"
    SETTINGS = "Settings"
    EXIT = "Exit"


GameSpecificChoices = Literal[
    MainMenu.CRACK_GAME,
    MainMenu.REMOVE_DRM,
    MainMenu.DL_USER_GAME_STATS,
    MainMenu.DLC_CHECK,
    MainMenu.DL_WORKSHOP_ITEM,
    MainMenu.CHECK_MOD_UPDATES,
    MainMenu.MULTIPLAYER_FIX,
    MainMenu.CRACK_FIX,
    MainMenu.HV_FIX,
    MainMenu.MANAGE_DLC_UNLOCKERS
]

GAME_SPECIFIC_CHOICES = (
    MainMenu.CRACK_GAME,
    MainMenu.REMOVE_DRM,
    MainMenu.DL_USER_GAME_STATS,
    MainMenu.DLC_CHECK,
    MainMenu.DL_WORKSHOP_ITEM,
    MainMenu.CHECK_MOD_UPDATES,
    MainMenu.MULTIPLAYER_FIX,
    MainMenu.CRACK_FIX,
    MainMenu.HV_FIX,
    MainMenu.MANAGE_DLC_UNLOCKERS
)


class InjectionChoice(Enum):
    ADD = "Add IDs"
    DELETE = "View/Delete IDs"
    PROFILES = "Injection Profiles (create, switch, save)"


class InjectionProfileChoice(Enum):
    CREATE = "Create profile"
    SWITCH = "Switch to profile"
    SAVE = "Save current profile"
    MERGE = "Merge another profile into a profile"
    DELETE = "Delete profile"
    RENAME = "Rename profile"


class LuaEndpoint(Enum):
    OUREVERYDAY = "oureveryday (quick but could be limited)"
    HUBCAP = "Hubcap Manifest (more stuff, needs API key, has a daily limit)"
    RYUU = "Ryuu Generator (needs API key)"


class MainReturnCode(Enum):
    LOOP = auto()
    LOOP_NO_PROMPT = auto()
    EXIT = auto()


class SettingCustomTypes(Enum):
    DIR = auto()
    FILE = auto()


class SupportedLanguages(Enum):
    EN = "en"
    PT = "pt"
    DE = "de"
    ES = "es"
    PL = "pl"
    RU = "ru"
    AR = "ar"
    AUTO = "Auto"

SettingType = Union[type, list[Enum], SettingCustomTypes]


class SettingItem(NamedTuple):
    key_name: str
    "The key name of the setting (used in the savefile)"
    clean_name: str
    "The name of the setting as displayed in the Settings menu"
    hidden: bool
    "Whether the item is hidden (e.g. sensitive info)"
    type: SettingType
    "Type of the setting"


# Note: values are only obtained through get_setting() in utils.py
class Settings(Enum):
    ADVANCED_MODE = SettingItem("advanced_mode", "Advanced Mode", False, bool)
    HUBCAP_KEY = SettingItem("morrenus_key", "Hubcap API Key", True, str)
    RYUU_KEY = SettingItem("ryuu_key", "Ryuu API Key", True, str)
    STEAM_PATH = SettingItem(
        "steam_path", "Steam Installation Path", False, SettingCustomTypes.DIR
    )
    STEAM_USER = SettingItem("steam_user", "Steam Username", False, str)
    STEAM_PASS = SettingItem("steam_pass", "Steam Password", True, str)
    STEAM32_ID = SettingItem("steam32_id", "Steam32 ID", False, str)
    SLS_CONFIG_LOCATION = SettingItem(
        "sls_config_loc",
        "SLSSteam Config File Location",
        False,
        SettingCustomTypes.FILE,
    )
    STEAM_WEB_API_KEY = SettingItem("steam_web_api_key", "Steam Web API Key", True, str)
    PLAY_MUSIC = SettingItem("play_music", "Play Music", False, bool)
    THEME = SettingItem("theme", "Theme", False, str)
    ONLINE_FIX_USER = SettingItem("online_fix_user", "Online-fix.me Username", False, str)
    ONLINE_FIX_PASS = SettingItem("online_fix_pass", "Online-fix.me Password", True, str)
    PARALLEL_DOWNLOADS = SettingItem("parallel_downloads", "Parallel Download Workers", False, str)
    BACKUP_RETENTION = SettingItem("backup_retention", "Backup Retention Count", False, str)
    ENABLE_NOTIFICATIONS = SettingItem("enable_notifications", "Enable Desktop Notifications", False, bool)
    USE_PARALLEL_DOWNLOADS = SettingItem("use_parallel_downloads", "Use Parallel Downloads", False, bool)
    ACTIVE_UNLOCKER_PER_GAME = SettingItem("active_unlocker_per_game", "Active DLC Unlocker Per Game", False, dict)
    DLC_UNLOCKER_CACHE_DIR = SettingItem("dlc_unlocker_cache", "DLC Unlocker Cache Directory", False, str)
    # DLC Unlocker mode (CreamInstaller-compatible)
    USE_SMOKEAPI = SettingItem("use_smokeapi", "Prefer SmokeAPI over CreamAPI (Steam)", False, bool)
    HIDE_STORE_IMAGES = SettingItem("hide_store_images", "Hide Store Images", False, bool)
    USE_MANIFEST_PINS = SettingItem("use_manifest_pins", "Use Pinned Manifest Versions from Lua", False, bool)
    MANIFEST_PINS_ASKED = SettingItem("manifest_pins_asked", "Manifest Pin Prompt Shown (managed automatically)", False, bool)

    MANIFESTHUB_API_KEY = SettingItem("manifesthub_api_key", "ManifestHub API Key (manifesthub1.filegear-sg.me, 24h)", True, str)
    MANIFESTHUB_KEY_EXPIRY = SettingItem("manifesthub_key_expiry", "ManifestHub Key Expiry (UTC epoch, managed automatically)", False, str)
    LANGUAGE = SettingItem("language", "Language (Requires Restart)", False, list(SupportedLanguages))
    MANIFEST_UPDATE_EXCLUDES = SettingItem("manifest_update_excludes", "Manifest Update Excluded Games", False, str)
    HV_FIRST_USE_WARNED = SettingItem("hv_first_use_warned", "HyperVisor First Use Warning Shown", False, bool)
    SAVE_WATCHER_INTERVAL = SettingItem("save_watcher_interval", "Background Save Watcher Interval (minutes, 0=off)", False, str)
    LAST_BACKUP_PROVIDER_CONFIG = SettingItem("last_backup_provider_config", "Last Cloud Save Provider Config (managed automatically)", False, str)
    CLOUD_PROVIDER = SettingItem("cloud_provider", "Cloud Save Provider", False, str)
    CLOUD_RCLONE_EXE = SettingItem("cloud_rclone_exe", "Cloud Save rclone Executable", False, str)
    CLOUD_RCLONE_REMOTE = SettingItem("cloud_rclone_remote", "Cloud Save rclone Remote", False, str)

    @property
    def key_name(self):
        "The key name of the setting (used in the savefile)"
        return self.value.key_name

    @property
    def clean_name(self):
        "The name of the setting as displayed in the Settings menu"
        return self.value.clean_name

    @property
    def hidden(self):
        "Whether the item is hidden (e.g. sensitive info)"
        return self.value.hidden

    @property
    def type(self):
        return self.value.type


class SettingOperations(Enum):
    EDIT = "Edit"
    DELETE = "Delete"


class SettingsManagementOptions(Enum):
    EDIT_SETTINGS = "Edit Settings"
    EXPORT_SETTINGS = "Export Settings to JSON"
    IMPORT_SETTINGS = "Import Settings from JSON"
    BACK = "Back to Main Menu"


class LoggedInUser(NamedTuple):
    """A user in loginusers.vdf"""

    steam64_id: str
    persona_name: str
    wants_offline_mode: str
    "Either 0 or 1 (str)"


class LuaResult(NamedTuple):
    path: Optional[Path]
    "The lua file's path if it exists"
    contents: Optional[str]
    "The string contents of the lua file"
    switch_choice: Union["LuaChoice", "LuaChoiceReturnCode"]
    "A LuaChoice to switch to."
    endpoint: Optional["LuaEndpoint"] = None
    "The LuaEndpoint used to download this lua, if applicable"


class GenEmuMode(Enum):
    USER_GAME_STATS = auto()
    STEAM_SETTINGS = auto()
    ALL = auto()  # Reserved for future use


class DepotOrAppID(NamedTuple):
    name: str
    "Name of the app"
    id: int
    "The App/Depot ID"
    parent_id: Optional[int]
    "The parent App ID (if it's a depot)"


@dataclass
class AppIDInfo:
    exists: bool
    """Whether this App ID exists in AppList
    (Sometimes a Depot ID is inside the folder but without an App ID)"""
    name: str
    "Name of the app"
    depots: list = field(default_factory=list)
    "(Optional) A list of Depot IDs under this app"


OrganizedAppIDs = dict[int, AppIDInfo]
"A dict of IDs where Depot IDs are organized inside their parent App IDs"


class InjectionPathAndID(NamedTuple):
    path: Path
    app_id: int


@dataclass
class DepotKeyPair:
    """A depot and its decryption key"""

    depot_id: str
    "Depot ID"
    decryption_key: str
    "Decryption Key of the Depot. Can be blank if it's not a depot"


@dataclass
class RawLua:
    path: Path
    "can be either a lua file or ZIP file"
    contents: str
    "content of the lua file"


@dataclass
class LuaParsedInfo(RawLua):
    app_id: str
    "The base app ID"
    depots: list[DepotKeyPair]
    manifest_overrides: dict = field(default_factory=dict)
    "depot_id -> manifest_gid pins from setManifestid() Lua calls"


NamedIDs = NewType("NamedIDs", dict[str, str])
"A dict of App IDs mapped to game names"

ProductInfo = NewType("ProductInfo", dict[str, dict[Any, Any]])
"The dict returned by get_product_info"

DepotManifestMap = NewType("DepotManifestMap", dict[str, str])
"Depot IDs mapped to Manifest IDs"


_midi_lib_ext = "dll" if sys.platform == "win32" else "so"


class MidiFiles(Enum):
    MIDI_PLAYER_DLL = root_folder() / f"c/midi_player_lib.{_midi_lib_ext}"
    SOUNDFONT = root_folder() / "c/Extended_Super_Mario_64_Soundfont.sf2"
    MIDI = root_folder() / "c/th105_broken_moon_redpaper_.mid"


class ManifestGetModes(Enum):
    AUTO = "Auto"
    MANUAL = "Manual"


class DLCTypes(Enum):
    DEPOT = "DOWNLOAD REQUIRED"
    NOT_DEPOT = "PRE-INSTALLED"
    UNRELEASED = "UNRELEASED"


class ContextMenuOptions(Enum):
    INSTALL = "Install"
    UNINSTALL = "Uninstall"


class ReleaseType(Enum):
    PRERELEASE = "Pre-release (Buggy)"
    STABLE = "Stable"


class OSType(Enum):
    WINDOWS = auto()
    LINUX = auto()
    OTHER = auto()
