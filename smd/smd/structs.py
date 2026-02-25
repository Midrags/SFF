"""Aliases, Enums, NamedTuples, etc go here"""

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Literal, NamedTuple, NewType, Optional, Union

from smd.utils import root_folder


class LuaChoice(Enum):
    ADD_LUA = "Add a .lua file"
    SELECT_SAVED_LUA = "Choose from saved .lua files"
    AUTO_DOWNLOAD = "Automatically download a .lua file"


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
    DLC_CHECK = "Check DLC status of a game"
    MANAGE_DLC_UNLOCKERS = "DLC Unlockers (CreamInstaller)"
    CRACK_GAME = "Crack a game (gbe_fork)"
    REMOVE_DRM = "Remove SteamStub DRM (Steamless)"
    DL_USER_GAME_STATS = "Download UserGameStatsSchema (achievements w/o gbe_fork)"
    MULTIPLAYER_FIX = "Apply multiplayer fix (online-fix.me)"
    OFFLINE_FIX = "Offline Mode Fix"
    if sys.platform == "win32":
        MANAGE_APPLIST = "Manage AppList IDs"
        REMOVE_GAME = "Remove a game from library (stplug-in)"
    elif sys.platform == "linux":
        MANAGE_APPLIST = "Manage SLSSteam IDs"
    else:
        MANAGE_APPLIST = "Manage injected IDs"
    ANALYTICS = "View analytics dashboard"
    CHECK_UPDATES = "Check for updates"
    INSTALL_MENU = "Install/Uninstall Context Menu"
    SYNC_LUA_TO_STEAM = "Sync saved LUAs to Steam (work without DLLInjector)"
    SETTINGS = "Settings"
    EXIT = "Exit"


GameSpecificChoices = Literal[
    MainMenu.CRACK_GAME,
    MainMenu.REMOVE_DRM,
    MainMenu.DL_USER_GAME_STATS,
    MainMenu.DLC_CHECK,
    MainMenu.DL_WORKSHOP_ITEM,
    MainMenu.MULTIPLAYER_FIX,
    MainMenu.MANAGE_DLC_UNLOCKERS
]

GAME_SPECIFIC_CHOICES = (
    MainMenu.CRACK_GAME,
    MainMenu.REMOVE_DRM,
    MainMenu.DL_USER_GAME_STATS,
    MainMenu.DLC_CHECK,
    MainMenu.DL_WORKSHOP_ITEM,
    MainMenu.MULTIPLAYER_FIX,
    MainMenu.MANAGE_DLC_UNLOCKERS
)


class AppListChoice(Enum):
    ADD = "Add IDs"
    DELETE = "View/Delete IDs"


class LuaEndpoint(Enum):
    OUREVERYDAY = "oureveryday (quick but could be limited)"
    MORRENUS = "Morrenus (more stuff, needs API key, has a daily limit)"


class MainReturnCode(Enum):
    LOOP = auto()
    LOOP_NO_PROMPT = auto()
    EXIT = auto()


class GreenLumaVersions(Enum):
    """These are the keynames in HKCU\\SOFTWARE\\"""

    GLR = "GLR"
    GL2020 = "GL2020"
    GL2024 = "GL2024"
    GL2025 = "GL2025"

    def __str__(self):
        return self.value


class SettingCustomTypes(Enum):
    DIR = auto()
    FILE = auto()


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
    MORRENUS_KEY = SettingItem("morrenus_key", "Morrenus API Key", True, str)
    STEAM_PATH = SettingItem(
        "steam_path", "Steam Installation Path", False, SettingCustomTypes.DIR
    )
    STEAM_USER = SettingItem("steam_user", "Steam Username", False, str)
    STEAM_PASS = SettingItem("steam_pass", "Steam Password", True, str)
    STEAM32_ID = SettingItem("steam32_id", "Steam32 ID", False, str)
    GL_VERSION = SettingItem(
        "greenluma_version", "GreenLuma Version", False, list(GreenLumaVersions)
    )
    APPLIST_FOLDER = SettingItem(
        "applist_folder", "GreenLuma AppList Folder", False, SettingCustomTypes.DIR
    )
    SLS_CONFIG_LOCATION = SettingItem(
        "sls_config_loc",
        "SLSSteam Config File Location",
        False,
        SettingCustomTypes.FILE,
    )
    TRACK_GREENLUMA_ACH = SettingItem(
        "gl_track_ach", "Track Achievements via Greenluma", False, bool
    )
    STEAM_WEB_API_KEY = SettingItem("steam_web_api_key", "Steam Web API Key", True, str)
    PLAY_MUSIC = SettingItem("play_music", "Play Music", False, bool)
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
    USE_KOALOADER_PROXY = SettingItem("use_koaloader_proxy", "Use Koaloader Proxy Mode (optional)", False, bool)
    APPLIST_ID_LIMIT = SettingItem("applist_id_limit", "AppList ID Limit (0 = unlimited)", False, str)

    @property
    def key_name(self) -> str:
        "The key name of the setting (used in the savefile)"
        return self.value.key_name

    @property
    def clean_name(self) -> str:
        "The name of the setting as displayed in the Settings menu"
        return self.value.clean_name

    @property
    def hidden(self) -> bool:
        "Whether the item is hidden (e.g. sensitive info)"
        return self.value.hidden

    @property
    def type(self) -> SettingType:
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


class GenEmuMode(Enum):
    USER_GAME_STATS = auto()
    STEAM_SETTINGS = auto()
    ALL = auto()  # idk why i have this, it's there if i ever need it


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
    depots: list[int] = field(default_factory=list[int])
    "(Optional) A list of Depot IDs under this app"


OrganizedAppIDs = dict[int, AppIDInfo]
"A dict of IDs where Depot IDs are organized inside their parent App IDs"


class AppListPathAndID(NamedTuple):
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


NamedIDs = NewType("NamedIDs", dict[str, str])
"A dict of App IDs mapped to game names"

ProductInfo = NewType("ProductInfo", dict[str, dict[Any, Any]])
"The dict returned by get_product_info"

DepotManifestMap = NewType("DepotManifestMap", dict[str, str])
"Depot IDs mapped to Manifest IDs"


class MidiFiles(Enum):
    MIDI_PLAYER_DLL = root_folder() / "c/midi_player_lib.dll"
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
