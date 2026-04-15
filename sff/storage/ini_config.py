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

from typing import Callable
from configupdater import ConfigUpdater

from pathlib import Path


def edit_ini_option(
    ini_file: Path, section: str, option: str, converter: Callable[[str], str]
):
    conf = ConfigUpdater()
    conf.read(ini_file)  # pyright: ignore[reportUnknownMemberType]

    old_val = conf[section][option].value
    if old_val is None:
        return

    new_val = converter(old_val)

    conf[section][option].value = new_val

    conf.update_file()
    return new_val
