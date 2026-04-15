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

"""DLC Unlockers module for alternative DLC unlock methods

Provides CreamInstaller-compatible DLC unlocker implementations for Steam and Ubisoft games.
Includes validation, error handling, and comprehensive testing.
"""

from sff.dlc_unlockers.base import Platform, UnlockerBase, UnlockerType
from sff.dlc_unlockers.creamapi import CreamAPIUnlocker
from sff.dlc_unlockers.downloader import GitHubReleaseDownloader
from sff.dlc_unlockers.koaloader import KoaloaderUnlocker
from sff.dlc_unlockers.manager import UnlockerManager
from sff.dlc_unlockers.smokeapi import SmokeAPIUnlocker
from sff.dlc_unlockers.steam_dll_utils import (
    detect_steam_architecture,
    find_all_steam_api_locations,
    find_steam_api_dll,
)
from sff.dlc_unlockers.uplay_r1 import UplayR1Unlocker
from sff.dlc_unlockers.uplay_r2 import UplayR2Unlocker
from sff.dlc_unlockers.validation import (
    check_disk_space,
    check_file_in_use,
    validate_app_id,
    validate_dlc_ids,
    validate_dll_file,
    validate_game_directory,
    validate_write_permissions,
)

__all__ = [
    # Core classes
    "UnlockerBase",
    "UnlockerType",
    "Platform",
    "UnlockerManager",
    # Unlocker implementations
    "SmokeAPIUnlocker",
    "CreamAPIUnlocker",
    "KoaloaderUnlocker",
    "UplayR1Unlocker",
    "UplayR2Unlocker",
    # Utilities
    "GitHubReleaseDownloader",
    # Steam DLL utilities
    "find_steam_api_dll",
    "detect_steam_architecture",
    "find_all_steam_api_locations",
    # Validation utilities
    "validate_game_directory",
    "validate_write_permissions",
    "validate_app_id",
    "validate_dlc_ids",
    "validate_dll_file",
    "check_disk_space",
    "check_file_in_use",
]
