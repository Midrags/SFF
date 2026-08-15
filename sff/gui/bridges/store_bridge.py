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
Store domain bridge functions extracted from web_bridge.py.

Each ``_bridge_*`` function takes a ``WebBridge`` instance as its first
parameter (named ``bridge``) in place of ``self``.  All standalone
helpers that only serve the Store code path are co-located here.

Helpers that are also used by other domains — ``_get_store_client``,
``_check_hubcap_key``, ``_is_hubcap_disabled``, ``_get_ssl_ctx``,
``_should_show_software`` — remain in **web_bridge.py** and are
accessed as ``bridge.<name>(…)``.
"""

import concurrent.futures as _concurrent
import json
import logging
import os
import re
import sys
import threading as _thr
import time as _time
import unicodedata as _ud
from collections import OrderedDict as _OrderedDict
from functools import lru_cache
from pathlib import Path

import urllib.request as _req
import urllib.parse as _urlparse

from PyQt6.QtCore import QTimer

from sff.game_list_fallback import (
    browse_games_json,
    enrich_game_dict,
    has_fallback_data,
    search_games_json,
    search_games_by_tag,
    search_name_fallback,
    ensure_loaded as _ensure_fallback_loaded,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants and caches (store‑only)
# ---------------------------------------------------------------------------

_NSFW_NAME_RE = re.compile(r"(hentai|futanari|furry|sex)", re.IGNORECASE)
_KNOWN_MACOS_ONLY_APPIDS = {12250}

_CRACK_BUILDID_CACHE: dict[str, str] | None = None
_CRACK_BUILDID_TIME = 0.0
_CRACK_BUILDID_FETCHING = False

_STEAM_APPLIST_CACHE = None
_STEAM_APPLIST_CACHE_TIME = 0.0

_STEAM_PLATFORM_CACHE: "_OrderedDict[int, dict]" = _OrderedDict()
_STEAM_PLATFORM_CACHE_MAX = 2000

_NONGAME_NAME_KW = ("soundtrack", "art book", "artbook", " ost", "music pack", "digital artbook")
_NON_GAME_TYPES = frozenset({2, 4, 6, 7, 9, 10, 11, 12, 13})

_ALIAS_EXPANSIONS = {
    "gta":   ["grand theft auto"],
    "rdr":   ["red dead redemption"],
    "cod":   ["call of duty"],
    "re":    ["resident evil"],
    "tf2":   ["team fortress 2"],
    "csgo":  ["counter strike global offensive", "counter-strike global offensive"],
    "cs2":   ["counter strike 2", "counter-strike 2"],
    "css":   ["counter strike source", "counter-strike source"],
    "cs":    ["counter strike", "counter-strike"],
    "kh":    ["kingdom hearts"],
    "mh":    ["monster hunter"],
    "ff":    ["final fantasy"],
    "ds":    ["dark souls"],
    "ds1":   ["dark souls"],
    "ds2":   ["dark souls 2", "dark souls ii"],
    "ds3":   ["dark souls 3", "dark souls iii"],
    "er":    ["elden ring"],
    "mk":    ["mortal kombat"],
    "ac":    ["assassins creed", "assassin s creed"],
    "btd":   ["bloons td"],
    "tw":    ["total war"],
    "wh":    ["warhammer"],
    "sf":    ["street fighter"],
    "tk":    ["tekken"],
    "p5":    ["persona 5"],
    "p4":    ["persona 4"],
    "p3":    ["persona 3"],
    "lol":   ["league of legends"],
    "pubg":  ["playerunknown s battlegrounds", "playerunknowns battlegrounds"],
    "wow":   ["world of warcraft"],
    "hots":  ["heroes of the storm"],
    "sc2":   ["starcraft 2", "starcraft ii"],
    "d2":    ["diablo 2", "diablo ii", "destiny 2"],
    "d3":    ["diablo 3", "diablo iii"],
    "d4":    ["diablo 4", "diablo iv"],
    "wukong": ["black myth wukong"],
}

# ---------------------------------------------------------------------------
# Module-level helper functions (store‑only)
# ---------------------------------------------------------------------------

def _looks_nsfw_by_name(name) -> bool:
    return bool(_NSFW_NAME_RE.search(str(name or "")))


def _store_blocks_nsfw() -> bool:
    try:
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings
        val = get_setting(Settings.STORE_BLOCK_NSFW)
    except Exception:
        return False
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _filter_store_nsfw_rows(rows):
    return [
        row for row in (rows or [])
        if not row.get("nsfw") and not _looks_nsfw_by_name(row.get("name"))
    ]


def _prefetch_crack_buildids():
    global _CRACK_BUILDID_CACHE, _CRACK_BUILDID_TIME, _CRACK_BUILDID_FETCHING
    if _CRACK_BUILDID_CACHE is not None and (_time.time() - _CRACK_BUILDID_TIME) < 3600:
        return
    if _CRACK_BUILDID_FETCHING:
        return
    _CRACK_BUILDID_FETCHING = True
    try:
        import httpx
        resp = httpx.get(
            "https://raw.githubusercontent.com/KoriaPolis/CrakFiles/main/crackfiles.json",
            follow_redirects=True, timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            out = {}
            for g in data:
                name = str(g.get("name", "") or "").strip().lower()
                bid = str(g.get("buildid", "") or "").strip()
                if name and bid:
                    out[name] = bid
            _CRACK_BUILDID_CACHE = out
            _CRACK_BUILDID_TIME = _time.time()
    except Exception:
        pass
    finally:
        _CRACK_BUILDID_FETCHING = False


def _get_crack_buildid_map() -> dict[str, str]:
    """Return cached crack buildid map. Never blocks — returns empty if not ready."""
    return _CRACK_BUILDID_CACHE or {}


def _platform_cache_put(aid: int, entry: dict) -> None:
    _STEAM_PLATFORM_CACHE[aid] = entry
    _STEAM_PLATFORM_CACHE.move_to_end(aid)
    while len(_STEAM_PLATFORM_CACHE) > _STEAM_PLATFORM_CACHE_MAX:
        _STEAM_PLATFORM_CACHE.popitem(last=False)


@lru_cache(maxsize=4096)
def _normalize_for_search(text):
    """Strip trademark marks, registered marks, accents, and odd
    punctuation so a user typing 'lego batman' still matches a Steam
    title rendered as 'LEGO\u00ae Batman\u2122: Legacy of the Dark Knight'.
    Returns a lowercased ASCII-only blob with whitespace collapsed.
    Empty / non-string inputs return ''.
    """
    if not text or not isinstance(text, str):
        return ""
    for mark in ("\u2122", "\u00ae", "\u00a9", "\u2117", "\u2120"):
        text = text.replace(mark, "")
    decomposed = _ud.normalize("NFKD", text)
    out_chars = []
    for ch in decomposed:
        cat = _ud.category(ch)
        if cat.startswith("M") or cat.startswith("S"):
            continue
        if not ch.isalnum():
            out_chars.append(" ")
            continue
        out_chars.append(ch.lower())
    collapsed = "".join(out_chars).split()
    return " ".join(collapsed)


def _store_words(text_norm):
    return [w for w in (text_norm or "").split() if w]


def _store_query_has_alias(query_norm):
    if query_norm in _ALIAS_EXPANSIONS:
        return True
    return any(token in _ALIAS_EXPANSIONS for token in _store_words(query_norm))


def _store_short_loose_query(query_norm):
    compact = (query_norm or "").replace(" ", "")
    return len(compact) < 3 and not compact.isdigit() and not _store_query_has_alias(query_norm)


def _store_word_start_match(query_norm, name_norm):
    tokens = _store_words(query_norm)
    if not tokens:
        return True
    words = _store_words(name_norm)
    pos = 0
    for token in tokens:
        found = False
        for idx in range(pos, len(words)):
            if words[idx].startswith(token):
                pos = idx + 1
                found = True
                break
        if not found:
            return False
    return True


def _store_token_match(token, name_norm):
    if len(token) < 3:
        return token in _store_words(name_norm)
    return token in name_norm


def _store_all_tokens_match(query_norm, name_norm, _depth=0):
    if _depth > 5:
        return False
    tokens = _store_words(query_norm)
    if not tokens:
        return True
    for token in tokens:
        if _store_token_match(token, name_norm):
            continue
        alts = _ALIAS_EXPANSIONS.get(token)
        if alts and any(_store_all_tokens_match(_normalize_for_search(alt), name_norm, _depth + 1) for alt in alts):
            continue
        return False
    return True


def _store_alias_score(query_norm, name_norm):
    candidates = []
    seen = set()
    for candidate in _alias_expanded_queries(query_norm):
        cand_norm = _normalize_for_search(candidate)
        if not cand_norm or cand_norm == query_norm or cand_norm in seen:
            continue
        seen.add(cand_norm)
        candidates.append(cand_norm)
    for cand_norm in candidates:
        if name_norm == cand_norm:
            return 0
        if name_norm.startswith(cand_norm):
            return 1
        if _store_word_start_match(cand_norm, name_norm):
            return 2
        if _store_all_tokens_match(cand_norm, name_norm):
            return 3
        if cand_norm in name_norm:
            return 4
    return None


def _store_search_score(query, name, appid=None):
    query_norm = _normalize_for_search(query or "")
    name_norm = _normalize_for_search(name or "")
    appid_text = str(appid or "").strip()
    if not query_norm:
        return (50, name_norm, appid_text)

    compact = query_norm.replace(" ", "")
    if compact.isdigit() and appid_text:
        if appid_text == compact:
            return (0, "", appid_text)
        if len(compact) >= 3 and appid_text.startswith(compact):
            return (3, appid_text, name_norm)

    if name_norm == query_norm:
        return (1, name_norm, appid_text)

    has_alias = _store_query_has_alias(query_norm)
    short_alias = has_alias and len(compact) < 3
    if not short_alias and name_norm.startswith(query_norm):
        return (2, name_norm, appid_text)
    if _store_short_loose_query(query_norm):
        if len(compact) >= 2 and _store_word_start_match(query_norm, name_norm):
            return (4, name_norm, appid_text)
        return (99, name_norm, appid_text)
    if not short_alias and _store_word_start_match(query_norm, name_norm):
        return (4, name_norm, appid_text)

    alias_score = _store_alias_score(query_norm, name_norm)
    if alias_score is not None:
        return (5, alias_score, name_norm, appid_text)

    if short_alias and name_norm.startswith(query_norm):
        return (6, name_norm, appid_text)
    if short_alias and _store_word_start_match(query_norm, name_norm):
        return (7, name_norm, appid_text)
    if _store_all_tokens_match(query_norm, name_norm):
        return (8, name_norm, appid_text)
    if not short_alias and not _store_short_loose_query(query_norm) and query_norm in name_norm:
        return (9, name_norm, appid_text)
    return (99, name_norm, appid_text)


def _matches_normalized(query_norm, name_norm):
    return _store_search_score(query_norm, name_norm)[0] < 99


def _attach_store_request_id(data, request_id):
    if not isinstance(data, dict):
        data = {"games": [], "total": 0}
    if request_id:
        data["request_id"] = str(request_id)
    return data


def _alias_expanded_queries(query):
    """Yield candidate query strings for remote search backends that
    do plain substring matching on game names.

    Hubcap's /library and /search endpoints don't know about
    abbreviations, so a user typing "gta san andreas" never hits a
    title stored as "Grand Theft Auto: San Andreas". For each known
    alias token (gta, re, cod, rdr, kh, er, tf2, cs2, ...) we generate
    one extra query string with that token swapped for each of its
    expansions. Original query is yielded first; expansions follow.
    Duplicates are de-duped. Returns a list, not a generator, so the
    caller can ``len()`` and reorder freely.
    """
    if not query or not isinstance(query, str):
        return []
    raw = query.strip()
    if not raw:
        return []
    out = [raw]
    seen = {raw.lower()}
    tokens = raw.split()
    if not tokens:
        return out
    full_alts = _ALIAS_EXPANSIONS.get(raw.lower())
    if full_alts:
        for alt in full_alts:
            if alt.lower() not in seen:
                seen.add(alt.lower())
                out.append(alt)
    for i, tok in enumerate(tokens):
        alts = _ALIAS_EXPANSIONS.get(tok.lower())
        if not alts:
            continue
        for alt in alts:
            new_tokens = list(tokens)
            new_tokens[i] = alt
            cand = " ".join(new_tokens)
            key = cand.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)
            if len(out) >= 6:
                return out
    return out


def _load_steam_applist():
    global _STEAM_APPLIST_CACHE, _STEAM_APPLIST_CACHE_TIME

    _now = _time.time()
    if _STEAM_APPLIST_CACHE is not None and (_now - _STEAM_APPLIST_CACHE_TIME) < 86400:
        return _STEAM_APPLIST_CACHE

    _lock = getattr(_load_steam_applist, '_lock', None)
    if _lock is None:
        _lock = _thr.Lock()
        _load_steam_applist._lock = _lock

    with _lock:
        if _STEAM_APPLIST_CACHE is not None and (_time.time() - _STEAM_APPLIST_CACHE_TIME) < 86400:
            return _STEAM_APPLIST_CACHE
        if getattr(_load_steam_applist, '_building', False):
            while getattr(_load_steam_applist, '_building', False):
                _lock.release()
                _time.sleep(0.05)
                _lock.acquire()
            if _STEAM_APPLIST_CACHE is not None and (_time.time() - _STEAM_APPLIST_CACHE_TIME) < 86400:
                return _STEAM_APPLIST_CACHE
        _load_steam_applist._building = True

    from sff.core.utils import root_folder

    _all_games_file = root_folder(outside_internal=True) / "all_games.txt"
    _all_games_file.parent.mkdir(parents=True, exist_ok=True)

    _merged: dict[int, dict] = {}

    def _add_apps(apps):
        for a in apps:
            aid = a.get("appid") or a.get("app_id")
            if aid and isinstance(aid, (int, float, str)):
                aid_int = int(aid)
                if aid_int > 0 and aid_int not in _merged:
                    name = str(a.get("name") or f"App {aid_int}").strip()
                    if name:
                        _merged[aid_int] = {"name": name, "appid": aid_int}

    # 1. Local all_games.txt (fast, no network)
    if _all_games_file.is_file() and _all_games_file.stat().st_size > 0:
        try:
            _apps_from_txt = []
            _line_re = re.compile(r'^(.*)\s+\[ID=(\d+)\]$')
            with _all_games_file.open(encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.rstrip()
                    _m = _line_re.match(_line)
                    if _m:
                        _apps_from_txt.append({"name": _m.group(1), "appid": int(_m.group(2))})
            _add_apps(_apps_from_txt)
            logger.debug("Steam applist loaded from all_games.txt: %d apps", len(_apps_from_txt))
        except Exception as _exc:
            logger.debug("all_games.txt load failed: %s", _exc)

    # 2. Steam API (short timeout, best-effort)
    try:
        from sff.core.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings
        _api_key = get_setting(Settings.STEAM_WEB_API_KEY)
        if not isinstance(_api_key, str) or not _api_key.strip():
            _api_key = _DEFAULT_KEY
        # _should_show_software() is kept in web_bridge.py (also used by update_games_file).
        # We import it here.
        from sff.gui.web_bridge import _should_show_software
        _params = {"key": _api_key, "max_results": "50000",
                   "include_games": "1", "include_dlc": "0",
                   "include_software": _should_show_software(),
                   "include_videos": "0", "include_hardware": "0"}
        _games = []
        _base = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
        for _ in range(3):
            try:
                from sff.gui.web_bridge import _get_ssl_ctx
                _qs = "&".join(f"{k}={v}" for k, v in _params.items())
                _req2 = _req.Request(f"{_base}?{_qs}", headers={"User-Agent": "SteaMidra/6.1.0"})
                with _req.urlopen(_req2, timeout=5, context=_get_ssl_ctx()) as _resp:
                    _data = json.loads(_resp.read())
                _apps_batch = _data.get("response", {}).get("apps", [])
                _games.extend(_apps_batch)
                if not _data.get("response", {}).get("have_more_results"):
                    break
                _last = _data.get("response", {}).get("last_appid")
                if _last:
                    _params["last_appid"] = str(_last)
                else:
                    break
            except Exception:
                break
        if _games:
            _add_apps(_games)
            logger.debug("Steam API contributed %d apps", len(_games))
    except Exception as _exc:
        logger.debug("Steam API fetch skipped: %s", _exc)

    # 3. GitHub mirrors — load from store_metadata/ cache first,
    #    refresh when older than 6 hours. SFF-main already ships
    #    store_metadata/games.json etc so first-launch is instant.
    _mirror_urls = {
        "games_appid.json": "https://raw.githubusercontent.com/jsnli/steamappidlist/refs/heads/master/data/games_appid.json",
        "software_appid.json": "https://raw.githubusercontent.com/jsnli/steamappidlist/refs/heads/master/data/software_appid.json",
    }
    _mirror_dir = root_folder(outside_internal=True) / "store_metadata"
    _mirror_dir.mkdir(parents=True, exist_ok=True)

    import concurrent.futures as _cf

    def _fetch_github_mirror(filename, url):
        cache_file = _mirror_dir / filename
        try:
            if cache_file.is_file():
                _age = _time.time() - cache_file.stat().st_mtime
                if _age < 21600:
                    _payload = json.loads(cache_file.read_bytes())
                    return _payload
        except Exception:
            pass
        try:
            import httpx as _httpx
            _resp = _httpx.get(url, timeout=20, follow_redirects=True)
            if _resp.status_code != 200:
                return None
            _payload = _resp.json()
            try:
                cache_file.write_bytes(_resp.content)
            except Exception:
                pass
            return _payload
        except Exception:
            return None

    def _add_mirror_payload(payload):
        if isinstance(payload, dict):
            for _key_str, _val_name in payload.items():
                if _key_str.isdigit():
                    _add_apps([{"name": str(_val_name), "appid": int(_key_str)}])
        elif isinstance(payload, list):
            for _entry in payload:
                if isinstance(_entry, dict) and "appid" in _entry:
                    _add_apps([{"name": _entry.get("name", ""), "appid": _entry["appid"]}])

    _gj = _mirror_dir / "games.json"
    if _gj.is_file():
        try:
            _games_payload = json.loads(_gj.read_bytes())
            _add_mirror_payload(_games_payload)
        except Exception:
            pass

    try:
        with _cf.ThreadPoolExecutor(max_workers=2) as _ex:
            _futures = {_ex.submit(_fetch_github_mirror, fn, u): fn for fn, u in _mirror_urls.items()}
            for _fut in _cf.as_completed(_futures):
                try:
                    _payload = _fut.result()
                    if _payload:
                        _add_mirror_payload(_payload)
                except Exception:
                    pass
    except Exception as _exc:
        logger.debug("GitHub mirror batch failed: %s", _exc)

    # 4. Build the merged list and cache it
    _result = list(_merged.values())
    if _result:
        try:
            _gs = [x.get("name", "UNKNOWN GAME") + f" [ID={x.get('appid')}]" for x in _result]
            _gs.sort()
            with _all_games_file.open("w", encoding="utf-8") as _f:
                _f.write("\n".join(_gs))
        except Exception:
            pass
        _STEAM_APPLIST_CACHE = _result
        _STEAM_APPLIST_CACHE_TIME = _now
        _result.sort(key=lambda x: x.get('appid', 0))
        logger.info("Steam applist built — %s total apps", len(_result))
        _load_steam_applist._building = False
        return _result

    _STEAM_APPLIST_CACHE = []
    _STEAM_APPLIST_CACHE_TIME = _now
    _load_steam_applist._building = False
    return []


def _search_steam_catalog(query, offset, per_page, sort_by='updated'):
    """Fallback store search using full Steam public app list when Hubcap is unavailable."""
    apps = _load_steam_applist()
    if not apps:
        return {"games": [], "total": 0, "fallback": True}
    if query:
        q_norm = _normalize_for_search(query)
        if q_norm:
            apps = [
                a for a in apps
                if _store_search_score(q_norm, a.get("name", ""), a.get("appid"))[0] < 99
            ]
    sb = (sort_by or 'updated').lower()
    if sb == 'name_asc':
        apps.sort(key=lambda a: (a.get('name') or '').lower())
    elif sb == 'name_desc':
        apps.sort(key=lambda a: (a.get('name') or '').lower(), reverse=True)
    elif sb == 'oldest':
        apps.sort(key=lambda a: a.get('appid') or 0)
    elif sb == 'newest':
        apps.sort(key=lambda a: a.get('appid') or 0, reverse=True)
    if query:
        apps.sort(key=lambda a: _store_search_score(query, a.get("name", ""), a.get("appid")))
    total = len(apps)
    fetch_count = 200 if query else per_page
    page_apps = apps[offset: offset + fetch_count]
    actual_page = page_apps[0: per_page]
    app_ids = [a["appid"] for a in actual_page if a.get("appid")]
    image_urls, type_map, nsfw_map = _fetch_steam_image_urls(app_ids)
    games = []
    for a in actual_page:
        appid = a.get("appid", 0)
        if type_map.get(appid) in _NON_GAME_TYPES:
            continue
        name_lc = a.get("name", f"App {appid}").lower()
        if any(kw in name_lc for kw in _NONGAME_NAME_KW):
            continue
        row = {
            "app_id": appid,
            "name": a.get("name", f"App {appid}"),
            "last_updated": "",
            "status": "",
            "size": 0,
            "image_url": image_urls.get(appid),
            "nsfw": bool(nsfw_map.get(appid, False)),
        }
        enrich_game_dict(row)
        games.append(row)
    return {"games": games, "total": total, "fallback": True}


def _fetch_steam_platforms(app_ids):
    """Look up Steam metadata for each appid via batched
    ``IStoreBrowseService/GetItems/v1`` calls.

    Returns a dict mapping appid (int) -> dict with four keys:
      'platforms'       : set of lowercase tags ("windows", "macos",
                          "linux") or ``{"_unknown"}`` when GetItems
                          returned no platform data
      'type'            : Steam's app type integer mapped to a
                          lowercase string ('game', 'dlc', 'demo',
                          'mod', 'tool', 'video', 'music',
                          'advertising'); '' when GetItems returned
                          no body for the appid
      'parent_appid'    : int when this appid is a DLC of another app
                          (Steam exposes this only for DLCs); None
                          for base games and demos
      'delisted_blank'  : True when GetItems returned the appid as a
                          row with no name and no type. Steam strips
                          all public metadata for fully removed
                          entries; classic delisted GAMES still
                          return name + type=0 (verified for GTA SA
                          classic, Resident Evil HD, Dark Souls PTDE
                          Edition, etc), so this flag is a strong
                          "this is removed-from-store DLC content"
                          signal

    Callers use ``parent_appid`` and ``delisted_blank`` as STRUCTURAL DLC
    drop signals — no name-keyword matching required. ``platforms`` is
    used to drop macOS-only / Linux-only ports.

    Switched from ``appdetails`` to ``GetItems`` because appdetails enforces
    a strict ~200 req / 5 min rate limit that returned HTTP 429 mid-flow
    on heavy searches. GetItems batches up to ~50 appids per request
    and has no per-IP rate limit visible.

    Uses the in-process ``_STEAM_PLATFORM_CACHE`` to avoid refetching
    on repeat searches.
    """
    if not app_ids:
        return {}

    out: dict[int, dict] = {}
    pending: list[int] = []
    for raw in app_ids:
        try:
            aid = int(raw)
        except (TypeError, ValueError):
            continue
        if aid <= 0:
            continue
        cached = _STEAM_PLATFORM_CACHE.get(aid)
        if cached is not None:
            out[aid] = cached
        else:
            pending.append(aid)

    if not pending:
        return out

    chunk_size = 50
    consecutive_failures = 0
    blank_default = {
        "platforms": {"_unknown"},
        "type": "",
        "parent_appid": None,
        "delisted_blank": False,
    }
    from sff.gui.web_bridge import _get_ssl_ctx
    for start in range(0, len(pending), chunk_size):
        chunk = pending[start:start + chunk_size]
        if consecutive_failures >= 2:
            for aid in chunk:
                cached = dict(blank_default)
                _platform_cache_put(aid, cached)
                out[aid] = cached
            continue
        try:
            payload = {
                "ids": [{"appid": aid} for aid in chunk],
                "context": {"language": "english", "country_code": "US"},
                "data_request": {
                    "include_assets": False,
                    "include_platforms": True,
                    "include_basic_info": False,
                    "include_release": False,
                },
            }
            url = (
                "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json="
                + _urlparse.quote(json.dumps(payload, separators=(",", ":")))
            )
            request = _req.Request(url, headers={"User-Agent": "Mozilla/5.0 SteaMidra"})
            with _req.urlopen(request, timeout=8, context=_get_ssl_ctx()) as resp:
                data = json.loads(resp.read())
            seen: set[int] = set()
            for item in (data.get("response") or {}).get("store_items", []) or []:
                aid = item.get("appid")
                if not isinstance(aid, int):
                    continue
                seen.add(aid)
                name = item.get("name") or ""
                type_int = item.get("type")
                related = item.get("related_items") or {}
                parent_appid = related.get("parent_appid")
                if isinstance(parent_appid, int) and parent_appid <= 0:
                    parent_appid = None

                delisted_blank = (not name) and (type_int is None)

                plats_raw = item.get("platforms")
                tags: set[str] = set()
                if isinstance(plats_raw, dict):
                    if plats_raw.get("windows"):
                        tags.add("windows")
                    if plats_raw.get("mac"):
                        tags.add("macos")
                    if plats_raw.get("steamos_linux") or plats_raw.get("linux"):
                        tags.add("linux")
                if not tags:
                    tags = {"_unknown"}

                type_str = ""
                if isinstance(type_int, int):
                    type_str = {
                        0: "game",
                        2: "dlc",
                        3: "demo",
                        4: "dlc",
                        5: "advertising",
                        6: "mod",
                        7: "tool",
                        9: "video",
                        10: "video",
                        11: "video",
                        12: "video",
                        13: "music",
                        14: "rerelease",
                        15: "video",
                    }.get(type_int, str(type_int))

                cached = {
                    "platforms": tags,
                    "type": type_str,
                    "parent_appid": parent_appid,
                    "delisted_blank": delisted_blank,
                }
                _platform_cache_put(aid, cached)
                out[aid] = cached
            for aid in chunk:
                if aid not in seen:
                    cached = dict(blank_default)
                    _platform_cache_put(aid, cached)
                    out[aid] = cached
            consecutive_failures = 0
        except Exception as e:
            logger.debug("Steam GetItems lookup failed for chunk starting at %s: %s", chunk[0], e)
            consecutive_failures += 1
            for aid in chunk:
                cached = dict(blank_default)
                _platform_cache_put(aid, cached)
                out[aid] = cached
    return out


def _fetch_steam_image_urls(app_ids):
    """Batch-fetch canonical image URLs via Steam IStoreBrowseService/GetItems/v1.

    Returns (images, types, nsfw_map) where:
      images:   dict mapping appid (int) -> canonical URL string
      types:    dict mapping appid (int) -> Steam app type int
                  (1=game, 2=dlc, 3=demo, 13=music, etc.)
      nsfw_map: dict mapping appid (int) -> bool (True if NSFW content descriptors detected)
    On any network or parse error returns ({}, {}, {}) so callers fall back gracefully.
    """
    if not app_ids:
        return {}, {}, {}
    result = {}
    types = {}
    nsfw_map = {}
    try:
        payload = {
            "ids": [{"appid": aid} for aid in app_ids],
            "context": {"language": "english", "country_code": "US"},
            "data_request": {"include_assets": True, "include_content_descriptors": True},
        }
        url = (
            "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json="
            + _urlparse.quote(json.dumps(payload, separators=(",", ":")))
        )
        from sff.gui.web_bridge import _get_ssl_ctx
        request = _req.Request(url, headers={"User-Agent": "SteaMidra/5.4.0"})
        with _req.urlopen(request, timeout=5, context=_get_ssl_ctx()) as resp:
            data = json.loads(resp.read())
        _NSFW_CD_IDS = frozenset({1, 2, 3, 4})
        for item in data.get("response", {}).get("store_items", []):
            appid = item.get("appid")
            header = (item.get("assets") or {}).get("header", "")
            if appid and header:
                result[appid] = (
                    f"https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/{header}"
                )
            if appid:
                types[appid] = int(item.get("type") or 1)
                cd_ids = (item.get("content_descriptors") or {}).get("ids") or []
                nsfw_map[appid] = any(cid in _NSFW_CD_IDS for cid in cd_ids)
    except Exception as e:
        logger.debug("Steam image batch fetch failed: %s", e)
    return result, types, nsfw_map


# ---------------------------------------------------------------------------
# Bridge functions — converted from WebBridge methods (``self`` → ``bridge``)
# ---------------------------------------------------------------------------

def _bridge_refresh_store_metadata(bridge):
    def _do():
        return _ensure_fallback_loaded(force=False)

    def _on_done(ok):
        bridge._emit_task_result(
            "store_metadata",
            bool(ok),
            "",
            has_fallback_data=has_fallback_data(),
        )

    bridge._run_async(_do, on_done=_on_done)


def _bridge_warm_store_metadata(bridge):
    if getattr(bridge, "_store_metadata_warming", False):
        return
    bridge._store_metadata_warming = True

    def _do():
        from sff.game_list_fallback import ensure_loaded_cached
        return ensure_loaded_cached()

    def _finished(_result=None):
        bridge._store_metadata_warming = False

    bridge._run_async(_do, on_done=_finished, on_error=_finished)


def _bridge_search_games(bridge, query, offset, per_page, sort_by='updated', tag='', request_id=''):
    """Search Steam catalog (primary), then merge fresh hits from
    Hubcap on top.

    Steam's IStoreService catalog is the authoritative source for
    active titles. Hubcap fills in delisted classics (the original
    GTA: San Andreas, GTA Legacy Collection, etc) and exposes a
    manifest-status overlay for matched titles. Both /library and
    /search are queried, and the user query is alias-expanded
    ("gta" -> "grand theft auto", "re" -> "resident evil", ...)
    before being sent to Hubcap so abbreviated typing still hits
    full Hubcap names. Hubcap-only hits are tagged with
    source='hubcap' so the UI can label them. When Steam returns
    nothing, Hubcap becomes the primary result set.

    When tag is set with no query, uses games.json tag search instead.
    """
    # Search/filter clicks can arrive faster than the Steam/Hubcap request can
    # finish. Keep one worker in flight and retain only the newest intent;
    # spawning an unbounded QThread per click was a major source of memory
    # growth and made the Store appear frozen under rapid navigation.
    request_args = (query, offset, per_page, sort_by, tag, request_id)
    if getattr(bridge, "_store_search_in_flight", False):
        bridge._pending_store_search = request_args
        return
    bridge._store_search_in_flight = True

    def _do():
        block_nsfw = _store_blocks_nsfw()
        if block_nsfw and _looks_nsfw_by_name(query):
            return {
                "games": [],
                "total": 0,
                "has_hubcap": bool(bridge._get_store_client()),
                "has_fallback_data": has_fallback_data(),
            }

        # When filtering by tag with no text query, use games.json tag search
        if tag and not query:
            result = search_games_by_tag(tag, 0, 10000)
            rows = result.get("games", [])
            if block_nsfw:
                rows = _filter_store_nsfw_rows(rows)
            result["total"] = len(rows)
            result["games"] = rows[offset:offset + per_page]
            result['has_hubcap'] = False
            return result

        # The unfiltered landing page must be instant and offline-first.
        # Building IStoreService's full ~190k app list here used to hold the
        # Store on its loading state for 30+ seconds on every cold launch.
        if not query:
            result = browse_games_json(
                offset=offset,
                per_page=per_page,
                sort_by=sort_by or 'updated',
                block_nsfw=block_nsfw,
            )
            result.pop('fallback', None)
            result['has_hubcap'] = bool(getattr(bridge, '_store_client', None)) and not bridge._hubcap_unavailable
            result['has_fallback_data'] = has_fallback_data()
            return result

        # Steam catalog is always the primary source.
        result = _search_steam_catalog(query, offset, per_page, sort_by=sort_by or 'updated')
        result.pop('fallback', None)
        if not has_fallback_data():
            _ensure_fallback_loaded()
        for g in result.get('games', []) or []:
            enrich_game_dict(g)

        client = bridge._get_store_client()
        if not client:
            result['has_hubcap'] = False
            client = None

        result['has_hubcap'] = bool(client) and not bridge._hubcap_unavailable
        hubcap_hits = {}
        if client and not bridge._hubcap_unavailable:
            hubcap_hits = {}
            hubcap_queries = []
            if query:
                hubcap_queries.append(query)
                alts = _alias_expanded_queries(query)
                if alts:
                    for alt in alts:
                        if alt.lower() != query.lower():
                            hubcap_queries.append(alt)
                            break
            else:
                hubcap_queries = [None]
            hubcap_queried = False
            try:
                for q in hubcap_queries:
                    try:
                        page = client.get_library(
                            limit=200, offset=0,
                            search=q,
                            sort_by=sort_by or 'updated',
                        )
                        hubcap_queried = True
                        for hg in page.games or []:
                            if hg.app_id and hg.app_id not in hubcap_hits:
                                hubcap_hits[hg.app_id] = hg
                    except Exception as e:
                        logger.debug("Hubcap /library failed for %r: %s", q, e)
                    if q:
                        try:
                            search_hits = client.search_library(
                                q, limit=50, search_by_appid=False,
                            )
                            hubcap_queried = True
                            for hg in search_hits or []:
                                if hg.app_id and hg.app_id not in hubcap_hits:
                                    hubcap_hits[hg.app_id] = hg
                        except Exception as e:
                            logger.debug("Hubcap /search failed for %r: %s", q, e)
            except Exception as e:
                logger.warning("Hubcap merge step crashed: %s", e)
            # Hubcap was hit but returned nothing — key may be invalid.
            # Only disable after two consecutive empty queries to avoid
            # bricking the session on a single transient API hiccup.
            if hubcap_queried and not hubcap_hits:
                _ec = getattr(bridge, '_hubcap_empty_count', 0) + 1
                bridge._hubcap_empty_count = _ec
                if _ec >= 2:
                    bridge._hubcap_unavailable = True
                    bridge._hubcap_empty_count = 0
                    logger.debug("Hubcap disabled for session (no results from valid query)")
            else:
                bridge._hubcap_empty_count = 0
        if not hubcap_hits:
            logger.debug(
                "search_games: query=%r yielded no Hubcap hits across %d variant(s)",
                query, len(queries) if 'queries' in dir() else 1,
            )
            hubcap_hits = {}

        # Structural DLC + platform filter for Hubcap-only candidates.
        # Three drop signals, all derived from Steam's GetItems:
        #
        #   1. parent_appid is set  -> Steam tags this as DLC of
        #      another app. Drops Cyberpunk Phantom Liberty,
        #      RE6 Predator/Onslaught modes, RE Op Raccoon Echo
        #      Six Expansion 1, Elden Ring Shadow of the Erdtree,
        #      etc.
        #   2. delisted_blank is True  -> GetItems returned no
        #      name and no type. Steam strips public metadata
        #      from removed DLC content (RE6 Mercenaries No
        #      Mercy, RE5 Stories Bundle, RE4 weapon tickets).
        #      Real classic delisted GAMES still return
        #      name + type=0 (verified for GTA SA classic, Dark
        #      Souls PTDE, Resident Evil HD), so this signal is
        #      reliably DLC content.
        #   3. platforms set excludes "windows"  -> macOS-only or
        #      Linux-only port (e.g. appid 12250 GTA SA Mac).
        #
        # No name keywords. Steam-confirmed appids that already
        # appear in the Steam catalog result skip the filter
        # entirely so we trust Steam's own listing.
        steam_ids = {g.get('app_id') for g in result.get('games', []) or []}
        extra_ids = [aid for aid in hubcap_hits.keys() if aid not in steam_ids]
        meta_map = _fetch_steam_platforms(extra_ids)
        non_windows_filtered = 0
        dlc_filtered = 0
        kept_hubcap = {}
        for app_id, hg in hubcap_hits.items():
            if int(app_id or 0) in _KNOWN_MACOS_ONLY_APPIDS:
                non_windows_filtered += 1
                continue
            if app_id in steam_ids:
                kept_hubcap[app_id] = hg
                continue
            meta = meta_map.get(app_id) or {}
            tags = meta.get("platforms") or {"_unknown"}
            parent_appid = meta.get("parent_appid")
            delisted_blank = bool(meta.get("delisted_blank"))
            store_type = (meta.get("type") or "").lower()

            # search filter logs are gated behind SFF_VERBOSE_FILTER=1.
            # default off because the live debug.log was getting
            # thousands of identical "filtered Hubcap appid=..." lines
            # per tab switch and burying real errors.
            _verbose_filter = os.environ.get("SFF_VERBOSE_FILTER") == "1"

            # Structural DLC signals.
            if parent_appid:
                # Re-releases (Enhanced / Definitive / GOTY /
                # Director's Cut) hang off the base appid the same
                # way DLC does, but ship as standalone games.
                # Steam tags them with `type: 14` (rerelease).
                # Keep those; drop everything else with a parent.
                if store_type == "rerelease":
                    kept_hubcap[app_id] = hg
                    continue
                dlc_filtered += 1
                if _verbose_filter:
                    logger.debug(
                        "search_games: filtered Hubcap appid=%s name=%r parent=%s",
                        app_id, hg.name, parent_appid,
                    )
                continue
            if delisted_blank:
                dlc_filtered += 1
                if _verbose_filter:
                    logger.debug(
                        "search_games: filtered Hubcap appid=%s name=%r (delisted, no Steam metadata)",
                        app_id, hg.name,
                    )
                continue
            # Belt-and-suspenders type drop. parent_appid covers
            # type=2/4 already. This catches edge cases where
            # GetItems returns type=5/7/9-15 (advertising, tool,
            # video, music) without a parent appid. Re-releases
            # (`type: 14` with parent set) are handled above.
            if store_type and store_type not in ("game", "demo", "mod", "rerelease"):
                dlc_filtered += 1
                if _verbose_filter:
                    logger.debug(
                        "search_games: filtered Hubcap appid=%s name=%r type=%s",
                        app_id, hg.name, store_type,
                    )
                continue

            # Platform check.
            if "_unknown" not in tags:
                _is_win = sys.platform == "win32"
                if _is_win and "windows" not in tags:
                    non_windows_filtered += 1
                    if _verbose_filter:
                        logger.debug(
                            "search_games: filtered Hubcap appid=%s name=%r platforms=%s",
                            app_id, hg.name, sorted(tags),
                        )
                    continue
                if not _is_win and "windows" not in tags and "linux" not in tags:
                    non_windows_filtered += 1
                    if _verbose_filter:
                        logger.debug(
                            "search_games: filtered Hubcap appid=%s name=%r platforms=%s",
                            app_id, hg.name, sorted(tags),
                        )
                    continue
                # on Linux, tag win-only games with a badge
                if not _is_win and "linux" not in tags and "windows" in tags:
                    hg._plat_label = "[Win]"
                elif not _is_win and "linux" in tags and "windows" not in tags:
                    hg._plat_label = "[Linux]"

            kept_hubcap[app_id] = hg
        hubcap_hits = kept_hubcap

        try:
            logger.debug(
                "search_games: query=%r got %d Steam + %d Hubcap hit(s) across %d variant(s) (%d DLC filtered, %d non-windows filtered)",
                query, len(result.get('games', [])), len(hubcap_hits),
                len(queries), dlc_filtered, non_windows_filtered,
            )
        except (NameError, UnboundLocalError):
            logger.debug(
                "search_games: query=%r got %d Steam + %d Hubcap hit(s)",
                query, len(result.get('games', [])), len(hubcap_hits),
            )

        # Overlay Hubcap status on Steam rows that share an app_id.
        for g in result.get('games', []) or []:
            hg = hubcap_hits.get(g.get('app_id'))
            if not hg:
                continue
            if hg.status:
                g['status'] = hg.status
            if hg.last_updated:
                g['last_updated'] = hg.last_updated
            if hg.size:
                g['size'] = hg.size

        # Build the Hubcap-only tail. The merged result behaves
        # like one virtual list: [steam_total Steam rows] then
        # [len(extras) Hubcap rows]. Pagination has to slice that
        # combined list per page; otherwise every page repeats
        # the full Hubcap tail (the bug we used to ship).
        seen_ids = {g.get('app_id') for g in result.get('games', []) or []}
        extras = []
        for app_id, hg in hubcap_hits.items():
            if app_id in seen_ids:
                continue
            extras.append({
                'app_id': hg.app_id,
                'name': hg.name,
                'status': hg.status or '',
                'last_updated': hg.last_updated or '',
                'size': hg.size or '',
                'image_url': '',
                'source': 'hubcap',
                'platform_label': getattr(hg, '_plat_label', ''),
            })

        steam_total = int(result.get('total') or 0)
        steam_rows = result.get('games') or []
        extras_total = len(extras)

        # Enrich ALL rows with games.json metadata (DRM, tags, NSFW,
        # header_image, DLC). This runs on every search but the
        # underlying cache is lazy-loaded and re-checks mtime.
        _ensure_fallback_loaded()
        for g in steam_rows:
            enrich_game_dict(g)
        for g in extras:
            enrich_game_dict(g)

        # Merge games.json + name-cache results so delisted/removed
        # games show up even when Steam + Hubcap return active titles.
        # Use alias expansion so "gta" -> "grand theft auto" hits
        # titles stored under their full name. Runs unconditionally;
        # search_games_json / search_name_fallback return empty lists
        # when the underlying data hasn't been loaded.
        if query:
            try:
                queries = _alias_expanded_queries(query) or [query]
                gj_extra = {}
                for q in queries:
                    try:
                        for g in search_games_json(q, limit=500):
                            if g.get('app_id') and g['app_id'] not in gj_extra:
                                gj_extra[g['app_id']] = g
                    except Exception:
                        pass
                    try:
                        for g in search_name_fallback(q, limit=500):
                            if g.get('app_id') and g['app_id'] not in gj_extra:
                                gj_extra[g['app_id']] = g
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("search_games: fallback merge failed: %s", e)
                gj_extra = {}
            if gj_extra:
                existing_ids = {g.get('app_id') for g in steam_rows if g.get('app_id')}
                existing_ids.update(e.get('app_id') for e in extras if e.get('app_id'))
                for app_id in list(gj_extra.keys()):
                    if app_id not in existing_ids:
                        g = gj_extra[app_id]
                        enrich_game_dict(g)
                        steam_rows.append(g)
                        steam_total += 1
                        existing_ids.add(app_id)
                if gj_extra:
                    logger.debug("search_games: merged %d extra games from JSON sources", len(gj_extra))

        # Platform filter for ALL search result rows. Uses Steam GetItems
        # platform data (cached in _STEAM_PLATFORM_CACHE) to drop
        # macOS-only games and tag Linux-specific / Windows-specific titles
        # with a readable label for Linux users.
        _is_win = sys.platform == "win32"
        _all_aids = []
        for g in steam_rows:
            aid = g.get('app_id')
            if aid:
                _all_aids.append(aid)
        for e in extras:
            aid = e.get('app_id')
            if aid:
                _all_aids.append(aid)
        if _all_aids:
            _plat_map = _fetch_steam_platforms(_all_aids)
            if _plat_map:
                _filtered_rows = []
                for g in steam_rows:
                    aid = g.get('app_id')
                    if int(aid or 0) in _KNOWN_MACOS_ONLY_APPIDS:
                        continue
                    meta = _plat_map.get(aid) if aid else None
                    tags = meta.get("platforms") if meta else {"_unknown"}
                    if "_unknown" in tags:
                        g['platform_label'] = ''
                        _filtered_rows.append(g)
                        continue
                    has_win = "windows" in tags
                    has_lin = "linux" in tags
                    has_mac = "macos" in tags
                    if has_mac and not has_win and not has_lin:
                        continue
                    if _is_win:
                        if not has_win:
                            continue
                        g['platform_label'] = ''
                    else:
                        if not has_win and not has_lin:
                            continue
                        if has_lin and not has_win:
                            g['platform_label'] = '[Linux Only]'
                        elif has_win and not has_lin:
                            g['platform_label'] = '[Windows Only]'
                        else:
                            g['platform_label'] = ''
                    _filtered_rows.append(g)
                steam_rows = _filtered_rows
                steam_total = len(steam_rows)
                _filtered_extras = []
                for e in extras:
                    aid = e.get('app_id')
                    if int(aid or 0) in _KNOWN_MACOS_ONLY_APPIDS:
                        continue
                    meta = _plat_map.get(aid) if aid else None
                    tags = meta.get("platforms") if meta else {"_unknown"}
                    if "_unknown" in tags:
                        e['platform_label'] = e.get('platform_label', '')
                        _filtered_extras.append(e)
                        continue
                    has_win = "windows" in tags
                    has_lin = "linux" in tags
                    has_mac = "macos" in tags
                    if has_mac and not has_win and not has_lin:
                        continue
                    if _is_win and not has_win:
                        continue
                    if not _is_win and not has_win and not has_lin:
                        continue
                    _filtered_extras.append(e)
                extras = _filtered_extras
                extras_total = len(extras)

        # Merge into one list, dedupe, then filter/sort/paginate once.
        merged = []
        seen_merged = set()
        for row in list(steam_rows) + list(extras):
            aid = row.get('app_id')
            if not aid or aid in seen_merged:
                continue
            seen_merged.add(aid)
            merged.append(row)

        # Fetch Steam content descriptors only when games.json did not
        # provide NSFW/art metadata.
        if merged and not has_fallback_data():
            try:
                _meta_img, _, _meta_nsfw = _fetch_steam_image_urls([
                    g['app_id'] for g in merged if g.get('app_id')
                ])
            except Exception as e:
                logger.debug("search_games: Steam metadata fetch failed: %s", e)
                _meta_img, _meta_nsfw = {}, {}
            for g in merged:
                aid = g.get('app_id')
                if aid and aid in _meta_nsfw:
                    g['nsfw'] = _meta_nsfw[aid]
                if aid and not g.get('image_url'):
                    g['image_url'] = _meta_img.get(aid) or ''

        # Filter by tag when both tag and text query are set.
        if tag and query:
            tag_lower = tag.lower().strip()
            merged = [
                g for g in merged
                if tag_lower in [t.lower() for t in g.get('tags', [])]
            ]

        if block_nsfw:
            merged = _filter_store_nsfw_rows(merged)

        if not merged:
            # Both Steam catalog and Hubcap came back empty. Try
            # games.json + name-cache directly as a last resort so
            # the store tab never shows a completely blank page.
            if has_fallback_data():
                _last_resort = []
                if query:
                    for g in search_games_json(query, limit=500):
                        _last_resort.append(g)
                    for g in search_name_fallback(query, limit=500):
                        _last_resort.append(g)
                else:
                    for g in search_games_json("", limit=200):
                        _last_resort.append(g)
                if _last_resort:
                    seen_lr = set()
                    _deduped = []
                    for g in _last_resort:
                        aid = g.get('app_id')
                        if not aid or aid in seen_lr:
                            continue
                        seen_lr.add(aid)
                        enrich_game_dict(g)
                        _deduped.append(g)
                    if _deduped:
                        _deduped.sort(key=lambda g: _store_search_score(
                            query,
                            g.get('name', ''),
                            g.get('app_id'),
                        ))
                        result['games'] = _deduped[offset:offset + per_page]
                        result['total'] = len(_deduped)
                        result['fallback_source'] = 'games_json'
                        result['has_fallback_data'] = True
            return result

        merged.sort(key=lambda g: _store_search_score(query, g.get('name', ''), g.get('app_id')))
        total = len(merged)
        if not query and not tag:
            total = max(total, int(result.get('total') or 0))
        page_games = merged[offset:offset + per_page]
        if not result.get('games') and any(g.get('source') == 'hubcap' for g in page_games):
            result['fallback_source'] = 'hubcap'
        result['games'] = page_games
        result['total'] = total

        # Annotate with crack file BuildIDs so users know which version
        # to download for crack compatibility
        try:
            _cr_buildids = _get_crack_buildid_map()
            for g in page_games:
                name = str(g.get('name', '') or '').strip().lower()
                if name and name in _cr_buildids:
                    g['crack_buildid'] = _cr_buildids[name]
        except Exception:
            pass

        result['has_fallback_data'] = True
        # User searched for something specific but nothing matched.
        # Force-refresh the fallback cache in background so next
        # search picks up fresh game data.
        if query and not merged:
            QTimer.singleShot(200, lambda: _ensure_fallback_loaded(force=True))
        return result

    def _start_pending():
        bridge._store_search_in_flight = False
        pending = getattr(bridge, "_pending_store_search", None)
        bridge._pending_store_search = None
        if pending:
            QTimer.singleShot(0, lambda args=pending: _bridge_search_games(bridge, *args))

    def _on_done(data):
        _rjson = json.dumps(_attach_store_request_id(data, request_id))
        bridge.search_results.emit(_rjson)
        _start_pending()

    def _on_error(message):
        logger.warning("Store search failed: %s", message)
        bridge.search_results.emit(json.dumps({
            "games": [],
            "total": 0,
            "request_id": str(request_id or ""),
            "error": str(message or "Store search failed"),
        }))
        _start_pending()

    bridge._run_async(_do, on_done=_on_done, on_error=_on_error)


def _bridge_connect_store(bridge, api_key):
    """Validates and stores Hubcap API key."""
    if not api_key or not api_key.strip():
        bridge._emit_task_result("store_connect", False, "API key is empty")
        return
    from sff.network.store_browser import StoreApiClient
    if not StoreApiClient.validate_api_key(api_key):
        bridge._emit_task_result("store_connect", False, "API key rejected by Hubcap. Check your key or try again.")
        return
    bridge._api_key = api_key
    bridge._store_client = StoreApiClient(api_key)
    bridge._hubcap_unavailable = False
    from sff.core.storage.settings import set_setting, clear_setting
    from sff.core.structs import Settings
    set_setting(Settings.HUBCAP_KEY, api_key)
    try:
        clear_setting(Settings.HUBCAP_DISABLED)
    except Exception:
        pass
    bridge.task_finished.emit(json.dumps({"task": "api_key_connected"}))


def _bridge_store_disconnect(bridge):
    """Disconnect Hubcap store — fall back to Steam search (key stays saved)."""
    bridge._store_client = None
    bridge._api_key = None
    bridge._hubcap_unavailable = True
    try:
        from sff.core.storage.settings import set_setting
        from sff.core.structs import Settings
        set_setting(Settings.HUBCAP_DISABLED, True)
    except Exception:
        pass
    bridge.task_finished.emit(json.dumps({"task": "store_disconnected"}))


def _bridge_update_store_lists(bridge):
    """Download all store data sources: all_games.txt + games.json + name cache.
    Emits task_finished('store_metadata_refresh')."""
    def _do():
        from sff.game_list_fallback import ensure_loaded as _fallback_loaded
        from sff.core.utils import root_folder
        from sff.core.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
        from sff.core.storage.settings import get_setting
        from sff.core.structs import Settings
        from sff.gui.web_bridge import _should_show_software, _get_ssl_ctx
        ok_steam = False
        ok_json = False
        results = []
        # 1) Download all_games.txt via IStoreService API
        try:
            all_games_file = root_folder(outside_internal=True) / "all_games.txt"
            api_key = get_setting(Settings.STEAM_WEB_API_KEY)
            if not isinstance(api_key, str) or not api_key.strip():
                api_key = _DEFAULT_KEY
            params = {"key": api_key, "max_results": "50000", "include_games": "1",
                       "include_dlc": "0", "include_software": _should_show_software(),
                       "include_videos": "0", "include_hardware": "0"}
            games = []
            base_url = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
            while True:
                query_str = "&".join(f"{k}={v}" for k, v in params.items())
                url = f"{base_url}?{query_str}"
                req2 = _req.Request(url, headers={"User-Agent": "SteaMidra/6.1.0"})
                with _req.urlopen(req2, timeout=30, context=_get_ssl_ctx()) as resp:
                    data = json.loads(resp.read())
                apps = data.get("response", {}).get("apps", [])
                games.extend(apps)
                if not data.get("response", {}).get("have_more_results"):
                    break
                last_id = data.get("response", {}).get("last_appid")
                if last_id:
                    params["last_appid"] = str(last_id)
                else:
                    break
            games_str = [
                x.get("name", "UNKNOWN GAME") + f" [ID={x.get('appid')}]"
                for x in games if x.get("appid") and x.get("name", "").strip()
            ]
            all_games_file.parent.mkdir(parents=True, exist_ok=True)
            with all_games_file.open("w", encoding="utf-8") as f:
                f.write("\n".join(games_str))
            ok_steam = True
            results.append(f"all_games.txt: {len(games_str)} games")
            logger.debug("Store list update: all_games.txt written (%d games)", len(games_str))
        except Exception as e:
            logger.warning("Store list update: all_games.txt failed: %s", e)
            results.append(f"all_games.txt failed: {e}")
        # 2) Force-refresh games.json + name cache (games_appid.json, software_appid.json)
        try:
            _fallback_loaded(force=True)
            from sff.game_list_fallback import metadata_counts
            counts = metadata_counts()
            games_count = counts.get("games", 0)
            names_count = counts.get("names", 0)
            dlc_count = counts.get("dlc_names", 0)
            ok_json = bool(games_count or names_count or dlc_count)
            results.append(
                f"games.json: {games_count} entries, app/software names: {names_count}, DLC names: {dlc_count}"
            )
            logger.debug(
                "Store list update: JSON sources refreshed (%d games, %d names, %d DLC names)",
                games_count, names_count, dlc_count,
            )
        except Exception as e:
            logger.warning("Store list update: JSON sources failed: %s", e)
            results.append(f"JSON sources failed: {e}")
        # Also invalidate the Steam applist in-memory cache so next search re-reads
        global _STEAM_APPLIST_CACHE, _STEAM_APPLIST_CACHE_TIME
        _STEAM_APPLIST_CACHE = None
        _STEAM_APPLIST_CACHE_TIME = 0
        return (ok_steam or ok_json, "; ".join(results))

    def _on_done(result):
        if isinstance(result, tuple) and len(result) == 2:
            ok, msg = result
        else:
            ok, msg = True, str(result)
        bridge._emit_task_result(
            "store_metadata_refresh",
            ok,
            msg or ("Store lists updated" if ok else "Failed to update store lists"),
        )

    bridge._run_async(_do, on_done=_on_done)


def _bridge_search_games_file(bridge, query):
    """Search all_games.txt by name. Returns JSON [{name, appid}, ...] max 200 results.

    Falls back to the Hubcap library when the local catalog returns
    zero hits AND a Hubcap API key is configured. The Hubcap library
    carries delisted titles (San Andreas, LEGO 2K Drive) that the
    Steam IStoreService applist no longer surfaces; users who own
    those titles can still install them, so they are addable from
    the home page filter.
    """
    from sff.core.utils import root_folder
    all_games_file = root_folder(outside_internal=True) / "all_games.txt"
    if not all_games_file.exists():
        bridge.update_games_file()
        return json.dumps([{"name": "Game list not found — downloading now. Please search again in a moment.", "appid": "0"}])

    # Cache parsed lines in memory so subsequent searches skip file I/O
    _cache = getattr(bridge, '_allgames_cache', None)
    if _cache is None:
        _id_re = re.compile(r"\[ID=(\d+)\]$")
        _cache = []
        try:
            with all_games_file.open(encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    m = _id_re.search(line)
                    if m:
                        _cache.append((line[:m.start()].strip(), m.group(1)))
        except Exception:
            return "[]"
        bridge._allgames_cache = _cache

    try:
        q_norm = _normalize_for_search(query)
        results = []
        for name, appid in _cache:
            if _matches_normalized(q_norm, _normalize_for_search(name)):
                results.append({"name": name, "appid": appid})
            if len(results) >= 200:
                break

        # Hubcap fallback for delisted games. The Steam applist drops
        # titles that have been removed from the store (San Andreas,
        # LEGO 2K Drive, etc.) but the games are still installable for
        # owners. Hubcap's library tracks them, so when the local file
        # has nothing and a key is configured, ask Hubcap. The user
        # query is alias-expanded ("gta" -> "grand theft auto", etc)
        # before being sent so abbreviated typing still hits Hubcap's
        # full game names. macOS-only / Linux-only entries are
        # dropped via Steam's appdetails endpoint.
        if not results and query and query.strip():
            try:
                client = bridge._get_store_client()
                if client is not None:
                    seen_ids = set()
                    candidates = []
                    for q in _alias_expanded_queries(query):
                        try:
                            hubcap_result = client.get_library(
                                limit=200, offset=0,
                                search=q, sort_by='updated',
                            )
                            for hg in (hubcap_result.games or []):
                                if not (hg.app_id and hg.name):
                                    continue
                                if hg.app_id in seen_ids:
                                    continue
                                seen_ids.add(hg.app_id)
                                candidates.append(hg)
                        except Exception as e:
                            logger.debug(
                                "Hubcap /library failed for %r: %s", q, e,
                            )
                        if len(candidates) >= 200:
                            break
                    plat_map = _fetch_steam_platforms(
                        [hg.app_id for hg in candidates]
                    )
                    for hg in candidates:
                        meta = plat_map.get(hg.app_id) or {}
                        tags = meta.get("platforms") or {"_unknown"}
                        store_type = (meta.get("type") or "").lower()
                        parent_appid = meta.get("parent_appid")
                        delisted_blank = bool(meta.get("delisted_blank"))
                        # Structural DLC drops: parent appid set
                        # (and not a re-release), blank delisted
                        # entry, or non-game type.
                        if parent_appid and store_type != "rerelease":
                            continue
                        if delisted_blank:
                            continue
                        if store_type and store_type not in ("game", "demo", "mod", "rerelease"):
                            continue
                        # Drop non-Windows-only entries.
                        if "_unknown" not in tags and "windows" not in tags:
                            continue
                        results.append({
                            "name": str(hg.name),
                            "appid": str(hg.app_id),
                        })
                        if len(results) >= 200:
                            break
                    if results:
                        logger.info(
                            "search_games_file: local catalog miss for %r; "
                            "Hubcap fallback returned %d entries",
                            query, len(results),
                        )
            except Exception as exc:
                logger.debug("Hubcap fallback in search_games_file failed: %s", exc)

        return json.dumps(results)
    except Exception as e:
        logger.debug("search_games_file failed: %s", e)
        return "[]"
