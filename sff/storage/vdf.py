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
from typing import Any, Optional, overload

import vdf  # type: ignore


def vdf_dump(vdf_file, obj):
    from pathlib import Path as _P
    import tempfile
    target = _P(vdf_file)
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    except (FileNotFoundError, PermissionError, OSError):
        return False
    try:
        with open(tmp_fd, "w", encoding="utf-8") as handle:
            vdf.dump(obj, handle, pretty=True)  # type: ignore
        _P(tmp_name).replace(target)
    except (FileNotFoundError, PermissionError, OSError):
        pass
    finally:
        try:
            _P(tmp_name).unlink(missing_ok=True)
        except Exception:
            pass


@overload
def vdf_load(vdf_file: Path, mapper: type[OrderedDict[Any, Any]]): ...


@overload
def vdf_load(vdf_file, mapper): ...


@overload
def vdf_load(vdf_file): ...


def vdf_load(vdf_file, mapper=dict):
    with Path(vdf_file).open(encoding="utf-8") as handle:
        return vdf.load(handle, mapper=mapper)  # type: ignore


class VDFLoadAndDumper:
    """Load a VDF on enter and write it back if the block succeeds."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = vdf.VDFDict()

    def __enter__(self):
        self.data = vdf_load(self.path, mapper=vdf.VDFDict)
        return self.data

    def __exit__(self, *exc_info):
        if exc_info[0] is None:
            vdf_dump(self.path, self.data)
        return None


def _libraryfolders_path(steam_path) -> Path:
    return Path(steam_path) / "config" / "libraryfolders.vdf"


def _library_table(steam_path):
    data = vdf_load(_libraryfolders_path(steam_path))
    return data, data.get("libraryfolders", {})


def _iter_real_libraries(folders):
    for key, library in folders.items():
        if key == "contentstatsid" or not isinstance(library, dict):
            continue
        yield key, library


def _existing_library_path(library):
    try:
        path = Path(library["path"])
        return path if path.exists() else None
    except (OSError, Exception):
        return None


def get_steam_libs(steam_path):
    _data, folders = _library_table(steam_path)
    paths = []
    for _key, library in _iter_real_libraries(folders):
        path = _existing_library_path(library)
        if path is not None:
            paths.append(path)
    return paths


def _same_resolved_path(left, right) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except Exception:
        return False


def _next_library_index(folders) -> str:
    highest = -1
    for key in folders:
        if str(key).isdigit():
            highest = max(highest, int(key))
    return str(highest + 1)


def _find_library_key(folders, library_path) -> str | None:
    for key, library in _iter_real_libraries(folders):
        if _same_resolved_path(library.get("path", ""), library_path):
            return str(key)
    return None


def ensure_library_has_app(steam_path, library_path, app_id):
    lib_folders = _libraryfolders_path(steam_path)
    if not lib_folders.exists():
        return False

    try:
        vdf_data, folders = _library_table(steam_path)
        lib_path_str = str(Path(library_path).resolve())
        folder_key = _find_library_key(folders, lib_path_str)
        if folder_key is None:
            folder_key = _next_library_index(folders)
            folders[folder_key] = {"path": lib_path_str, "apps": {}}

        apps = folders[folder_key].setdefault("apps", {})
        app_id_str = str(app_id)
        if apps.get(app_id_str) == "1":
            return False

        apps[app_id_str] = "1"
        vdf_dump(lib_folders, vdf_data)
        return True
    except Exception:
        return False
