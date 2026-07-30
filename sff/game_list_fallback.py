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

"""SteamTools-Team games.json fallback data source.

Lazy-loaded JSON files providing DRM info, tags, NSFW flags, header images,
and DLC metadata for Steam games. Used as enrichment for search results when
Steam/Hubcap match a game, and as a last-resort name-resolution fallback
when both primary sources miss.

Files are expected alongside all_games.txt in the internal data folder:

  * games.json          — primary: full metadata per appid
   * games_appid.json    — name-only mapping appid -> name
   * software_appid.json — name-only mapping for software titles
   * dlc_appid.json      — DLC name metadata for DLC tools only
"""

import json
import logging
import ssl
import tempfile
import threading
import time
import urllib.request as _req
from pathlib import Path


def _get_ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for candidate in ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem"):
        if os.path.exists(candidate):
            try:
                return ssl.create_default_context(cafile=candidate)
            except Exception:
                pass
    try:
        return ssl.create_default_context()
    except Exception:
        logger.warning("No CA certificates available, HTTPS verification disabled for game list fetches")
        return ssl._create_unverified_context()

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400

_games_cache = {}
_games_cache_time = 0.0

_name_cache = {}
_dlc_name_cache = {}
_name_cache_time = 0.0
_name_mtime = 0.0

_loaded = False
_FALLBACK_LOG_LAST = 0.0
_LOAD_LOCK = threading.Lock()

_GAMES_JSON_URL = (
    "https://raw.githubusercontent.com/SteamTools-Team/GameList/refs/heads/main/games.json"
)
_NAME_JSON_URLS = {
    "games_appid.json": [
        "https://raw.githubusercontent.com/jsnli/steamappidlist/refs/heads/master/data/games_appid.json",
    ],
    "software_appid.json": [
        "https://raw.githubusercontent.com/jsnli/steamappidlist/refs/heads/master/data/software_appid.json",
    ],
}
_DLC_JSON_URLS = {
    "dlc_appid.json": [
        "https://cdn.jsdelivr.net/gh/jsnli/steamappidlist@master/data/dlc_appid.json",
    ],
}

def _get_cache_dir() -> Path:
    from sff.utils import sff_data_dir
    path = sff_data_dir() / "store_metadata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_json_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def _normalize_games_data(data) -> dict:
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    if isinstance(data, list):
        return {
            str(item.get("appid")): item
            for item in data
            if isinstance(item, dict) and item.get("appid")
        }
    logger.warning("games.json: expected dict or list, got %s", type(data).__name__)
    return {}


def _normalize_name_data(data) -> dict:
    if isinstance(data, dict):
        out = {}
        for appid, value in data.items():
            if isinstance(value, str):
                name = value
            elif isinstance(value, dict):
                name = value.get("name", "")
            else:
                continue
            if str(appid).isdigit() and name:
                out[str(appid)] = str(name)
        return out
    if isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict):
                appid = item.get("appid") or item.get("app_id") or item.get("id")
                name = item.get("name")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                appid, name = item[0], item[1]
            else:
                continue
            if str(appid).isdigit() and name:
                out[str(appid)] = str(name)
        return out
    logger.warning("appid name list: expected dict or list, got %s", type(data).__name__)
    return {}


def _load_cached_games_json() -> bool:
    global _games_cache, _games_cache_time, _loaded
    path = _get_cache_dir() / "games.json"
    if not path.exists():
        return False
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        cleaned = _normalize_games_data(data)
        if not cleaned:
            return False
        _games_cache = cleaned
        _games_cache_time = path.stat().st_mtime
        _loaded = True
        logger.info("games.json loaded from cache: %d entries", len(_games_cache))
        return True
    except Exception as e:
        logger.debug("Failed to load cached games.json from %s: %s", path, e)
    return False


