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
STATUS_CACHE_TTL = 300
_STATUS_CACHE_MAX = 500  # 5 minutes, same as Hubcap Bot


@dataclass
class GameInfo:
    app_id: int
    name: str
    last_updated: str = ""
    status: str = ""
    size: int = 0
    # Lowercase platform tags like "windows", "macos", "linux".
    # Empty list means "Hubcap didn't report platforms for this game"
    # and the caller should treat the entry as platform-agnostic
    # (don't filter it out).
    platforms: list = field(default_factory=list)


def _parse_platforms(item):
    """Extract a list of lowercase platform tags from a Hubcap row.

    Hubcap responses use a few different shapes for platform info
    across endpoints. Common shapes:

      * `"platforms": ["windows", "macos"]` (list of strings)
      * `"platforms": "windows,macos"` (csv string)
      * `"oslist": "windows"` (Steam-style csv)
      * per-platform booleans: `windows: true`, `macos: false`,
        `linux: false`, plus the lowercase / capitalized variants
        Hubcap's UI sometimes ships
      * `"os_list": ["Windows"]`

    Anything we can't parse returns []. The caller treats [] as
    "platform unknown, keep the row" so we never drop entries the
    server didn't tag.
    """
    if not isinstance(item, dict):
        return []
    out = []

    def _add(val):
        v = str(val).strip().lower()
        if v in ("win", "win32", "win64"):
            v = "windows"
        elif v in ("mac", "osx", "os x", "macosx"):
            v = "macos"
        elif v in ("linux64", "steamos", "linux32"):
            v = "linux"
        if v in ("windows", "macos", "linux") and v not in out:
            out.append(v)

    for key in ("platforms", "platform", "oslist", "os_list", "os"):
        val = item.get(key)
        if not val:
            continue
        if isinstance(val, list):
            for entry in val:
                _add(entry)
        elif isinstance(val, str):
            for piece in val.replace("|", ",").split(","):
                if piece.strip():
                    _add(piece)

    # Per-platform boolean flags. Keys vary in casing across
    # Hubcap's responses (windows / Windows / WINDOWS etc.).
    bool_keys = {
        "windows": ("windows", "Windows", "WINDOWS", "win"),
        "macos":   ("macos", "macOS", "Mac", "mac", "osx"),
        "linux":   ("linux", "Linux", "LINUX"),
    }
    for plat, keys in bool_keys.items():
        for k in keys:
            v = item.get(k)
            if v is True or (isinstance(v, str) and v.strip().lower() in ("true", "1", "yes")):
                if plat not in out:
                    out.append(plat)
                break
    return out


