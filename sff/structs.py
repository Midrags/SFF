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
    ZH_CN = "zh_CN"
    ZH_TW = "zh_TW"
    FR = "fr"
    IT = "it"
    JA = "ja"
    KO = "ko"
    TR = "tr"
    UK = "uk"
    VI = "vi"
    ID = "id"
    TH = "th"
    CS = "cs"
    AUTO = "Auto"

SettingType = Union[type, list[Enum], SettingCustomTypes]


class SettingItem(NamedTuple):
    storage_key: str
    "The storage-key of the setting (used in the savefile)"
    label: str
    "The name of the setting as displayed in the Settings menu"
    is_secret: bool
    "Whether the item holds sensitive info"
    value_type: SettingType
    "Type of the setting"
    group_hint: str = ""
    "Optional group label for UI organisation"

    @property
    def key_name(self):
        return self.storage_key

    @property
    def clean_name(self):
        return self.label

    @property
    def hidden(self):
        return self.is_secret

    @property
    def type(self):
        return self.value_type


# Note: values are only obtained through get_setting() in utils.py
class Settings(Enum):
    ADVANCED_MODE = SettingItem("advanced_mode", "Advanced Mode", False, bool)
    HUBCAP_KEY = SettingItem("morrenus_key", "Hubcap API Key", True, str)
    RYUU_KEY = SettingItem("ryuu_key", "Ryuu Reseller Key", True, str)
    RYUU_API_KEY = SettingItem("ryuu_api_key", "Ryuu API Key (premium)", True, str)
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
    CUSTOM_BACKGROUND_IMAGE = SettingItem("custom_background_image", "Custom UI Background Image", False, str)
    CUSTOM_ACCENT_COLOR = SettingItem("custom_accent_color", "Custom UI Accent Color", False, str)
    ONLINE_FIX_NEW_SYSTEM_SHOWN = SettingItem("online_fix_new_system_shown", "Online-Fix New System Shown", False, bool)
    PARALLEL_DOWNLOADS = SettingItem("parallel_downloads", "Parallel Download Workers", False, str)
    DOWNLOAD_CONCURRENCY = SettingItem("download_concurrency", "Max concurrent chunk downloads (8-64)", False, str)
    DEPOT_DOWNLOAD_TIMEOUT = SettingItem("depot_download_timeout", "DDMod depot timeout in minutes (0 = no limit)", False, str)
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
    # 6.2.9: Local-provider destination folder. Set via the Browse button on
    # the Cloud Saves tab next to "Local Backup Folder". Empty falls back to
    # %APPDATA%\SteaMidra\save_backups\.
    CLOUD_LOCAL_BACKUP_DEST = SettingItem(
        "cloud_local_backup_dest",
        "Local Cloud-Save Backup Folder",
        False, str,
    )
    # 6.2.4: per-game custom save paths the user added by hand. Stored as
    # JSON {"<app_id>": "<absolute path>"} so the cloud-saves "All Save
    # Locations" scan picks them up alongside emu / Steam-userdata folders.
    CLOUD_CUSTOM_SAVE_PATHS = SettingItem(
        "cloud_custom_save_paths",
        "Custom Save Paths Per Game (managed via Cloud Saves UI)",
        False, str,
    )
    CLOSE_TO_TRAY = SettingItem("close_to_tray", "Close button hides to tray (off = quit)", False, bool)
    WARN_BEFORE_BREAKING_ACHIEVEMENTS = SettingItem(
        "warn_before_breaking_achievements",
        "Warn before running actions that break Steam achievements",
        False,
        bool,
    )
    # SteamAutoCrack default mode. When set, skips the "Apply Both vs
    # Steamless Only" picker dialog and runs that mode directly. Empty
    # string means ask every time (the default behaviour). Valid values:
    # "" (ask), "full" (Goldberg + Steamless), "steamless_only".
    STEAMAUTO_DEFAULT_MODE = SettingItem(
        "steamauto_default_mode",
        "SteamAutoCrack default mode (empty = ask each time)",
        False,
        str,
    )
    # A9: startup self-update popup (default ON, toggle in Settings page)
    AUTO_UPDATE_CHECK = SettingItem("auto_update_check", "Check for updates on startup", False, bool)
    LAST_SKIPPED_VERSION = SettingItem("last_skipped_version", "Last Skipped Update Version (managed automatically)", False, str)
    # A12: Bulk Import Queue mode. "process_immediately" starts the drain
    # as soon as files are enqueued; "collect_then_confirm" waits for the
    # user to confirm before processing. Single-file imports never see
    # this setting.
    BULK_IMPORT_MODE = SettingItem("bulk_import_mode", "Bulk Import Mode", False, str)
    # A15: back up depotcache manifests so a Steam uninstall does not nuke
    # the work SteaMidra registered. Default ON; the off-switch disables
    # backup, watcher, and restore in lockstep.
    MANIFEST_PRESERVE = SettingItem("manifest_preserve", "Preserve manifests when Steam uninstalls a game (recommended)", False, bool)
    # A17: widen the Store list filter to {game, application} so software
    # titles surface alongside games. Default ON; an explicit False clamps
    # the list back to type "game" only and matches pre-A17 behavior.
    STORE_SHOW_SOFTWARE = SettingItem("store_show_software", "Show software in Store", False, bool)
    STORE_BLOCK_NSFW = SettingItem("store_block_nsfw", "Block NSFW content in Store", False, bool)
    LIVE_LOG_MAX_LINES = SettingItem("live_log_max_lines", "Live Log Line Limit", False, str)
    # LumaCore version tracking. Both fields are managed by sff.lumacore_setup
    # and never surface in the Settings UI directly.
    LUMACORE_INSTALLED_VERSION = SettingItem(
        "lumacore_installed_version",
        "LumaCore Installed Version (managed automatically)",
        False,
        str,
    )
    LUMACORE_LATEST_VERSION = SettingItem(
        "lumacore_latest_version",
        "LumaCore Latest Known Version (managed automatically)",
        False,
        str,
    )
    LUMACORE_LAST_CHECK = SettingItem(
        "lumacore_last_check",
        "LumaCore Last Update Check (UTC epoch, managed automatically)",
        False,
        str,
    )
    # DarkH2o pattern. When ON, SteaMidra drops a tiny override .lua into
    # <Steam>\config\stplug-in\ that wraps setManifestid so games render
    # the "Update available" prompt instead of silently swallowing the
    # newer manifest id Steam pushes. The .lua file does not move on its
    # own; the toggle controls when it lands and when it gets cleaned up.
    SHOW_UPDATE_PROMPTS = SettingItem(
        "show_update_prompts",
        "Show in-Steam 'Update available' prompts on installed games",
        False,
        bool,
    )
    # 6.2.5: per-game and global update-available toggle. The
    # interval is stored as a string so the existing settings UI
    # text path handles edits the same way SAVE_WATCHER_INTERVAL
    # does. Defaults are applied at read time (False / 60 / "{}")
    # so users have to opt in to background CM polling instead of
    # getting hit with a periodic appdetails / Login Anonymous burst
    # the moment SteaMidra launches.
    GLOBAL_UPDATE_CHECK = SettingItem(
        "global_update_check",
        "Check for game updates (global default)",
        False,
        bool,
    )
    UPDATE_CHECK_INTERVAL_MIN = SettingItem(
        "update_check_interval_min",
        "Minutes between background update checks (default 60)",
        False,
        str,
    )
    UPDATE_CHECK_OVERRIDES = SettingItem(
        "update_check_overrides",
        "Per-game update check overrides (managed automatically)",
        False,
        str,
    )
    # JSON object {appid: bool}. True means SteaMidra has dropped
    # 00_LetUpdate_override.lua into that game's stplug-in directory and
    # the per-game "Show update available for this game" toggle is on.
    # Managed by the per-game context menu in main_window.py.
    GAME_UPDATE_OVERRIDE = SettingItem(
        "game_update_override",
        "Per-game LetUpdate override flags (managed automatically)",
        False,
        str,
    )
    AUTO_ENABLE_UPDATES_NEW_GAMES = SettingItem(
        "auto_enable_updates_new_games",
        "Auto-enable Steam update prompts for newly added games",
        False,
        bool,
    )
    WINDOW_GEOMETRY = SettingItem(
        "window_geometry",
        "Window geometry (managed automatically)",
        False,
        str,
    )
    USE_MODERN_UI = SettingItem(
        "use_modern_ui",
        "Use Modern Web UI",
        False,
        bool,
    )
    # Older-version browser headless mode. Default false so the browser
    # window is visible. Set true to suppress QMessageBox warnings.
    OLDER_VERSION_QUIET = SettingItem(
        "older_version_quiet",
        "Older-version browser quiet mode (no popup warnings)",
        False,
        bool,
    )
    PROVIDER_CONTRIBUTE_KEYS = SettingItem(
        "provider_contribute_keys",
        "Contribute clean provider keys every 24 hours",
        False,
        bool,
    )
    PROVIDER_ENRICH_STEAM_METADATA = SettingItem(
        "provider_enrich_steam_metadata",
        "Use Steam appinfo to fill missing provider metadata before submitting",
        False,
        bool,
    )
    PROVIDER_LAST_UPDATE_CHECK = SettingItem(
        "provider_last_update_check",
        "Provider cache last update check (managed automatically)",
        False,
        str,
    )
    PROVIDER_LAST_UPDATE_ATTEMPT = SettingItem(
        "provider_last_update_attempt",
        "Provider cache last update attempt (managed automatically)",
        False,
        str,
    )
    PROVIDER_LAST_UPDATE_SUCCESS = SettingItem(
        "provider_last_update_success",
        "Provider cache last successful update (managed automatically)",
        False,
        str,
    )
    PROVIDER_LAST_UPDATE_ERROR = SettingItem(
        "provider_last_update_error",
        "Provider cache last update error (managed automatically)",
        False,
        str,
    )

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
    token_overrides: dict = field(default_factory=dict)
    "appid -> token values from addtoken() Lua calls"


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
