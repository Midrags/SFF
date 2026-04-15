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

"""Hubcap Manifest API client — library browsing, search, downloads."""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# base URL for the manifest API
BASE_URL = "https://hubcapmanifest.com/api/v1"

# how long to cache game status responses (seconds)
STATUS_CACHE_TTL = 300  # 5 minutes, same as Hubcap Bot


@dataclass
class GameInfo:
    app_id: int
    name: str
    last_updated: str = ""
    status: str = ""
    size: int = 0


@dataclass
class LibraryPage:
    games: list = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 100

    @property
    def total_pages(self) -> int:
        if self.limit <= 0:
            return 1
        return max(1, (self.total + self.limit - 1) // self.limit)


@dataclass
class GameStatus:
    app_id: int
    status: str = "unknown"
    message: str = ""
    _cached_at: float = 0.0


class StoreApiClient:
    """Morrenus manifest API. Needs a Bearer token (smm_ key)."""

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self._status_cache: dict[int, GameStatus] = {}
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        # lazy-init so we reuse connections
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "SteaMidra/1.0",
                },
                timeout=self.timeout,
            )
        return self._client

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()

    # --- validation ---

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        return bool(api_key and api_key.strip().startswith("smm") and len(api_key.strip()) > 10)

    def test_api_key(self) -> bool:
        try:
            resp = self._get_client().get("/user/stats")
            return resp.status_code == 200
        except Exception as e:
            logger.warning("API key test failed: %s", e)
            return False

    # --- library browsing ---

    def get_library(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        sort_by: str = "updated",
    ) -> LibraryPage:
        params = {
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
        }
        if search:
            params["search"] = search

        try:
            resp = self._get_client().get("/library", params=params)
            resp.raise_for_status()
            data = resp.json()

            games = []
            for item in data.get("games", []):
                gid = item.get("game_id", item.get("appid", "0"))
                gname = item.get("game_name", item.get("name", f"App {gid}"))
                uploaded = item.get("uploaded_date", item.get("last_updated", ""))
                manifest_ok = item.get("manifest_available", False)
                games.append(GameInfo(
                    app_id=int(gid) if str(gid).isdigit() else 0,
                    name=gname,
                    last_updated=str(uploaded),
                    status="available" if manifest_ok else "",
                    size=int(item.get("manifest_size", 0) or 0),
                ))

            return LibraryPage(
                games=games,
                total=data.get("total_count", len(games)),
                offset=offset,
                limit=limit,
            )
        except Exception as e:
            logger.error("Failed to get library: %s", e)
            return LibraryPage()

    def search_library(
        self,
        query: str,
        limit: int = 50,
        search_by_appid: bool = False,
    ) -> list[GameInfo]:
        params = {
            "q": query,
            "limit": limit,
        }
        if search_by_appid:
            params["appid"] = "true"

        try:
            resp = self._get_client().get("/search", params=params)
            resp.raise_for_status()
            data = resp.json()

            results = []
            items = data.get("results", []) if isinstance(data, dict) else data
            for item in items:
                gid = item.get("game_id", item.get("appid", "0"))
                gname = item.get("game_name", item.get("name", f"App {gid}"))
                uploaded = item.get("uploaded_date", item.get("last_updated", ""))
                manifest_ok = item.get("manifest_available", False)
                results.append(GameInfo(
                    app_id=int(gid) if str(gid).isdigit() else 0,
                    name=gname,
                    last_updated=str(uploaded),
                    status="available" if manifest_ok else "",
                ))
            return results
        except Exception as e:
            logger.error("Search failed: %s", e)
            return []

    def get_all_games(self) -> list[GameInfo]:
        try:
            resp = self._get_client().get("/games")
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("games", [])
            return [
                GameInfo(
                    app_id=int(item.get("game_id", item.get("appid", 0))),
                    name=item.get("game_name", item.get("name", "")),
                )
                for item in items
            ]
        except Exception as e:
            logger.error("Failed to get all games: %s", e)
            return []

    # --- game status ---

    def get_game_status(self, app_id: int, force_refresh: bool = False) -> GameStatus:
        # cached for 5 min
        cached = self._status_cache.get(app_id)
        if cached and not force_refresh:
            if (time.time() - cached._cached_at) < STATUS_CACHE_TTL:
                return cached

        try:
            resp = self._get_client().get(f"/status/{app_id}")
            resp.raise_for_status()
            data = resp.json()

            status = GameStatus(
                app_id=app_id,
                status=data.get("status", "unknown"),
                message=data.get("message", ""),
                _cached_at=time.time(),
            )
            self._status_cache[app_id] = status
            return status
        except Exception as e:
            logger.warning("Failed to get status for %d: %s", app_id, e)
            return GameStatus(app_id=app_id, status="error", message=str(e))

    # --- downloads ---

    def get_manifest(self, app_id: int) -> Optional[bytes]:
        try:
            resp = self._get_client().get(f"/manifest/{app_id}")
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error("Failed to download manifest for %d: %s", app_id, e)
            return None

    def get_lua_content(self, app_id: int) -> Optional[str]:
        try:
            resp = self._get_client().get(f"/lua/{app_id}")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("Failed to get lua for %d: %s", app_id, e)
            return None

    def get_workshop_manifest(self, workshop_id: int) -> Optional[bytes]:
        try:
            resp = self._get_client().get(f"/generate/workshopmanifest/{workshop_id}")
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error("Failed to get workshop manifest for %d: %s", workshop_id, e)
            return None

    # --- depot helpers ---

    def get_game_depots(self, app_id: int) -> list[int]:
        """Return depot IDs for a game using the Morrenus generate/manifest list endpoint."""
        try:
            resp = self._get_client().get(f"/generate/manifest/{app_id}")
            resp.raise_for_status()
            data = resp.json()
            # Try known response shapes
            if isinstance(data, list):
                return [int(d) for d in data if str(d).isdigit()]
            depots = data.get("depots", data.get("depot_ids", []))
            return [int(d) for d in depots if str(d).isdigit()]
        except Exception as e:
            logger.debug(f"Morrenus depot list failed for {app_id}: {e}")
            return []

    # --- user info ---

    def get_user_stats(self) -> Optional[dict]:
        try:
            resp = self._get_client().get("/user/stats")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Failed to get user stats: %s", e)
            return None