def _load_games_json(force=False):
    global _games_cache, _games_cache_time, _loaded
    now = time.time()
    if not force and _games_cache_time and (now - _games_cache_time) < _CACHE_TTL:
        return bool(_games_cache)
    with _LOAD_LOCK:
        # Double-check inside the lock so concurrent calls don't
        # both fetch (was causing duplicate HTTP requests).
        if not force and _games_cache_time and (now - _games_cache_time) < _CACHE_TTL:
            return bool(_games_cache)
        if not force and not _games_cache and _load_cached_games_json():
            if (now - _games_cache_time) < _CACHE_TTL:
                return True
        if not _games_cache_time:
            logger.debug("Fetching games.json from GitHub...")
        try:
            request = _req.Request(_GAMES_JSON_URL, headers={"User-Agent": "SteaMidra/6.0.0"})
            with _req.urlopen(request, timeout=30, context=_get_ssl_ctx()) as resp:
                data = json.load(resp)
            _games_cache = _normalize_games_data(data)
            if _games_cache:
                _atomic_json_write(_get_cache_dir() / "games.json", data)
            _games_cache_time = now
            _loaded = True
            logger.info("games.json fetched: %d entries", len(_games_cache))
            return bool(_games_cache)
        except Exception as e:
            logger.debug("Fetching games.json failed: %s", e)
            if _load_cached_games_json():
                _games_cache_time = now
                return True
            _games_cache_time = now
            return False


def _load_name_source(fname: str, urls: list[str], *, force: bool, cache_dir: Path) -> tuple[dict, float]:
    """Load one appid->name source, preferring cached data unless refresh is due."""
    path = cache_dir / fname
    cached = {}
    cached_mtime = 0.0
    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                cached = _normalize_name_data(json.load(f))
            cached_mtime = path.stat().st_mtime
        except Exception as cache_exc:
            logger.debug("Failed to load cached %s: %s", fname, cache_exc)
            cached = {}

    should_refresh = force or not cached or (time.time() - cached_mtime) >= _CACHE_TTL
    if not should_refresh:
        return cached, cached_mtime

    last_exc = None
    for url in urls:
        try:
            request = _req.Request(url, headers={"User-Agent": "SteaMidra/6.3.2"})
            with _req.urlopen(request, timeout=20, context=_get_ssl_ctx()) as resp:
                data = json.load(resp)
            normalized = _normalize_name_data(data)
            if normalized:
                _atomic_json_write(path, normalized)
                return normalized, path.stat().st_mtime if path.exists() else time.time()
        except Exception as exc:
            last_exc = exc
            logger.debug("Failed to refresh %s from %s: %s", fname, url, exc)

    if last_exc:
        logger.debug("Using cached %s after refresh failure: %s", fname, last_exc)
    return cached, cached_mtime


def _load_name_cache(force=False):
    global _name_cache, _dlc_name_cache, _name_cache_time, _name_mtime
    now = time.time()
    if not force and _name_cache_time and (now - _name_cache_time) < _CACHE_TTL:
        return
    with _LOAD_LOCK:
        if not force and _name_cache_time and (now - _name_cache_time) < _CACHE_TTL:
            return
        cache_dir = _get_cache_dir()
        _name_cache = {}
        _dlc_name_cache = {}
        latest_mtime = 0.0
        for fname, urls in _NAME_JSON_URLS.items():
            normalized, mtime = _load_name_source(fname, urls, force=force, cache_dir=cache_dir)
            _name_cache.update(normalized)
            latest_mtime = max(latest_mtime, mtime)
        for fname, urls in _DLC_JSON_URLS.items():
            normalized, mtime = _load_name_source(fname, urls, force=force, cache_dir=cache_dir)
            _dlc_name_cache.update(normalized)
            latest_mtime = max(latest_mtime, mtime)
        _name_mtime = latest_mtime
        _name_cache_time = now
        if _name_cache or _dlc_name_cache:
            logger.debug(
                "Name cache loaded: %d app/software entries, %d DLC entries",
                len(_name_cache),
                len(_dlc_name_cache),
            )


