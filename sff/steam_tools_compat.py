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

"""Install LUAs and manifests into Steam's config directories.

- LUAs: Steam\\config\\stplug-in\\{app_id}.lua
- Manifests: Steam\\depotcache (primary) and Steam\\config\\depotcache (alternate)
- Decryption keys: already in config.vdf via ConfigVDFWriter
"""


import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

STPLUGIN_DIR = "stplug-in"
CONFIG_DEPOTCACHE_SUBDIR = ("config", "depotcache")


def install_lua_to_steam(steam_path, app_id, lua_source_path):
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


def sync_manifest_to_config_depotcache(steam_path, manifest_path):
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


def remove_lua_from_steam(steam_path, app_id: str | int):
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


def remove_acf_and_manifests(steam_path, app_id: str | int, mounted_depots: dict, acf_path=None):
    deleted = 0
    for depot_id, manifest_id in mounted_depots.items():
        filename = f"{depot_id}_{manifest_id}.manifest"
        for cache_dir in [
            steam_path / "depotcache",
            steam_path / "config" / "depotcache",
        ]:
            f = cache_dir / filename
            try:
                if f.exists():
                    f.unlink()
                    logger.info("Deleted manifest: %s", f)
                    deleted += 1
            except OSError as e:
                logger.warning("Could not delete manifest %s: %s", f, e)
    if acf_path is not None:
        try:
            if acf_path.exists():
                acf_path.unlink()
                logger.info("Deleted ACF: %s", acf_path)
                deleted += 1
        except OSError as e:
            logger.warning("Could not delete ACF %s: %s", acf_path, e)
    return deleted
