"""
Steam Tools–style compatibility: install LUAs and manifests into Steam's config
so games and DLCs work with or without GreenLuma's DLLInjector.

- LUAs: Steam\\config\\stplug-in\\{app_id}.lua (Steam Tools / LuaTools location)
- Manifests: Steam\\depotcache (primary) and Steam\\config\\depotcache (alternate)
- Decryption keys: already in config.vdf via ConfigVDFWriter
"""

import logging
import shutil
from pathlib import Path


logger = logging.getLogger(__name__)

STPLUGIN_DIR = "stplug-in"
CONFIG_DEPOTCACHE_SUBDIR = ("config", "depotcache")


def install_lua_to_steam(steam_path: Path, app_id: str, lua_source_path: Path) -> bool:
    """
    Copy a LUA file into Steam's config/stplug-in so the Steam client can use it
    (Steam Tools / LuaTools style). Works with or without DLLInjector.

    Args:
        steam_path: Steam install path (e.g. C:\\Program Files (x86)\\Steam)
        app_id: App ID string (e.g. "268910")
        lua_source_path: Full path to the .lua file (e.g. saved_lua/268910.lua)

    Returns:
        True if copy succeeded or target already up to date, False on error.
    """
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
    """
    Copy a manifest from Steam/depotcache to Steam/config/depotcache so both
    locations are populated (Steam Tools uses config/depotcache in some setups).

    Args:
        steam_path: Steam install path
        manifest_path: Path to the manifest file (e.g. .../depotcache/123_456.manifest)

    Returns:
        True if copy succeeded or already present, False on error.
    """
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


def sync_all_saved_lua_to_steam(steam_path: Path, saved_lua_dir: Path) -> int:
    """
    Copy all .lua files from saved_lua into Steam config/stplug-in.
    Use this to make all previously backed-up games work without DLLInjector.

    Returns:
        Number of LUAs copied.
    """
    if not saved_lua_dir.exists():
        return 0
    count = 0
    dest_dir = steam_path / "config" / STPLUGIN_DIR
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for lua_file in saved_lua_dir.glob("*.lua"):
            app_id = lua_file.stem
            if not app_id.isdigit():
                continue
            dest_file = dest_dir / f"{app_id}.lua"
            shutil.copy2(lua_file, dest_file)
            count += 1
        if count:
            logger.info("Synced %d LUA(s) to Steam config/stplug-in", count)
    except OSError as e:
        logger.warning("Could not sync saved LUAs to Steam: %s", e)
    return count


def remove_lua_from_steam(steam_path: Path, app_id: str | int) -> bool:
    """
    Remove a game's LUA file from Steam config/stplug-in (reverse of install_lua_to_steam).
    Deletes config/stplug-in/{app_id}.lua so the game no longer appears in the library.

    Returns True if the file was removed or did not exist, False on error.
    """
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


def sync_all_manifests_to_config_depotcache(steam_path: Path) -> int:
    """
    Copy all manifests from Steam/depotcache to Steam/config/depotcache
    so both locations are populated (for Steam Tools compatibility).

    Returns:
        Number of manifest files copied.
    """
    depotcache = steam_path / "depotcache"
    config_depot = steam_path.joinpath(*CONFIG_DEPOTCACHE_SUBDIR)
    if not depotcache.exists():
        return 0
    count = 0
    try:
        config_depot.mkdir(parents=True, exist_ok=True)
        for manifest_file in depotcache.glob("*.manifest"):
            dest = config_depot / manifest_file.name
            if not dest.exists() or dest.stat().st_mtime < manifest_file.stat().st_mtime:
                shutil.copy2(manifest_file, dest)
                count += 1
        if count:
            logger.info("Synced %d manifest(s) to config/depotcache", count)
    except OSError as e:
        logger.warning("Could not sync manifests to config/depotcache: %s", e)
    return count


