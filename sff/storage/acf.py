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

import logging
from enum import IntFlag
from pathlib import Path
from typing import Optional

from sff.storage.vdf import get_steam_libs, vdf_load
from sff.utils import enter_path

logger = logging.getLogger(__name__)


class AppState(IntFlag):
    StateInvalid = 0
    StateDownloading = 1048576
    StateUninstalled = 1
    StateUpdateRequired = 2
    StateFullyInstalled = 4
    StateEncrypted = 8
    StateLocked = 16
    StateFilesMissing = 32
    StateAppRunning = 64
    StateFilesCorrupt = 128
    StateUpdateRunning = 256
    StateUpdatePaused = 512
    StateUpdateStarted = 1024
    StateUninstalling = 2048
    StateBackupRunning = 4096
    StateReconfiguring = 65536
    StateValidating = 131072
    StateAddingFiles = 262144
    StatePreallocating = 524288
    StateStaging = 2097152
    StateCommitting = 4194304
    StateUpdateStopping = 8388608
    StateReserved1 = 16777216
    StateReserved2 = 33554432


class ACFParser:
    def __init__(self, acf):
        self.data = vdf_load(acf)
        self._cached_name: Optional[str] = None
        self._cached_id: Optional[int] = None
        self._cached_state: Optional[AppState] = None

    @property
    def name(self):
        if self._cached_name is None:
            self._cached_name = enter_path(self.data, "AppState", "name", default=None)
        return self._cached_name

    @property
    def id(self):
        if self._cached_id is None:
            raw = enter_path(self.data, "AppState", "appid", default=None)
            if raw and raw.isdigit():
                self._cached_id = int(raw)
        return self._cached_id

    @property
    def state(self):
        if self._cached_state is None:
            raw = enter_path(self.data, "AppState", "StateFlags", default=None)
            self._cached_state = AppState(int(raw)) if raw and raw.isdigit() else None
        return self._cached_state

    @property
    def install_dir(self):
        raw = enter_path(self.data, "AppState", "installdir", default=None)
        return raw if raw else ""

    def needs_update(self):
        s = self.state
        return bool(s and AppState.StateUpdateRequired in s)

    def get_mounted_depots(self) -> dict:
        return enter_path(self.data, "AppState", "MountedDepots", default={})


def _candidate_libraries(steam_path):
    libs = []
    try:
        libs = get_steam_libs(steam_path)
    except Exception as e:
        logger.debug("get_steam_libs failed: %s", e)
    return libs or [steam_path]


def _appmanifest_paths(steam_path, app_id):
    for lib in _candidate_libraries(steam_path):
        yield lib, lib / "steamapps" / f"appmanifest_{app_id}.acf"


def find_and_parse_acf(steam_path, app_id):
    for _, acf_path in _appmanifest_paths(steam_path, app_id):
        try:
            if not acf_path.exists():
                continue
            return ACFParser(acf_path), acf_path
        except OSError:
            continue
        except Exception as e:
            logger.debug("ACF parse failed for %s: %s", acf_path, e)
    return None, None


def get_app_name_from_acf(steam_path, app_id):
    """
    Get game name from local ACF files only (no Steam login/API).
    Used by remove-game menu so the list never blocks on "Logging in anonymously...".
    ACF first; store page is used as fallback for uninstalled games.
    """
    for _, acf_path in _appmanifest_paths(steam_path, app_id):
        if acf_path.exists():
            try:
                parser = ACFParser(acf_path)
                if parser.name:
                    return parser.name
            except Exception as e:
                logger.debug("ACF parse failed for %s: %s", acf_path, e)
    return str(app_id)