def ensure_loaded(force=False):
    _load_games_json(force=force)
    _load_name_cache(force=force)
    _has = _loaded or bool(_name_cache) or bool(_dlc_name_cache)
    if force or not _loaded:
        global _FALLBACK_LOG_LAST
        now = time.time()
        if now - _FALLBACK_LOG_LAST > 60:
            logger.debug("Fallback data: games=%d entries, name_cache=%d entries, dlc_cache=%d entries",
                         len(_games_cache) if _games_cache else 0,
                         len(_name_cache) if _name_cache else 0,
                         len(_dlc_name_cache) if _dlc_name_cache else 0)
            _FALLBACK_LOG_LAST = now
    return _has


def metadata_counts() -> dict:
    ensure_loaded()
    return {
        "games": len(_games_cache),
        "names": len(_name_cache),
        "dlc_names": len(_dlc_name_cache),
    }


def has_fallback_data() -> bool:
    return bool(_games_cache)


def get_game_info(app_id: int) -> dict:
    ensure_loaded()
    return _games_cache.get(str(app_id), {})


def get_app_name(app_id: int | str) -> str:
    ensure_loaded()
    appid_str = str(app_id)
    info = _games_cache.get(appid_str, {})
    name = info.get("name", "") if isinstance(info, dict) else ""
    if name:
        return name
    return _name_cache.get(appid_str, "")


def get_dlc_name(app_id: int | str) -> str:
    ensure_loaded()
    return _dlc_name_cache.get(str(app_id), "")


def get_game_drm(app_id: int) -> list:
    info = get_game_info(app_id)
    return info.get("drm", [])


def get_game_tags(app_id: int) -> list:
    info = get_game_info(app_id)
    return info.get("tags", [])


def is_nsfw(app_id: int) -> bool:
    info = get_game_info(app_id)
    return bool(info.get("nsfw", False))


def get_game_header(app_id: int) -> str:
    info = get_game_info(app_id)
    return info.get("header_image", "")


def get_game_dlc(app_id: int) -> dict:
    info = get_game_info(app_id)
    return info.get("dlc", {})


def _normalize(text: str) -> str:
    chars = []
    for ch in text.lower():
        if ch.isalnum():
            chars.append(ch)
        else:
            chars.append(" ")
    return " ".join("".join(chars).split())


def search_name_fallback(query: str, limit=500):
    ensure_loaded()
    if not _name_cache:
        return []
    q_tokens = _normalized_tokens(query)
    if not q_tokens:
        return []
    results = []
    for appid_str, name in _name_cache.items():
        if not name or not isinstance(name, str):
            continue
        name_tokens = _normalized_tokens(name)
        if all(t in name_tokens for t in q_tokens):
            results.append({
                "app_id": int(appid_str) if appid_str.isdigit() else 0,
                "name": name,
            })
            if len(results) >= limit:
                break
    # Fallback: if token matching returned nothing, try substring matching
    # so abbreviated queries like "gta sa" still find "Grand Theft Auto: San Andreas"
    if not results:
        q_lower = query.lower().strip()
        for appid_str, name in _name_cache.items():
            if not name or not isinstance(name, str):
                continue
            if q_lower in name.lower():
                results.append({
                    "app_id": int(appid_str) if appid_str.isdigit() else 0,
                    "name": name,
                })
                if len(results) >= limit:
                    break
    return results


def _normalized_tokens(text: str) -> list[str]:
    """Lowercase, strip non-alnum, split into non-empty tokens."""
    return _normalize(text).split()

