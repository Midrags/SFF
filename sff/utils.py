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

"""Miscellaneous stuff used across various files"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional, Union

import vdf  # type: ignore

logger = logging.getLogger(__name__)


def root_folder(outside_internal: bool = False):
    is_frozen = getattr(sys, "frozen", False)

    if is_frozen:
        if outside_internal:
            # User-writable data (settings.bin, manifests, logs) lives next to the EXE
            return Path(sys.executable).resolve().parent
        # Bundled resources (third_party, static, locales) are extracted to _MEIPASS
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Running as Python script — __file__ is in sff/, parent.parent is project root
        return Path(__file__).resolve().parent.parent


def enter_path(
    obj: Union[vdf.VDFDict, dict[Any, Any]],
    *paths: Union[int, str],
    mutate: bool = False,
    ignore_case: bool = False,
    default: Optional[Any] = None,
) -> Any:
    """
    Walks or creates nested dicts in a VDFDict/dict.
    Returns an empty dict-like if not found.
    `default` key only works when `mutate` is False.
    """
    current = obj
    for key in paths:
        if isinstance(key, int):
            try:
                current = current[key]  # pyright: ignore[reportUnknownVariableType]
            except IndexError:
                return type(current)()
            continue
        original_key = key
        if ignore_case:
            key = key.lower()

        key_map = {}
        for x in current:  # pyright: ignore[reportUnknownVariableType]
            if ignore_case and isinstance(x, str):
                key_map[x.lower()] = x
            else:
                key_map[x] = x

        if key in key_map:
            current = current[  # pyright: ignore[reportUnknownVariableType]
                key_map[key]
            ]
        else:
            if not mutate:
                return default if default else type(current)()
            # create a new key that's the same type as current
            new_node = type(current)()
            current[original_key] = new_node
            current = new_node

    return current  # pyright: ignore[reportUnknownVariableType]
