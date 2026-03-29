"""
Steam Tools–style compatibility: install LUAs and manifests into Steam's config
so games and DLCs work with or without GreenLuma's DLLInjector.

- LUAs: Steam\\config\\stplug-in\\{app_id}.lua (Steam Tools / LuaTools location)
- Manifests: Steam\\depotcache (primary) and Steam\\config\\depotcache (alternate)
- Decryption keys: already in config.vdf via ConfigVDFWriter
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

STPLUGIN_DIR = "stplug-in"
CONFIG_DEPOTCACHE_SUBDIR = ("config", "depotcache")


def install_lua_to_steam(steam_path: Path, app_id: str, lua_source_path: Path) -> bool:
    if not lua_source_path.exists():
        logger.debug("LUA source not found: %s", lua_source_path)
        return False
    dest_dir = steam_path / "config" / STPLUGIN_DIR
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{app_id}.lua"
        shutil.copy2(lua_source_path, dest_file)
        logger.info("Installed LUA to Steam config: %s", dest_file)
        return True
    except OSError as e:
        logger.warning("Could not install LUA to Steam config: %s", e)
        return False


def sync_manifest_to_config_depotcache(steam_path: Path, manifest_path: Path) -> bool:
    if not manifest_path.exists():
        return False
    try:
        config_depot = steam_path.joinpath(*CONFIG_DEPOTCACHE_SUBDIR)
        config_depot.mkdir(parents=True, exist_ok=True)
        dest = config_depot / manifest_path.name
        if dest != manifest_path:
            shutil.copy2(manifest_path, dest)
            logger.debug("Synced manifest to config/depotcache: %s", dest.name)
        return True
    except OSError as e:
        logger.debug("Could not sync manifest to config/depotcache: %s", e)
        return False


def remove_lua_from_steam(steam_path: Path, app_id: str | int) -> bool:
    dest_dir = steam_path / "config" / STPLUGIN_DIR
    dest_file = dest_dir / f"{app_id}.lua"
    try:
        if dest_file.exists():
            dest_file.unlink()
            logger.info("Removed LUA from Steam config: %s", dest_file)
        return True
    except OSError as e:
        logger.warning("Could not remove LUA from Steam config: %s", e)
        return False
