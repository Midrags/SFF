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
import os
import sys
from collections.abc import Callable, Iterable
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

PathProbe = Callable[[], Path | None]


def validate_steam_path(path):
    if path is None:
        return False
    try:
        return (Path(path) / "steamapps").is_dir()
    except (TypeError, OSError):
        return False


def _real_path(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _settings_probe() -> tuple[PathProbe, Callable[[], str | None]]:
    cached = {"raw": None}

    def probe() -> Path | None:
        cached["raw"] = get_setting(Settings.STEAM_PATH)
        if cached["raw"]:
            candidate = Path(cached["raw"])
            if validate_steam_path(candidate):
                return candidate
        return None

    def raw_value() -> str | None:
        return cached["raw"]

    return probe, raw_value


def _registry_probe() -> Path | None:
    candidate = find_steam_path_from_registry()
    if validate_steam_path(candidate):
        return candidate
    return None


def _linux_candidates() -> Iterable[Path]:
    home = Path.home()
    yield home / ".steam" / "steam"
    yield home / ".local" / "share" / "Steam"
    yield home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
    yield home / "snap" / "steam" / "common" / ".steam" / "steam"


def _linux_probe() -> Path | None:
    for candidate in _linux_candidates():
        if validate_steam_path(candidate):
            return _real_path(candidate)
    return None


class LinuxFinder:
    def find(self) -> Path | None:
        return _linux_probe()


def _manual_probe() -> Path | None:
    print("Couldn't find your Steam path.")
    return prompt_dir(
        msg="Paste the path here (The folder that has Steam)",
        custom_check=validate_steam_path,
        custom_msg="Make sure the folder contains the Steam application",
    )


def _platform_probes(os_type) -> list[PathProbe]:
    if os_type == OSType.WINDOWS:
        return [_registry_probe]
    if os_type == OSType.LINUX:
        return [_linux_probe]
    return []


def _first_valid_path(probes: Iterable[PathProbe]) -> Path:
    for probe in probes:
        candidate = probe()
        if validate_steam_path(candidate):
            return Path(candidate)
    raise FileNotFoundError("Steam path could not be resolved.")


def _announce_path(path: Path) -> None:
    colorized_path = Fore.YELLOW + str(path.resolve()) + Style.RESET_ALL
    print(f"Your Steam path is {colorized_path}")


def init_steam_path(os_type):
    settings_probe, previous_setting = _settings_probe()
    probes = [settings_probe, *_platform_probes(os_type), _manual_probe]

    steam_path = _first_valid_path(probes)
    _announce_path(steam_path)

    resolved = str(steam_path.resolve())
    if resolved != previous_setting():
        logger.debug("Updating STEAM_PATH in Settings")
        set_setting(Settings.STEAM_PATH, resolved)
    return steam_path
