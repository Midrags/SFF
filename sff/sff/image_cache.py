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

"""
Image cache for Steam game thumbnails.

LRU disk cache with async preload, 200-item limit.
Downloads header images from Steam CDN.
"""

import os
import time
import logging
import hashlib
from pathlib import Path
from collections import OrderedDict

import httpx

logger = logging.getLogger(__name__)

# Steam CDN URL for game header images
STEAM_CDN_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

# cache settings
MAX_CACHE_SIZE = 200
CACHE_DIR_NAME = "image_cache"
TARGET_WIDTH = 280  # pixel width for thumbnails


def _get_cache_dir():
    """get the image cache directory, creating it if needed"""
    base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    cache_dir = base / "SteaMidra" / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


class ImageCache:
    """
    LRU disk cache for Steam game header images.

    Stores images at %APPDATA%/SteaMidra/image_cache/{appid}.jpg
    Evicts oldest entries when cache exceeds MAX_CACHE_SIZE items.
    """

    def __init__(self, max_size = MAX_CACHE_SIZE):
        self.max_size = max_size
        self.cache_dir = _get_cache_dir()
        # track access order for LRU eviction
        self._access_order: OrderedDict[int, float] = OrderedDict()
        self._load_existing()

    def _load_existing(self):
        """scan disk for existing cached images"""
        try:
            for f in self.cache_dir.glob("*.jpg"):
                try:
                    app_id = int(f.stem)
                    mtime = f.stat().st_mtime
                    self._access_order[app_id] = mtime
                except (ValueError, OSError):
                    continue
            # sort by modification time (oldest first)
            sorted_items = sorted(self._access_order.items(), key=lambda x: x[1])
            self._access_order = OrderedDict(sorted_items)
        except Exception as e:
            logger.warning("Failed to scan image cache: %s", e)

    def _evict_if_needed(self):
        """remove oldest entries until we're under the size limit"""
        while len(self._access_order) > self.max_size:
            oldest_id, _ = self._access_order.popitem(last=False)
            cache_path = self.cache_dir / f"{oldest_id}.jpg"
            try:
                cache_path.unlink(missing_ok=True)
                logger.debug("Evicted image cache for app %d", oldest_id)
            except OSError:
                pass

    def get_path(self, app_id):
        """
        Get the cached image path for an app.
        Returns None if not cached.
        """
        cache_path = self.cache_dir / f"{app_id}.jpg"
        if cache_path.exists():
            # move to end of LRU
            self._access_order.move_to_end(app_id)
            self._access_order[app_id] = time.time()
            return cache_path
        return None

    def has(self, app_id):
        """check if an image is cached"""
        return (self.cache_dir / f"{app_id}.jpg").exists()

    def download(self, app_id, force = False):
        """
        Download and cache a game header image.
        Returns the path to the cached file, or None on failure.
        """
        cache_path = self.cache_dir / f"{app_id}.jpg"
        if cache_path.exists() and not force:
            self._access_order.move_to_end(app_id)
            self._access_order[app_id] = time.time()
            return cache_path
        url = STEAM_CDN_URL.format(appid=app_id)
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                cache_path.write_bytes(resp.content)
                self._access_order[app_id] = time.time()
                self._access_order.move_to_end(app_id)
                self._evict_if_needed()
                logger.debug("Cached image for app %d (%d bytes)", app_id, len(resp.content))
                return cache_path
        except Exception as e:
            logger.warning("Failed to download image for app %d: %s", app_id, e)
            return None

    def download_batch(self, app_ids, max_concurrent = 5):
        """
        Download multiple images, skipping already-cached ones.
        Returns a dict of app_id -> path (or None on failure).
        """
        results = {}
        to_download = []
        for app_id in app_ids:
            existing = self.get_path(app_id)
            if existing:
                results[app_id] = existing
            else:
                to_download.append(app_id)
        # download missing ones sequentially (keep it simple)
        for app_id in to_download:
            results[app_id] = self.download(app_id)
        return results

    def clear(self):
        """wipe the entire cache"""
        try:
            for f in self.cache_dir.glob("*.jpg"):
                f.unlink(missing_ok=True)
            self._access_order.clear()
            logger.info("Image cache cleared")
        except Exception as e:
            logger.error("Failed to clear image cache: %s", e)

    @property
    def size(self):
        """number of cached images"""
        return len(self._access_order)

    @property
    def disk_usage(self):
        """total bytes used by cached images"""
        total = 0
        try:
            for f in self.cache_dir.glob("*.jpg"):
                total += f.stat().st_size
        except OSError:
            pass
        return total
