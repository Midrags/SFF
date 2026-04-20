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
Fix Game cache — stores app info, Goldberg DLLs, and PICS data.

Mirrors Solus FixGameCacheService.cs - caches DLC lists, launch configs,
Goldberg emulator version, and parsed lua data.
"""

import os
import sys
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


def _get_cache_dir():
    """get the fix game cache directory (XDG-compliant on Linux)"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or os.path.expanduser("~"))
    else:
        base = Path.home() / ".local" / "share"
    cache_dir = base / "SteaMidra" / "fix_game_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _ensure_defender_exclusion(base / "SteaMidra")
    return cache_dir


def _ensure_defender_exclusion(path):
    """
    Attempt to add a Windows Defender exclusion for the SteaMidra data directory.
    First tries non-elevated; if that fails (needs admin), silently skips.
    A flag file prevents repeated pointless attempts in the same session.
    No-op on non-Windows or if Defender is not running.
    """
    import subprocess, sys
    if sys.platform != "win32":
        return

    flag = path / ".defender_excluded"
    if flag.exists():
        return  # already confirmed excluded in a previous run

    try:
        result = subprocess.run(
            [
                "powershell", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command",
                f"Add-MpPreference -ExclusionPath '{path}' -ErrorAction Stop",
            ],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            try:
                flag.write_text("excluded", encoding="utf-8")
            except Exception:
                pass
    except Exception:
        pass


@dataclass
class CachedAppInfo:
    """cached information about a game for the fix pipeline"""
    app_id: int
    name: str = ""
    dlc_list: dict = field(default_factory=dict)  # {dlc_id: name}
    cloud_save_paths: dict = field(default_factory=dict)  # {platform: [paths]}
    launch_configs: list = field(default_factory=list)  # [{exe, args, workdir, oslist}]
    build_id: int = 0
    depots: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class FixGameCache:
    """
    Manages the fix game cache at %APPDATA%/SteaMidra/fix_game_cache/.

    Structure:
        fix_game_cache/
        ├── goldberg/           # cached Goldberg emulator DLLs
        │   ├── version.txt     # current cached version tag
        │   ├── steam_api.dll
        │   ├── steam_api64.dll
        │   ├── steamclient.dll
        │   ├── steamclient64.dll
        │   ├── steamclient_loader_x32.exe
        │   ├── steamclient_loader_x64.exe
        │   └── ...
        ├── apps/               # per-game cached info
        │   ├── {appid}.json
        │   └── ...
        └── pics/               # cached PICS data
            ├── {appid}.json
            └── ...
    """

    def __init__(self):
        self.cache_dir = _get_cache_dir()
        self.goldberg_dir = self.cache_dir / "goldberg"
        self.apps_dir = self.cache_dir / "apps"
        self.pics_dir = self.cache_dir / "pics"
        # create subdirs
        self.goldberg_dir.mkdir(parents=True, exist_ok=True)
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.pics_dir.mkdir(parents=True, exist_ok=True)

    # --- app info cache ---

    def save_app_info(self, info):
        """save cached app info to disk"""
        path = self.apps_dir / f"{info.app_id}.json"
        try:
            path.write_text(json.dumps(info.to_dict(), indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save app info for %d: %s", info.app_id, e)

    def load_app_info(self, app_id):
        """load cached app info from disk"""
        path = self.apps_dir / f"{app_id}.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return CachedAppInfo.from_dict(data)
        except Exception as e:
            logger.warning("Failed to load app info for %d: %s", app_id, e)
        return None

    # --- goldberg version ---

    def get_goldberg_version(self):
        """get the cached Goldberg emulator version tag"""
        version_file = self.goldberg_dir / "version.txt"
        try:
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return None

    def set_goldberg_version(self, version):
        """save the current Goldberg version tag"""
        version_file = self.goldberg_dir / "version.txt"
        try:
            version_file.write_text(version.strip(), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save Goldberg version: %s", e)

    def has_goldberg_dlls(self, linux_native: bool = False):
        """check if we have the core Goldberg files cached"""
        if linux_native:
            required = ["libsteam_api.so"]
        else:
            required = ["steam_api.dll", "steam_api64.dll"]
        return all((self.goldberg_dir / name).exists() for name in required)

    def get_goldberg_dll_path(self, dll_name):
        """get path to a cached Goldberg DLL"""
        path = self.goldberg_dir / dll_name
        return path if path.exists() else None

    # --- PICS data ---

    def save_pics_data(self, app_id, data):
        """save raw PICS data for a game"""
        path = self.pics_dir / f"{app_id}.json"
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save PICS data for %d: %s", app_id, e)

    def load_pics_data(self, app_id):
        """load cached PICS data"""
        path = self.pics_dir / f"{app_id}.json"
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load PICS data for %d: %s", app_id, e)
        return None

    # --- lua parsing ---

    @staticmethod
    def parse_lua_for_cache(lua_content, app_id):
        """
        Parse lua content to extract DLC, depot, and launch info.
        This mirrors what Solus does when caching data from lua downloads.
        """
        info = CachedAppInfo(app_id=app_id)
        # try to extract DLC list from lua
        import re
        # pattern: addDLC({dlc_id}, "{name}")  or similar
        dlc_pattern = re.compile(r'["\']?(\d{4,})["\']?\s*[=:]\s*["\']([^"\']+)["\']')
        for match in dlc_pattern.finditer(lua_content):
            dlc_id = match.group(1)
            dlc_name = match.group(2)
            info.dlc_list[dlc_id] = dlc_name
        return info

    def clear(self):
        """nuke the entire cache"""
        import shutil
        try:
            for subdir in [self.apps_dir, self.pics_dir]:
                for f in subdir.glob("*.json"):
                    f.unlink(missing_ok=True)
            logger.info("Fix game cache cleared (kept Goldberg DLLs)")
        except Exception as e:
            logger.error("Failed to clear cache: %s", e)
