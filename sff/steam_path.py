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
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from colorama import Fore, Style

from sff.prompts import prompt_dir
from sff.storage.settings import get_setting, set_setting
from sff.structs import OSType, Settings

if sys.platform == "win32":
    from sff.registry_access import find_steam_path_from_registry
else:
    find_steam_path_from_registry = lambda: None  # noqa: E731

logger = logging.getLogger(__name__)


def validate_steam_path(path):
    return path is not None and (path / "steamapps").exists()


class PathFinderStrategy(ABC):
    @abstractmethod
    def find(self):
        pass


class RegistryFinder(PathFinderStrategy):
    def find(self):
        path = find_steam_path_from_registry()
        if validate_steam_path(path):
            return path
        return None


class LinuxFinder(PathFinderStrategy):
    def find(self):
        steam_dir = (Path.home() / ".steam/root").resolve()
        if steam_dir.exists():
            return steam_dir


class UserInputFinder(PathFinderStrategy):
    def __init__(self, validator):
        self.validator = validator

    def find(self):
        print("Couldn't find your Steam path.")
        return prompt_dir(
            msg="Paste the path here (The folder that has Steam)",
            custom_check=self.validator,
            custom_msg="Make sure the folder contains the Steam application"
        )


class SettingsFinder(PathFinderStrategy):
    def __init__(self):
        self.raw_path = None
        "populated after find() is ran"

    def find(self):
        self.raw_path = get_setting(Settings.STEAM_PATH)
        if self.raw_path is not None:
            path = Path(self.raw_path)
            if validate_steam_path(path):
                return path


class SteamPathService:
    def __init__(self, finders):
        self.finders = finders

    def get_path(self):
        for finder in self.finders:
            path = finder.find()
            if path:
                self._log_success(path)
                return path
        raise FileNotFoundError("Steam path could not be resolved.")

    def _log_success(self, path):
        colorized = Fore.YELLOW + str(path.resolve()) + Style.RESET_ALL
        print(f"Your Steam path is {colorized}")


def init_steam_path(os_type):
    settings_strat = SettingsFinder()
    os_specific_finder = []
    if os_type == OSType.WINDOWS:
        os_specific_finder.append(RegistryFinder())
    elif os_type == OSType.LINUX:
        os_specific_finder.append(LinuxFinder())

    strategies = [
        settings_strat,
        *os_specific_finder,
        UserInputFinder(validator=validate_steam_path),
    ]

    service = SteamPathService(strategies)
    path = service.get_path()
    path_str = str(path.resolve())
    if path_str != settings_strat.raw_path:
        logger.debug("Updating STEAM_PATH in Settings")
        set_setting(Settings.STEAM_PATH, path_str)
    return path
