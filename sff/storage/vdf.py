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

from collections import OrderedDict
from pathlib import Path
from types import TracebackType

import vdf  # type: ignore
from typing import Any, Optional, TypeVar, overload

_DictType = TypeVar("_DictType", bound=dict[Any, Any])


def vdf_dump(vdf_file, obj):
    with vdf_file.open("w", encoding="utf-8") as f:
        vdf.dump(obj, f, pretty=True)  # type: ignore


@overload
def vdf_load(
    vdf_file: Path, mapper: type[OrderedDict[Any, Any]]
): ...


@overload
def vdf_load(vdf_file, mapper): ...


@overload
def vdf_load(vdf_file): ...


def vdf_load(vdf_file, mapper = dict):
    with vdf_file.open(encoding="utf-8") as f:
        data = vdf.load(f, mapper=mapper)  # type: ignore
    return data


class VDFLoadAndDumper:
    """For when you need to load and dump a vdf file in one line.
    Use `vdf_load` or `vdf_dump` to do just one of the two"""

    def __init__(self, path):
        self.path = path
        self.data = vdf.VDFDict()

    def __enter__(self):
        self.data = vdf_load(self.path, mapper=vdf.VDFDict)
        return self.data

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        exc_traceback: Optional[TracebackType],
    ):
        if exc_type is None:
            vdf_dump(self.path, self.data)


def get_steam_libs(steam_path):
    lib_folders = steam_path / "config/libraryfolders.vdf"

    vdf_data = vdf_load(lib_folders)
    paths = []
    for library in vdf_data["libraryfolders"].values():
        try:
            if (path := Path(library["path"])).exists():
                paths.append(path)
        except Exception:
            pass
    return paths


def ensure_library_has_app(steam_path, library_path, app_id):
    lib_folders = steam_path / "config/libraryfolders.vdf"
    if not lib_folders.exists():
        return False
    try:
        vdf_data = vdf_load(lib_folders)
        folders = vdf_data.get("libraryfolders", {})
        lib_path_str = str(library_path.resolve())
        found_key = None
        for key, lib in folders.items():
            if key == "contentstatsid":
                continue
            try:
                if Path(lib.get("path", "")).resolve() == Path(lib_path_str).resolve():
                    found_key = key
                    break
            except Exception:
                pass
        if found_key is None:
            # Library not in list; add it
            next_idx = 0
            for k in folders:
                if k != "contentstatsid" and str(k).isdigit():
                    next_idx = max(next_idx, int(k) + 1)
            found_key = str(next_idx)
            folders[found_key] = {"path": lib_path_str, "apps": {}}
        if "apps" not in folders[found_key]:
            folders[found_key]["apps"] = {}
        apps = folders[found_key]["apps"]
        app_id_str = str(app_id)
        if apps.get(app_id_str) != "1":
            apps[app_id_str] = "1"
            vdf_dump(lib_folders, vdf_data)
            return True
        return False
    except Exception:
        return False


def auto_fix_greenluma_offline(steam_path: Path) -> bool:
    """Auto-fix WantsOfflineMode on startup to prevent GreenLuma breakage.

    When Steam is closed with Offline Mode enabled, launching with GreenLuma
    can break Steam.  This sets WantsOfflineMode to "0" for all users.
    Returns True if a fix was applied.
    """
    login_file = steam_path / "config" / "loginusers.vdf"
    if not login_file.exists():
        return False
    try:
        data = vdf_load(login_file)
        fixed = False
        for user in data.get("users", {}).values():
            if user.get("WantsOfflineMode") == "1":
                user["WantsOfflineMode"] = "0"
                fixed = True
        if fixed:
            vdf_dump(login_file, data)
        return fixed
    except Exception:
        return False
