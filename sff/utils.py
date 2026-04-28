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
import os
import sys

from pathlib import Path


import vdf  # type: ignore


logger = logging.getLogger(__name__)


def root_folder(outside_internal = False):

    is_frozen = getattr(sys, "frozen", False)

    if is_frozen:

        if outside_internal:
            # outside_internal=True → caller wants a WRITABLE directory for user data
            # (settings.bin, debug.log, recent_files.json, exports, …).
            # On AppImage the squashfs mount is read-only, so use the directory that
            # contains the .AppImage file instead (set by the AppImage runtime).
            appimage = os.environ.get('APPIMAGE')
            if appimage:
                return Path(appimage).resolve().parent
            return Path(sys.executable).resolve().parent

        # PyInstaller 6.x places ALL bundled data in sys._MEIPASS, not next to the EXE.
        # One-file build  → _MEIPASS = %TEMP%\_MEIXXXXX\  (temporary extraction dir)
        # One-dir  build  → _MEIPASS = <exe_dir>\_internal\
        # This makes the EXE self-contained regardless of where the user places it.
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent

    else:

        # Running as Python script
        # __file__ is in sff/ subfolder, so parent.parent gets us to Maintool/
        root = Path(__file__).resolve().parent.parent
        if outside_internal:
            return root
        return root


def enter_path(

    obj,

    *paths,

    mutate = False,

    ignore_case = False,

    default = None,

):

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