@dataclass
class LibraryPage:
    games: list = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 100

    @property
    def total_pages(self):
        if self.limit <= 0:
            return 1
        return max(1, (self.total + self.limit - 1) // self.limit)


@dataclass
class GameStatus:
    app_id: int
    status: str = "unknown"
    message: str = ""
    _cached_at = 0.0


class StoreApiClient:
    """Morrenus manifest API. Needs a Bearer token (smm_ key)."""

    def __init__(self, api_key, timeout = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self._status_cache: dict[int, GameStatus] = {}
        self._client: Optional[httpx.Client] = None

    def _get_client(self):
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
    def validate_api_key(api_key):
        return bool(api_key and api_key.strip().startswith("smm") and len(api_key.strip()) > 10)

    def test_api_key(self):
        try:
            resp = self._get_client().get("/user/stats")
            return resp.status_code == 200
        except Exception as e:
            logger.warning("API key test failed: %r", e)
            return False

    # --- library browsing ---

    def get_library(
        self,
        limit = 100,
        offset = 0,
        search = None,
        sort_by = "updated",
    ):
        params = {
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
        }
        if search:
            params["search"] = search
        try:
            resp = self._get_client().get("/library", params=params)
            # Hubcap library returns 500 on a bunch of cyrillic queries (RU
            # users hit this constantly typing "рф" in the search field) and
            # sometimes 503 during their own outages. Both are server-side,
            # nothing the client can do, and surfacing them as ERROR popups
            # in the live log scared people. Treat 4xx/5xx the same as an
            # empty result so the rest of the pipeline (Steam applist etc)
            # picks up the slack quietly.
            if resp.status_code in (400, 500, 503):
                logger.debug(
                    "hubcap library api %s for offset=%d limit=%d search=%r, skipping",
                    resp.status_code, offset, limit, search,
                )
                return LibraryPage(offset=offset, limit=limit)
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
                    platforms=_parse_platforms(item),
                ))
            return LibraryPage(
                games=games,
                total=data.get("total_count", len(games)),
                offset=offset,
                limit=limit,
            )
        except httpx.HTTPStatusError as e:
            # raise_for_status above re-raises 4xx/5xx that aren't in the
            # quiet-skip set. Still keep them out of ERROR-level so the live
            # log doesn't get spammed.
            logger.debug("hubcap library status err %s: %s", e.response.status_code, e)
            return LibraryPage(offset=offset, limit=limit)
        except Exception as e:
            err_str = str(e)
            if isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                logger.debug("hubcap library unreachable (network): %r", e)
            elif "Name or service not known" in err_str or "getaddrinfo" in err_str.lower():
                logger.debug("hubcap library dns resolution failed: %r", e)
            else:
                logger.warning("Failed to get library: %r", e)
            return LibraryPage()

    def search_library(
        self,
        query: str,
        limit = 50,
        search_by_appid = False,
    ):
        params = {
            "q": query,
            "limit": limit,
        }
        if search_by_appid:
            params["appid"] = "true"
        try:
            resp = self._get_client().get("/search", params=params)
            # Hubcap /search rejects a lot of cyrillic queries with 400 and
            # has a known 500 cluster too. Both are server-side. Return an
            # empty list with a single DEBUG line so the user just sees "no
            # results" instead of a scary [ERRO] popup.
            if resp.status_code in (400, 500, 503):
                logger.debug(
                    "hubcap search api %s for q=%r, skipping",
                    resp.status_code, query,
                )
                return []
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
                    platforms=_parse_platforms(item),
                ))
            return results
        except httpx.HTTPStatusError as e:
            logger.debug("hubcap search status err %s: %s", e.response.status_code, e)
            return []
        except Exception as e:
            logger.error("Search failed: %r", e)
            return []

    def get_all_games(self):
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
            logger.error("Failed to get all games: %r", e)
            return []

    # --- game status ---

    def get_game_status(self, app_id, force_refresh = False):
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
            if len(self._status_cache) > _STATUS_CACHE_MAX:
                keys_to_drop = sorted(
                    self._status_cache.keys(),
                    key=lambda k: self._status_cache[k]._cached_at,
                )[:len(self._status_cache) // 2]
                for k in keys_to_drop:
                    self._status_cache.pop(k, None)
            return status
        except Exception as e:
            logger.warning("Failed to get status for %d: %r", app_id, e)
            return GameStatus(app_id=app_id, status="error", message=str(e))

    # --- downloads ---

    def get_manifest(self, app_id):
        try:
            resp = self._get_client().get(f"/manifest/{app_id}")
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error("Failed to download manifest for %d: %r", app_id, e)
            return None

    def get_lua_content(self, app_id):
        try:
            resp = self._get_client().get(f"/lua/{app_id}")
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("Failed to get lua for %d: %r", app_id, e)
            return None

    def get_workshop_manifest(self, workshop_id):
        try:
            resp = self._get_client().get(f"/generate/workshopmanifest/{workshop_id}")
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error("Failed to get workshop manifest for %d: %r", workshop_id, e)
            return None

    # --- depot helpers ---

    def get_game_depots(self, app_id):
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

    def get_user_stats(self):
        try:
            resp = self._get_client().get("/user/stats")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Failed to get user stats: %r", e)
            return None


# Module-level Store grid cache. The Web bridge wipes this on
# `store_show_software` toggles so the next list_games call
# rebuilds against the fresh setting. Stays None until a caller
# decides to use it; list_games itself does not populate it.
_cached_grid = None


def _coerce_show_software(raw) -> bool:
    """STORE_SHOW_SOFTWARE ships as a bool but older settings.bin
    blobs may surface it as a string. Match the close-to-tray pattern
    so the parse is consistent across the project."""
    if raw is None or raw == "":
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ("false", "0", "no", "off")


def list_games(entries):
    """Filter a Store grid result set against `STORE_SHOW_SOFTWARE`.

    The setting is read on every call, so a flip from the Settings
    dialog takes effect on the next round trip without restart. When
    the toggle parses as false, every entry whose `type` field equals
    `"software"` is dropped before the list returns. Entries whose
    type is unset, missing, or non-string pass through untouched.

    The input is iterable of dicts (Steam IStoreService rows or the
    Hubcap-merged dicts the Store tab renders). The output preserves
    input order and is a fresh list, so the caller can mutate freely.
    """
    try:
        from sff.storage.settings import get_setting as _get
        from sff.structs import Settings
        show_software = _coerce_show_software(_get(Settings.STORE_SHOW_SOFTWARE))
    except Exception:
        # Settings layer unreachable: keep the conservative default
        # (hide software, matching the SettingItem default of False).
        show_software = False

    out = []
    for entry in entries or []:
        if not show_software:
            try:
                etype = entry.get("type") if isinstance(entry, dict) else getattr(entry, "type", None)
            except Exception:
                etype = None
            if isinstance(etype, str) and etype.strip().lower() == "software":
                continue
        out.append(entry)
    return out