def search_games_json(query: str, limit=500):
    ensure_loaded()
    if not _games_cache:
        return []
    q_tokens = _normalized_tokens(query)
    if not q_tokens:
        return []
    results = []
    for appid_str, info in _games_cache.items():
        name = info.get("name", "")
        if not name:
            continue
        name_tokens = _normalized_tokens(name)
        if all(t in name_tokens for t in q_tokens):
            results.append({
                "app_id": int(appid_str) if appid_str.isdigit() else 0,
                "name": name,
                "drm": info.get("drm", []),
                "tags": info.get("tags", []),
                "nsfw": bool(info.get("nsfw", False)),
                "header_image": info.get("header_image", ""),
                "dlc": info.get("dlc", {}),
                "source": "games_json",
            })
            if len(results) >= limit:
                break
    # Fallback: substring matching when token matching misses
    # delisted/renamed games
    if not results:
        q_lower = query.lower().strip()
        for appid_str, info in _games_cache.items():
            name = info.get("name", "")
            if not name:
                continue
            if q_lower in name.lower():
                results.append({
                    "app_id": int(appid_str) if appid_str.isdigit() else 0,
                    "name": name,
                    "drm": info.get("drm", []),
                    "tags": info.get("tags", []),
                    "nsfw": bool(info.get("nsfw", False)),
                    "header_image": info.get("header_image", ""),
                    "dlc": info.get("dlc", {}),
                    "source": "games_json",
                })
                if len(results) >= limit:
                    break
    return results


_NON_GAME_NAME_KEYWORDS = ("soundtrack", "art book", "artbook", "ost", "music pack", "digital artbook")


def _is_game_entry(info: dict) -> bool:
    gtype = (info.get("type") or "").lower().strip()
    if gtype not in ("game", "demo", ""):
        return False
    name_lc = (info.get("name") or "").lower()
    for kw in _NON_GAME_NAME_KEYWORDS:
        if kw in name_lc:
            return False
    return True


def search_games_by_tag(tag: str, offset=0, per_page=20):
    ensure_loaded()
    if not _games_cache or not tag:
        return {"games": [], "total": 0}
    tag_lower = tag.lower().strip()
    seen = set()
    results = []

    # Phase 1: exact tag match (for genres like Action, RPG, etc.)
    for appid_str, info in _games_cache.items():
        if not _is_game_entry(info):
            continue
        game_tags = info.get("tags", [])
        if any(t.lower() == tag_lower for t in game_tags):
            if appid_str not in seen:
                seen.add(appid_str)
                results.append({
                    "app_id": int(appid_str) if appid_str.isdigit() else 0,
                    "name": info.get("name", f"App {appid_str}"),
                    "last_updated": info.get("updated_date", ""),
                    "status": "",
                    "size": 0,
                    "image_url": info.get("header_image", ""),
                    "drm": info.get("drm", []),
                    "tags": info.get("tags", []),
                    "nsfw": bool(info.get("nsfw", False)),
                    "dlc": info.get("dlc", {}),
                    "source": "games_json",
                })

    # Phase 2: name fallback (catches genres like Shooter, Puzzle, Horror)
    for appid_str, info in _games_cache.items():
        if appid_str in seen:
            continue
        if not _is_game_entry(info):
            continue
        name = info.get("name", "")
        if tag_lower in name.lower():
            seen.add(appid_str)
            results.append({
                "app_id": int(appid_str) if appid_str.isdigit() else 0,
                "name": name,
                "last_updated": info.get("updated_date", ""),
                "status": "",
                "size": 0,
                "image_url": info.get("header_image", ""),
                "drm": info.get("drm", []),
                "tags": info.get("tags", []),
                "nsfw": bool(info.get("nsfw", False)),
                "dlc": info.get("dlc", {}),
                "source": "games_json",
            })

    results.sort(key=lambda g: (g.get("name") or "").lower())
    total = len(results)
    page = results[offset:offset + per_page]
    return {"games": page, "total": total, "has_fallback_data": bool(_games_cache)}


def enrich_game_dict(game: dict) -> dict:
    app_id = game.get("app_id")
    if not app_id:
        return game
    info = get_game_info(app_id)
    if not info:
        return game
    game["drm"] = info.get("drm", [])
    game["tags"] = info.get("tags", [])
    game["nsfw"] = bool(info.get("nsfw", False))
    game["image_url"] = game.get("image_url") or info.get("header_image", "")
    game["header_image"] = info.get("header_image", "") or game.get("image_url", "")
    game["dlc"] = info.get("dlc", {})
    return game
