"""Shared utilities for Steam DLL discovery (used by SmokeAPI, CreamAPI, Koaloader)."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DLL_32_NAME = "steam_api.dll"
DLL_64_NAME = "steam_api64.dll"


def find_steam_api_dll(
    game_dir: Path, dll_name: str, *, exclude_backup: bool = True
) -> Optional[Path]:
    dll_path = game_dir / dll_name
    if dll_path.exists() and (not exclude_backup or not dll_path.stem.endswith("_o")):
        return dll_path
    for found in game_dir.rglob(dll_name):
        if exclude_backup and found.stem.endswith("_o"):
            continue
        return found
    return None


def detect_steam_architecture(game_dir: Path, backup_suffix: str = "_o") -> Optional[str]:
    # Check originals first
    if (game_dir / DLL_64_NAME).exists():
        return "64"
    if (game_dir / DLL_32_NAME).exists():
        return "32"
    # Check backup files
    if (game_dir / f"steam_api64{backup_suffix}.dll").exists():
        return "64"
    if (game_dir / f"steam_api{backup_suffix}.dll").exists():
        return "32"
    # Search subdirectories
    for found in game_dir.rglob(DLL_64_NAME):
        if not found.stem.endswith(backup_suffix):
            logger.debug(f"Found {DLL_64_NAME} in {found.relative_to(game_dir)}")
            return "64"
    for found in game_dir.rglob(DLL_32_NAME):
        if not found.stem.endswith(backup_suffix):
            logger.debug(f"Found {DLL_32_NAME} in {found.relative_to(game_dir)}")
            return "32"
    return None


def find_all_steam_api_locations(game_dir: Path, backup_suffix: str = "_o") -> list[tuple[Path, str, str]]:
    locations: list[tuple[Path, str, str]] = []
    seen: set[tuple[Path, str]] = set()  # (path, dll_name) to allow both arches in same dir
    for dll_name in [DLL_32_NAME, DLL_64_NAME]:
        arch = "64" if dll_name == DLL_64_NAME else "32"
        for dll_path in game_dir.rglob(dll_name):
            if dll_path.stem.endswith(backup_suffix):
                continue
            parent = dll_path.parent
            key = (parent, dll_name)
            if key in seen:
                continue
            seen.add(key)
            locations.append((parent, dll_name, arch))
    # Sort: root first, then alphabetically
    def sort_key(item: tuple[Path, str, str]) -> tuple[int, str]:
        path, _, _ = item
        try:
            rel = path.relative_to(game_dir)
            depth = len(rel.parts) if str(rel) != "." else 0
        except ValueError:
            depth = 999
        return (depth, str(path))
    locations.sort(key=sort_key)
    return locations
