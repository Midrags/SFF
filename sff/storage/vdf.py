from collections import OrderedDict
from pathlib import Path
from types import TracebackType
from typing import Any, Optional, TypeVar, overload

import vdf  # type: ignore

_DictType = TypeVar("_DictType", bound=dict[Any, Any])


def vdf_dump(vdf_file: Path, obj: dict[str, Any]):
    with vdf_file.open("w", encoding="utf-8") as f:
        vdf.dump(obj, f, pretty=True)  # type: ignore


@overload
def vdf_load(
    vdf_file: Path, mapper: type[OrderedDict[Any, Any]]
) -> OrderedDict[Any, Any]: ...


@overload
def vdf_load(vdf_file: Path, mapper: type[_DictType]) -> _DictType: ...


@overload
def vdf_load(vdf_file: Path) -> dict[Any, Any]: ...


def vdf_load(vdf_file: Path, mapper: type[_DictType] = dict) -> _DictType:
    with vdf_file.open(encoding="utf-8") as f:
        data: _DictType = vdf.load(f, mapper=mapper)  # type: ignore
    return data


class VDFLoadAndDumper:
    """For when you need to load and dump a vdf file in one line.
    Use `vdf_load` or `vdf_dump` to do just one of the two"""

    def __init__(self, path: Path):
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


def get_steam_libs(steam_path: Path):
    """Get list of Steam library paths by the user

    Args:
        steam_path (Path): Steam install path

    Returns:
        list[Path]: list of Steam library paths
    """
    lib_folders = steam_path / "config/libraryfolders.vdf"

    vdf_data = vdf_load(lib_folders)
    paths: list[Path] = []
    for library in vdf_data["libraryfolders"].values():
        try:
            if (path := Path(library["path"])).exists():
                paths.append(path)
        except Exception:
            pass
    return paths


def ensure_library_has_app(steam_path: Path, library_path: Path, app_id: str) -> bool:
    """Ensure the library is in libraryfolders.vdf and the app is registered there.
    This prevents Steam from showing PURCHASE after restart (game stays in library).

    Args:
        steam_path: Steam install path (e.g. C:\\Program Files (x86)\\Steam)
        library_path: Full path to the Steam library (e.g. K:\\SteamLibrary)
        app_id: Steam App ID as string (e.g. "268910")

    Returns:
        True if registration was updated, False otherwise
    """
    lib_folders = steam_path / "config/libraryfolders.vdf"
    if not lib_folders.exists():
        return False
    try:
        vdf_data = vdf_load(lib_folders)
        folders = vdf_data.get("libraryfolders", {})
        lib_path_str = str(library_path.resolve())
        found_key: Optional[str] = None
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
