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

"""Depot manifest version history — multi-source chain with session+disk caching."""

import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_MIRROR_OWNER = "qwe213312"
_MIRROR_REPO = "k25FCdfEOoEJ42S6"
_GH_API = "https://api.github.com"
_TREE_TTL = 3600
_RESULT_TTL = 300

_TREE = None
_TREE_FETCHED_AT = 0.0
_TREE_MAP = {}
_DATES = {}
_DATES_DIRTY = False
_RATE_REMAINING = 60
_RESULT_CACHE = {}

_CF_COOKIE_TTL = 3600  # 1 hour
_CF_COOKIE_CACHE = {}  # {cf_clearance, user_agent, saved_at}

_BUILD_IDS_CACHE: dict[str, dict[str, str]] = {}  # app_id -> {date -> build_id}


def _load_build_ids_cache(app_id: str) -> dict[str, str]:
    """Load build IDs from disk cache."""
    try:
        p = _sff_dir() / f"build_ids_{app_id}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("build_ids", {})
    except Exception:
        pass
    return {}


def _save_build_ids_cache(app_id: str, build_ids: dict[str, str]) -> None:
    """Persist build IDs to disk."""
    try:
        p = _sff_dir() / f"build_ids_{app_id}.json"
        p.write_text(json.dumps({
            "app_id": app_id,
            "build_ids": build_ids,
        }), encoding="utf-8")
    except Exception as exc:
        logger.debug("build_ids cache save error: %s", exc)


def get_build_ids(app_id: str) -> dict[str, str]:
    """Return cached {date -> build_id} mapping for an app, or empty dict."""
    app_id = str(app_id)
    if app_id in _BUILD_IDS_CACHE:
        return _BUILD_IDS_CACHE[app_id]
    # Try loading from disk
    disk = _load_build_ids_cache(app_id)
    if disk:
        _BUILD_IDS_CACHE[app_id] = disk
    return disk


def _parse_patchnotes_rss(xml_text: str) -> dict[str, str]:
    """Parse SteamDB PatchnotesRSS XML feed.

    Returns {date_str: build_id} mapping (YYYY-MM-DD -> build ID string).

    Each <item> has:
      <title>Build 11026049 – No title</title>  (or "Build 11026049 – Bug fix")
      <link>https://steamdb.info/patchnotes/11026049/</link>
      <pubDate>Mon, 08 May 2023 01:01:00 +0000</pubDate>
    """
    build_ids: dict[str, str] = {}
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            if link_el is None or pub_el is None:
                continue
            link = (link_el.text or "").strip()
            pub = (pub_el.text or "").strip()
            # Extract build ID from link: /patchnotes/11026049/
            bm = re.search(r"/patchnotes/(\d+)", link)
            if not bm:
                # Fallback: extract from <title>: "Build 11026049 – ..."
                title_el = item.find("title")
                if title_el is not None:
                    bm = re.search(r"Build\s+(\d+)", title_el.text or "")
            if not bm:
                continue
            bid = bm.group(1)
            # Parse pubDate: "Mon, 08 May 2023 01:01:00 +0000"
            # Extract date using email.utils or manual parse
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                # Manual fallback: find "DD Mon YYYY" in pubDate
                dm = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", pub)
                if not dm:
                    continue
                day, mon_abbr, year = dm.groups()
                _ABBR = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                         "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                         "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
                month = _ABBR.get(mon_abbr)
                if not month:
                    continue
                date_str = f"{year}-{month}-{int(day):02d}"
            build_ids.setdefault(date_str, bid)
    except Exception as exc:
        logger.debug("Patchnotes RSS parse error: %s", exc)
    return build_ids


def _ensure_build_ids(app_id: str) -> None:
    """Fetch build IDs from SteamDB PatchnotesRSS API.

    Uses the public RSS feed (no CF cookie needed, plain XML).
    Falls back to curl_cffi if httpx fails.
    """
    app_id = str(app_id)
    # Already in memory
    if app_id in _BUILD_IDS_CACHE:
        return
    # Already on disk
    disk = _load_build_ids_cache(app_id)
    if disk:
        _BUILD_IDS_CACHE[app_id] = disk
        logger.debug("Patchnotes: loaded %d build IDs for app %s from disk", len(disk), app_id)
        return

    rss_url = f"https://steamdb.info/api/PatchnotesRSS/?appid={app_id}"
    xml_text = ""

    # Try 1: httpx (no CF cookie needed for API)
    try:
        r = httpx.get(rss_url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "SteaMidra/5"})
        if r.status_code == 200:
            xml_text = r.text
    except Exception:
        pass

    # Try 2: curl_cffi with CF cookie
    if not xml_text:
        try:
            from curl_cffi import requests as curl_requests
            cf_c, cf_ua = _get_valid_cf_cookie()
            sess = curl_requests.Session(impersonate="chrome")
            resp = sess.get(
                rss_url,
                headers=_steamdb_headers_base(cf_ua),
                cookies={"cf_clearance": cf_c} if cf_c else {},
                timeout=15,
            )
            if resp.status_code == 200:
                xml_text = resp.text
            sess.close()
        except Exception:
            pass

    if not xml_text:
        logger.debug("Patchnotes: failed to fetch RSS for app %s", app_id)
        return

    bid = _parse_patchnotes_rss(xml_text)
    if bid:
        _BUILD_IDS_CACHE[app_id] = bid
        _save_build_ids_cache(app_id, bid)
        logger.debug("Patchnotes: %d build IDs for app %s — dates: %s",
                     len(bid), app_id, list(bid.keys()))
    else:
        logger.debug("Patchnotes: RSS returned 0 build IDs for app %s", app_id)


@dataclass
class ManifestEntry:
    manifest_id: str
    date: str
    branch: str = "public"
    size_mb: float = 0.0
    source: str = ""

    def __str__(self):
        size_str = f"  ({self.size_mb:.0f} MB)" if self.size_mb else ""
        return f"{self.date}  —  {self.manifest_id}  [{self.branch}]{size_str}"


# ---------------------------------------------------------------------------
# Persistent cache helpers
# ---------------------------------------------------------------------------

def _sff_dir():
    p = Path.home() / ".sff"
    p.mkdir(exist_ok=True)
    return p


def _load_dates_cache():
    global _DATES
    try:
        p = _sff_dir() / "github_dates.json"
        if p.exists():
            _DATES = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("dates cache load error: %s", exc)


def _save_dates_cache():
    global _DATES_DIRTY
    if not _DATES_DIRTY:
        return
    try:
        (_sff_dir() / "github_dates.json").write_text(json.dumps(_DATES), encoding="utf-8")
        _DATES_DIRTY = False
    except Exception as exc:
        logger.debug("dates cache save error: %s", exc)


_load_dates_cache()


# ---------------------------------------------------------------------------
# CF clearance cookie disk cache (Layer 2 fast path)
# ---------------------------------------------------------------------------

def _load_cf_cookie_cache():
    global _CF_COOKIE_CACHE
    try:
        p = _sff_dir() / "cf_cookie_cache.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if time.time() - data.get("saved_at", 0) < _CF_COOKIE_TTL:
                _CF_COOKIE_CACHE = data
    except Exception as exc:
        logger.debug("cf cookie cache load error: %s", exc)


def _save_cf_cookie_cache(cf_clearance: str, user_agent: str):
    global _CF_COOKIE_CACHE
    _CF_COOKIE_CACHE = {"cf_clearance": cf_clearance, "user_agent": user_agent, "saved_at": time.time()}
    try:
        (_sff_dir() / "cf_cookie_cache.json").write_text(
            json.dumps(_CF_COOKIE_CACHE), encoding="utf-8"
        )
    except Exception as exc:
        logger.debug("cf cookie cache save error: %s", exc)


# ---------------------------------------------------------------------------
# Per-app depot history disk cache
# Keyed by app_id; invalidated when Steam CM reports a new manifest for any depot.
# ---------------------------------------------------------------------------

_APP_CACHE_VERSION = 1


def _load_app_depot_cache(app_id: str):
    """Load cached depot history for *app_id*.

    Returns (depots_dict, None) where depots_dict maps depot_id -> list of raw
    entry dicts, or (None, None) on any error / version mismatch.
    """
    try:
        p = _sff_dir() / f"depot_cache_{app_id}.json"
        if not p.exists():
            return None, None
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("version") != _APP_CACHE_VERSION:
            return None, None
        return data.get("depots", {}), None
    except Exception as exc:
        logger.debug("depot cache load error for app %s: %s", app_id, exc)
        return None, None


def _save_app_depot_cache(app_id: str, result: dict):
    """Persist depot history for *app_id* to disk.

    *result* is {depot_id: [ManifestEntry, ...]} as returned by get_depots_for_app.
    """
    try:
        p = _sff_dir() / f"depot_cache_{app_id}.json"
        data = {
            "version": _APP_CACHE_VERSION,
            "app_id": app_id,
            "cached_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "depots": {
                depot_id: [
                    {
                        "manifest_id": e.manifest_id,
                        "date": e.date,
                        "branch": e.branch,
                        "size_mb": e.size_mb,
                        "source": e.source,
                    }
                    for e in entries
                ]
                for depot_id, entries in result.items()
            },
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Saved depot cache for app %s (%d depots)", app_id, len(result))
    except Exception as exc:
        logger.debug("depot cache save error for app %s: %s", app_id, exc)


def _get_valid_cf_cookie():
    """Return (cf_clearance, user_agent) if cache is fresh, else (None, None)."""
    if not _CF_COOKIE_CACHE:
        _load_cf_cookie_cache()
    data = _CF_COOKIE_CACHE
    if data and time.time() - data.get("saved_at", 0) < _CF_COOKIE_TTL:
        return data.get("cf_clearance"), data.get("user_agent")
    return None, None


# ---------------------------------------------------------------------------
# Local fallback data (loaded once at import)
# ---------------------------------------------------------------------------

def _load_local_fallbacks():
    lua_dir = Path(__file__).parent.parent / "lua"
    dk_ids = frozenset()
    tokens = {}
    try:
        dk = json.loads((lua_dir / "fallback_depotkeys.json").read_text(encoding="utf-8"))
        dk_ids = frozenset(dk.keys())
    except Exception as exc:
        logger.debug("fallback_depotkeys load error: %s", exc)
    try:
        raw = json.loads((lua_dir / "fallback_tokens.json").read_text(encoding="utf-8"))
        tokens = {k: v for k, v in raw.items() if k in dk_ids}
    except Exception as exc:
        logger.debug("fallback_tokens load error: %s", exc)
    return dk_ids, tokens


_DEPOT_KEY_IDS, _FALLBACK_TOKENS = _load_local_fallbacks()


# ---------------------------------------------------------------------------
# GitHub mirror tree (session + disk cached)
# ---------------------------------------------------------------------------

def _gh_headers():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github.v3+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _update_rate_limit(resp: httpx.Response):
    global _RATE_REMAINING
    try:
        _RATE_REMAINING = int(resp.headers.get("X-RateLimit-Remaining", _RATE_REMAINING))
    except Exception:
        pass


def _get_mirror_tree():
    """Return GitHub tree, fetching once per session (disk-backed with TTL)."""
    global _TREE, _TREE_FETCHED_AT, _TREE_MAP
    now = time.time()
    if _TREE is not None and (now - _TREE_FETCHED_AT) < _TREE_TTL:
        return _TREE
    disk = _sff_dir() / "mirror_tree_cache.json"
    if disk.exists():
        try:
            cached = json.loads(disk.read_text(encoding="utf-8"))
            if (now - cached.get("ts", 0)) < _TREE_TTL:
                _TREE = cached["tree"]
                _TREE_FETCHED_AT = cached["ts"]
                _TREE_MAP = _build_tree_map(_TREE)
                logger.debug("mirror tree loaded from disk (%d items)", len(_TREE))
                return _TREE
        except Exception:
            pass
    url = f"{_GH_API}/repos/{_MIRROR_OWNER}/{_MIRROR_REPO}/git/trees/main?recursive=1"
    try:
        resp = httpx.get(url, headers=_gh_headers(), timeout=30, follow_redirects=True)
        _update_rate_limit(resp)
        if resp.status_code == 200:
            _TREE = resp.json().get("tree", [])
            _TREE_FETCHED_AT = now
            _TREE_MAP = _build_tree_map(_TREE)
            try:
                disk.write_text(json.dumps({"ts": now, "tree": _TREE}), encoding="utf-8")
            except Exception:
                pass
            logger.debug("mirror tree fetched (%d items)", len(_TREE))
    except Exception as exc:
        logger.debug("mirror tree fetch failed: %s", exc)
    if _TREE is None:
        _TREE = []
    return _TREE


def _build_tree_map(tree):
    result = {}
    for item in tree:
        m = re.match(r"^(\d+)_(\d+)\.manifest$", item.get("path", ""))
        if m:
            result.setdefault(m.group(1), []).append(m.group(2))
    return result


def _fetch_file_date(filename):
    """Fetch commit date for one mirror file. Rate-limited; cached persistently."""
    global _DATES_DIRTY
    if filename in _DATES:
        return _DATES[filename]
    if _RATE_REMAINING < 3:
        logger.debug("GitHub rate limit low (%d), skipping date fetch", _RATE_REMAINING)
        return "N/A"
    url = f"{_GH_API}/repos/{_MIRROR_OWNER}/{_MIRROR_REPO}/commits"
    try:
        resp = httpx.get(
            url,
            params={"path": filename, "per_page": 1},
            headers=_gh_headers(),
            timeout=12,
            follow_redirects=True,
        )
        _update_rate_limit(resp)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                date = data[0]["commit"]["committer"]["date"][:10]
                _DATES[filename] = date
                _DATES_DIRTY = True
                _save_dates_cache()
                return date
    except Exception as exc:
        logger.debug("date fetch failed for %s: %s", filename, exc)
    return "N/A"


# ---------------------------------------------------------------------------
# Source 1 — Steam CM
# ---------------------------------------------------------------------------

def _fetch_steam_cm_entries(app_id):
    """Get depot IDs + current manifests with real dates from Steam CM."""
    result = {}
    try:
        from sff.steam_client import create_provider_for_current_thread
        prov = create_provider_for_current_thread()
        app_data = prov.get_single_app_info(int(app_id))
        if not app_data:
            return result
        depots_raw = app_data.get("depots", {})
        branches_meta = depots_raw.get("branches", {})
        for branch_name, branch_info in branches_meta.items():
            if not isinstance(branch_info, dict):
                continue
            ts = branch_info.get("timeupdated")
            branch_date = "unknown"
            if ts:
                try:
                    branch_date = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                except Exception:
                    pass
            for depot_id, depot_data in depots_raw.items():
                if not str(depot_id).isdigit() or not isinstance(depot_data, dict):
                    continue
                gid = depot_data.get("manifests", {}).get(branch_name, {}).get("gid")
                if gid:
                    result.setdefault(str(depot_id), []).append(ManifestEntry(
                        manifest_id=str(gid),
                        date=branch_date,
                        branch=branch_name,
                        source="Steam CM",
                    ))
        # DLC depot fetching: read extended.listofdlc and pull depots from each DLC app
        try:
            dlc_raw = app_data.get("extended", {}).get("listofdlc", "")
            if dlc_raw:
                dlc_app_ids = [int(x.strip()) for x in str(dlc_raw).split(",") if x.strip().isdigit()]
                if dlc_app_ids:
                    dlc_info = prov.get_app_info(dlc_app_ids)
                    for _dlc_appid, dlc_data in (dlc_info or {}).items():
                        dlc_depots = dlc_data.get("depots", {})
                        dlc_branches = dlc_depots.get("branches", {})
                        for b_name, b_info in dlc_branches.items():
                            if not isinstance(b_info, dict):
                                continue
                            ts2 = b_info.get("timeupdated")
                            b_date = "unknown"
                            if ts2:
                                try:
                                    b_date = datetime.fromtimestamp(int(ts2)).strftime("%Y-%m-%d")
                                except Exception:
                                    pass
                            for depot_id2, depot_data2 in dlc_depots.items():
                                if not str(depot_id2).isdigit() or not isinstance(depot_data2, dict):
                                    continue
                                gid2 = depot_data2.get("manifests", {}).get(b_name, {}).get("gid")
                                if gid2:
                                    result.setdefault(str(depot_id2), []).append(ManifestEntry(
                                        manifest_id=str(gid2),
                                        date=b_date,
                                        branch=b_name,
                                        source="Steam CM (DLC)",
                                    ))
        except Exception as dlc_exc:
            logger.debug("DLC depot fetch failed for app %s: %s", app_id, dlc_exc)
    except Exception as exc:
        logger.debug("Steam CM fetch failed for app %s: %s", app_id, exc)
    return result


# ---------------------------------------------------------------------------
# Source 3 — Morrenus SteamCMD
# ---------------------------------------------------------------------------

def _fetch_hubcap_depots(app_id):
    """Get depot IDs from Hubcap/SteamCMD API."""
    try:
        resp = httpx.get(
            f"https://steamcmd.morrenus.net/api/{app_id}",
            timeout=10, follow_redirects=True,
        )
        if resp.status_code == 200:
            depots = resp.json().get("depots", {})
            if isinstance(depots, dict):
                return [k for k in depots if str(k).isdigit()]
    except Exception as exc:
        logger.debug("Morrenus fetch failed for app %s: %s", app_id, exc)
    return []


# ---------------------------------------------------------------------------
# CF challenge detection helper
# ---------------------------------------------------------------------------

def _is_cf_challenge(html: str) -> bool:
    """Return True if *html* is a Cloudflare challenge/block page, not real content."""
    if not html:
        return True
    lc = html.lower()
    return any(marker in lc for marker in (
        "just a moment",
        "cf-browser-verification",
        "cdn-cgi/challenge-platform",
        "checking your browser",
        "enable javascript and cookies",
    ))


# ---------------------------------------------------------------------------
# Source 5a — SteamDB Layer 1: curl_cffi Chrome impersonation (fast path)
# ---------------------------------------------------------------------------

def _steamdb_headers_base(user_agent=None):
    ua = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.steamdb.info/",
    }


async def _fetch_one_curl_cffi(session, depot_id: str):
    """Fetch a single SteamDB depot page using curl_cffi Chrome impersonation."""
    url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
    try:
        resp = await session.get(url, timeout=8)
        if resp.status_code == 200:
            entries = _parse_steamdb_html(resp.text)
            if entries:
                logger.debug("curl_cffi Layer1: depot %s -> %d entries", depot_id, len(entries))
                return depot_id, entries
    except Exception as exc:
        logger.debug("curl_cffi Layer1: depot %s failed: %s", depot_id, exc)
    return depot_id, []


async def _fetch_steamdb_curl_cffi_async(depot_ids: list):
    """Async batch fetch via curl_cffi Chrome impersonation. Max 3 concurrent."""
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        logger.debug("curl_cffi not installed, skipping Layer1")
        return {}

    results = {}
    semaphore = asyncio.Semaphore(3)

    async def _guarded(session, did):
        async with semaphore:
            result = await _fetch_one_curl_cffi(session, did)
            await asyncio.sleep(random.uniform(0.8, 1.5))
            return result

    async with AsyncSession(impersonate="chrome124") as session:
        tasks = [_guarded(session, did) for did in depot_ids]
        for coro in asyncio.as_completed(tasks):
            did, entries = await coro
            results[did] = entries

    return results


def _fetch_steamdb_layer1(depot_ids: list) -> dict:
    """Layer 1: curl_cffi Chrome impersonation (no browser, ~80% hit rate vs CF)."""
    if not depot_ids:
        return {}
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_fetch_steamdb_curl_cffi_async(depot_ids))
        finally:
            loop.close()
    except Exception as exc:
        logger.debug("curl_cffi Layer1 batch failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Source 5b — SteamDB Layer 2: httpx + cached cf_clearance cookie
# ---------------------------------------------------------------------------

def _fetch_steamdb_layer2(depot_ids: list) -> dict:
    """Layer 2: httpx with cached cf_clearance cookie (fast, no browser)."""
    if not depot_ids:
        return {}
    cf_clearance, user_agent = _get_valid_cf_cookie()
    if not cf_clearance:
        logger.debug("Layer2: no valid cf_clearance cookie, skipping")
        return {}

    results = {}
    cookies = {"cf_clearance": cf_clearance}
    headers = _steamdb_headers_base(user_agent)

    for depot_id in depot_ids:
        url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
        try:
            resp = httpx.get(url, headers=headers, cookies=cookies, timeout=8, follow_redirects=True)
            if resp.status_code == 403:
                logger.debug("Layer2: got 403 for depot %s — cookie expired", depot_id)
                break
            if resp.status_code == 200:
                entries = _parse_steamdb_html(resp.text)
                results[depot_id] = entries
                logger.debug("Layer2: depot %s -> %d entries", depot_id, len(entries))
        except Exception as exc:
            logger.debug("Layer2: depot %s failed: %s", depot_id, exc)
        time.sleep(random.uniform(0.8, 1.5))

    return results


# ---------------------------------------------------------------------------
# Source 5c — SteamDB Layer 3A: zendriver CDP (primary browser layer)
# ---------------------------------------------------------------------------

async def _fetch_steamdb_zendriver_async(
    depot_ids: list,
    app_id,
    progress_cb,
    stop_event,
    results_out: dict = None,
) -> tuple:
    """Async CDP scraping via zendriver — no navigator.webdriver, invisible to CF.

    Runs Chrome with headless=False positioned off-screen so Cloudflare treats it
    as a real visible browser without showing a window to the user.
    Results are written into results_out in real-time so partial progress is
    preserved even if the outer timeout fires.
    """
    import sys
    import zendriver as zd
    from zendriver.cdp import network as cdp_network

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    results: dict = {}
    if results_out is None:
        results_out = {}
    remaining = list(depot_ids)

    _, chrome_path = _detect_sb_browser(progress_cb=progress_cb)
    zd_kwargs: dict = {
        "headless": False,
        "browser_args": ["--window-position=-32000,-32000", "--window-size=1280,720"],
    }
    if chrome_path:
        zd_kwargs["browser_executable_path"] = chrome_path

    browser = None
    try:
        browser = await zd.start(**zd_kwargs)

        if app_id:
            app_url = f"https://www.steamdb.info/app/{app_id}/depots/"
            try:
                if progress_cb:
                    try:
                        progress_cb(f"SteamDB: zendriver — warming CF clearance for app {app_id}\u2026")
                    except Exception:
                        pass
                app_tab = await browser.get(app_url)
                await asyncio.sleep(8)
                html_app = await app_tab.get_content()
                if _is_cf_challenge(html_app):
                    await asyncio.sleep(6)
                    html_app = await app_tab.get_content()
                discovered = _parse_steamdb_app_depots(html_app)
                depot_id_set = set(depot_ids)
                extra = [d for d in discovered if d not in depot_id_set]
                if extra:
                    logger.debug("zendriver: discovered %d extra depot(s) from app page", len(extra))
                    for d in extra:
                        if d not in remaining:
                            remaining.append(d)
                try:
                    cookies = await app_tab.send(cdp_network.get_all_cookies())
                    for ck in cookies:
                        if ck.name == "cf_clearance":
                            ua = await app_tab.evaluate("navigator.userAgent")
                            _save_cf_cookie_cache(ck.value, ua or "")
                            logger.debug("zendriver: cf_clearance saved (app page)")
                            break
                except Exception as ck_exc:
                    logger.debug("zendriver: cookie extract on app page failed: %s", ck_exc)
            except Exception as app_exc:
                logger.debug("zendriver: app page failed for %s: %s", app_id, app_exc)

        all_len = len(remaining)
        _zd_cf_fails = 0
        for i, depot_id in enumerate(list(remaining)):
            if stop_event is not None and stop_event.is_set():
                break
            if progress_cb:
                try:
                    progress_cb(f"SteamDB: zendriver depot {i + 1}/{all_len} ({depot_id})\u2026")
                except Exception:
                    pass
            url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
            try:
                tab = await browser.get(url)
                await asyncio.sleep(8)
                html = await tab.get_content()
                if _is_cf_challenge(html):
                    await asyncio.sleep(8)
                    html = await tab.get_content()
                if not _is_cf_challenge(html):
                    entries = _parse_steamdb_html(html)
                    results[depot_id] = entries
                    results_out[depot_id] = entries
                    remaining.remove(depot_id)
                    logger.debug("zendriver: depot %s -> %d entries", depot_id, len(entries))
                    try:
                        cookies = await tab.send(cdp_network.get_all_cookies())
                        for ck in cookies:
                            if ck.name == "cf_clearance":
                                ua = await tab.evaluate("navigator.userAgent")
                                _save_cf_cookie_cache(ck.value, ua or "")
                                break
                    except Exception:
                        pass
                else:
                    _zd_cf_fails += 1
                    logger.debug(
                        "zendriver: CF challenge still active for depot %s (%d/2)",
                        depot_id, _zd_cf_fails,
                    )
                    if _zd_cf_fails >= 2:
                        logger.debug("zendriver: CF persistent after 2 depots, bailing to SeleniumBase")
                        break
            except Exception as exc:
                logger.debug("zendriver: depot %s failed: %s", depot_id, exc)

    finally:
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass

    return results, remaining


def _fetch_steamdb_zendriver(
    depot_ids: list,
    app_id=None,
    progress_cb=None,
    stop_event=None,
    results_out: dict = None,
) -> tuple:
    """Sync wrapper for zendriver CDP scraping. Returns (results_dict, remaining_list).

    Runs a single off-screen Chrome session (headless=False, window off-screen).
    Results are written into results_out in real-time so the caller can read
    partial progress even if this function is interrupted by an outer timeout.
    Gracefully skips if zendriver is not installed.
    """
    try:
        import zendriver  # noqa: F401
    except ImportError:
        logger.debug("zendriver not installed, skipping Layer 3A")
        return {}, list(depot_ids)

    if results_out is None:
        results_out = {}

    results: dict = {}
    remaining = list(depot_ids)
    try:
        loop = asyncio.new_event_loop()
        try:
            results, remaining = loop.run_until_complete(
                _fetch_steamdb_zendriver_async(
                    depot_ids, app_id, progress_cb, stop_event, results_out=results_out
                )
            )
        finally:
            loop.close()
    except Exception as exc:
        logger.debug("zendriver batch failed: %s", exc)
        results, remaining = results_out.copy(), list(depot_ids)

    if results:
        logger.debug("zendriver: %d depot(s) scraped", len(results))
    else:
        logger.debug("zendriver: 0 results")

    return results, remaining


# ---------------------------------------------------------------------------
# Source 5 — SteamDB via SeleniumBase UC mode
# ---------------------------------------------------------------------------

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
        __import__('os').environ.get('USERNAME', '')
    ),
]


def _ensure_chrome_for_testing(progress_cb=None):
    """
    Download the full Chrome for Testing binary from Google if not cached.
    The full Chrome binary (chrome.exe) is required — chrome-headless-shell does
    not support the WebDriver Classic protocol that Selenium/UC mode requires.
    Stored once in ~/.sff/chrome-for-testing/ (~300 MB).
    Returns path to chrome.exe or '' on failure.
    """
    import urllib.request, zipfile, json as _json, platform as _platform

    plat = "win64" if _platform.machine() in ("AMD64", "x86_64") else "win32"
    chrome_exe = _sff_dir() / "chrome-for-testing" / f"chrome-{plat}" / "chrome.exe"

    if chrome_exe.exists():
        return str(chrome_exe)

    logger.info("Chrome for Testing not found — downloading (~300 MB, one-time)...")
    if progress_cb:
        try:
            progress_cb("Downloading Chrome for Testing (~300 MB, one-time setup)…")
        except Exception:
            pass
    try:
        api = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
        with urllib.request.urlopen(api, timeout=20) as resp:
            data = _json.loads(resp.read())
        downloads = data["channels"]["Stable"]["downloads"].get("chrome", [])
        entry = next((d for d in downloads if d["platform"] == plat), None)
        if not entry:
            logger.debug("Chrome for Testing: no %s download found", plat)
            return ""
        zip_path = _sff_dir() / "chrome-for-testing.zip"
        logger.info("Downloading Chrome for Testing (%s) — this may take a minute...", plat)
        import socket as _sock_cft
        _old_timeout_cft = _sock_cft.getdefaulttimeout()
        _sock_cft.setdefaulttimeout(120)
        try:
            urllib.request.urlretrieve(entry["url"], str(zip_path))
        finally:
            _sock_cft.setdefaulttimeout(_old_timeout_cft)
        extract_dir = _sff_dir() / "chrome-for-testing"
        with zipfile.ZipFile(str(zip_path)) as z:
            z.extractall(str(extract_dir))
        zip_path.unlink(missing_ok=True)
        if chrome_exe.exists():
            logger.info("Chrome for Testing ready: %s", chrome_exe)
            if progress_cb:
                try:
                    progress_cb("Chrome for Testing ready — starting SteamDB scrape…")
                except Exception:
                    pass
            return str(chrome_exe)
    except Exception as exc:
        logger.debug("Chrome for Testing download failed: %s", exc)
    return ""


def _detect_sb_browser(progress_cb=None):
    """
    Return (browser_name, binary_path) for SeleniumBase UC mode.
    Preference order:
      1. Chrome bundled inside the frozen EXE (sys._MEIPASS/chrome-bundled/)
      2. Installed system Chrome (known file paths + Windows registry)
      3. Chrome for Testing auto-downloaded to ~/.sff/
    """
    import os, sys
    # 1. Frozen EXE: check bundled chrome
    if getattr(sys, 'frozen', False):
        bundled = Path(sys._MEIPASS) / 'chrome-bundled' / 'chrome.exe'
        if bundled.exists():
            return 'chrome', str(bundled)
    # 2a. System Chrome via known file paths
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return 'chrome', path
    # 2b. System Chrome via Windows registry (covers non-standard install locations)
    if sys.platform == "win32":
        try:
            import winreg as _wr
            _reg_keys = [
                (_wr.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                (_wr.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                (_wr.HKEY_CURRENT_USER,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            ]
            for _hive, _subkey in _reg_keys:
                try:
                    with _wr.OpenKey(_hive, _subkey) as _rk:
                        _rpath = _wr.QueryValue(_rk, None)
                        if _rpath and os.path.exists(_rpath):
                            logger.debug("Chrome found via registry: %s", _rpath)
                            return 'chrome', _rpath
                except OSError:
                    pass
        except ImportError:
            pass
    # 3. Auto-download Chrome for Testing
    chrome = _ensure_chrome_for_testing(progress_cb=progress_cb)
    if chrome:
        return 'chrome', chrome
    return 'chrome', ''   # last resort: let SeleniumBase try its own detection


def _cleanup_chrome_for_testing():
    """Kill any orphaned automation Chrome / ChromeDriver processes.

    Targets Chrome instances launched by zendriver or SeleniumBase UC mode.
    Every automation-spawned Chrome carries ``--remote-debugging-port`` in its
    command line; a user's regular browsing session never has that flag, so
    this filter is safe regardless of whether system Chrome or a bundled binary
    was used.
    """
    import subprocess, sys
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                 "Where-Object { $_.CommandLine -like '*--remote-debugging-port*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA 0 }; "
                 "Get-Process chromedriver -EA 0 | Stop-Process -Force -EA 0"],
                capture_output=True, timeout=15,
            )
        else:
            subprocess.run(["pkill", "-f", "chrome-for-testing"],
                           capture_output=True, timeout=5)
            subprocess.run(["pkill", "-f", "chromedriver"],
                           capture_output=True, timeout=5)
    except Exception:
        pass



def _fetch_steamdb_seleniumbase(depot_id):
    """Try SteamDB via SeleniumBase UC mode (headless Chrome + CF bypass)."""
    try:
        from seleniumbase import SB
    except ImportError:
        logger.debug("seleniumbase not installed, skipping SteamDB fallback")
        return []
    url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
    browser, binary = _detect_sb_browser()
    try:
        sb_kwargs = dict(uc=True, headless=True, block_images=True, browser=browser)
        if binary:
            sb_kwargs["binary_location"] = binary
        with SB(**sb_kwargs) as sb:
            sb.driver.set_page_load_timeout(30)
            sb.driver.set_script_timeout(30)
            sb.uc_open_with_reconnect(url, 10)
            try:
                sb.wait_for_element('td.tabular-nums', timeout=12)
            except Exception:
                sb.sleep(4)
            entries = _parse_steamdb_html(sb.get_page_source())
            try:
                for ck in sb.driver.get_cookies():
                    if ck.get("name") == "cf_clearance":
                        ua = sb.driver.execute_script("return navigator.userAgent;")
                        _save_cf_cookie_cache(ck["value"], ua or "")
                        logger.debug("SteamDB single-depot: cf_clearance cookie saved")
                        break
            except Exception:
                pass
            if entries:
                logger.debug("SteamDB SeleniumBase: %d entries for depot %s", len(entries), depot_id)
            return entries
    except Exception as exc:
        logger.debug("SteamDB SeleniumBase failed for depot %s: %s", depot_id, exc)
        return []
    finally:
        _cleanup_chrome_for_testing()


def _fetch_steamdb_batch(
    depot_ids: list,
    progress_cb=None,
    app_id=None,
    _stop_event=None,
):
    """
    SeleniumBase Layer 3B: fallback browser scraper used when zendriver is unavailable
    or failed.

    Uses headless2 (Chrome --headless=new) for sessions 0-1; switches to visible
    window for session 2+ if headless keeps getting CF-blocked.

    curl_cffi fast path is disabled after 3 consecutive 403s to prevent IP
    contamination from TLS fingerprint mismatches poisoning browser fetches.

    Returns {depot_id: [ManifestEntry, ...]}.
    """
    if not depot_ids and not app_id:
        return {}
    try:
        from seleniumbase import SB
    except ImportError:
        logger.debug("seleniumbase not installed, skipping SteamDB batch scrape")
        return {}

    _cf_session = None
    try:
        from curl_cffi import requests as _cf_mod
        _cf_session = _cf_mod.Session(impersonate="chrome124")
    except Exception:
        logger.debug("curl_cffi not available, will use browser for all depots")

    results = {}
    browser_name, binary = _detect_sb_browser(progress_cb=progress_cb)
    cookie_saved = False
    _curl_cffi_consecutive_fails = 0
    _curl_cffi_disabled = False

    def _try_curl_cffi(did):
        """Fast path: curl_cffi with Chrome TLS impersonation + cached cf_clearance."""
        nonlocal _curl_cffi_consecutive_fails, _curl_cffi_disabled
        if not _cf_session or _curl_cffi_disabled:
            return None
        cf_c, cf_ua = _get_valid_cf_cookie()
        if not cf_c:
            return None
        url_c = f"https://www.steamdb.info/depot/{did}/manifests/"
        try:
            r = _cf_session.get(
                url_c,
                headers=_steamdb_headers_base(cf_ua),
                cookies={"cf_clearance": cf_c},
                timeout=10,
            )
            if r.status_code == 200:
                _curl_cffi_consecutive_fails = 0
                return _parse_steamdb_html(r.text)
            if r.status_code == 403:
                logger.debug("curl_cffi: 403 for depot %s", did)
                _curl_cffi_consecutive_fails += 1
                if _curl_cffi_consecutive_fails >= 3:
                    _curl_cffi_disabled = True
                    logger.debug(
                        "curl_cffi: disabled for session after %d consecutive 403s "
                        "(prevents IP contamination)",
                        _curl_cffi_consecutive_fails,
                    )
        except Exception as exc:
            logger.debug("curl_cffi depot %s failed: %s", did, exc)
        return None

    def _extract_cf_cookie(sb, label=""):
        """Extract cf_clearance from browser and save to disk cache."""
        nonlocal cookie_saved
        try:
            for ck in sb.driver.get_cookies():
                if ck.get("name") == "cf_clearance":
                    ua = sb.driver.execute_script("return navigator.userAgent;")
                    _save_cf_cookie_cache(ck["value"], ua or "")
                    cookie_saved = True
                    if label:
                        logger.debug("SteamDB batch: cf_clearance saved (%s)", label)
                    return True
        except Exception:
            pass
        return False

    all_depot_ids = list(depot_ids)
    remaining = list(depot_ids)

    _MAX_SESSIONS = 3
    for session_num in range(_MAX_SESSIONS):
        if not remaining:
            break
        if _stop_event is not None and _stop_event.is_set():
            break

        if session_num > 0:
            _cleanup_chrome_for_testing()
            time.sleep(3)
            logger.debug(
                "SteamDB batch: starting session %d for %d remaining depots",
                session_num + 1, len(remaining),
            )

        sb_kwargs = dict(uc=True, headless=True, block_images=True, browser=browser_name)
        if binary:
            sb_kwargs["binary_location"] = binary

        consecutive_cf = 0
        try:
            with SB(**sb_kwargs) as sb:
                sb.driver.set_page_load_timeout(30)
                sb.driver.set_script_timeout(30)

                if session_num == 0 and app_id:
                    try:
                        app_url = f"https://www.steamdb.info/app/{app_id}/depots/"
                        if progress_cb:
                            try:
                                progress_cb(f"SteamDB: discovering depots for app {app_id}\u2026")
                            except Exception:
                                pass
                        sb.uc_open_with_reconnect(app_url, 8)
                        try:
                            sb.wait_for_element('a[href*="/depot/"]', timeout=12)
                        except Exception:
                            sb.sleep(4)
                        app_html = sb.get_page_source()
                        discovered = _parse_steamdb_app_depots(app_html)
                        depot_id_set = set(depot_ids)
                        extra = [d for d in discovered if d not in depot_id_set]
                        if extra:
                            logger.debug("SteamDB: discovered %d extra depot(s) from app page", len(extra))
                            all_depot_ids = list(depot_ids) + extra
                            for d in extra:
                                if d not in remaining:
                                    remaining.append(d)
                        _extract_cf_cookie(sb, "app page")
                        if _cf_session and cookie_saved and not _curl_cffi_disabled:
                            try:
                                pn_url = f"https://www.steamdb.info/app/{app_id}/patchnotes/"
                                cf_c, cf_ua = _get_valid_cf_cookie()
                                if cf_c:
                                    time.sleep(random.uniform(0.5, 1.0))
                                    pn_resp = _cf_session.get(
                                        pn_url,
                                        headers=_steamdb_headers_base(cf_ua),
                                        cookies={"cf_clearance": cf_c},
                                        timeout=15,
                                    )
                                    if pn_resp.status_code == 200:
                                        bid = _parse_steamdb_patchnotes(pn_resp.text)
                                        if bid:
                                            _BUILD_IDS_CACHE[str(app_id)] = bid
                                            logger.debug("SteamDB patchnotes: %d build IDs for app %s", len(bid), app_id)
                            except Exception as pn_exc:
                                logger.debug("SteamDB patchnotes fetch failed: %s", pn_exc)
                    except Exception as exc:
                        logger.debug("SteamDB app depots page failed for app %s: %s", app_id, exc)

                if session_num > 0:
                    try:
                        sb.uc_open_with_reconnect("https://www.steamdb.info/", 8)
                        sb.sleep(2)
                        _extract_cf_cookie(sb, f"session {session_num + 1}")
                    except Exception:
                        pass

                n = len(all_depot_ids)
                batch = list(remaining)

                for depot_id in batch:
                    if _stop_event is not None and _stop_event.is_set():
                        logger.debug("SteamDB batch: stop signal received")
                        break

                    idx = (all_depot_ids.index(depot_id) + 1) if depot_id in all_depot_ids else (len(results) + 1)
                    if progress_cb:
                        try:
                            progress_cb(f"SteamDB: depot {idx}/{n} ({depot_id})\u2026")
                        except Exception:
                            pass

                    if cookie_saved and not _curl_cffi_disabled:
                        time.sleep(random.uniform(0.8, 1.5))
                        entries = _try_curl_cffi(depot_id)
                        if entries is not None:
                            results[depot_id] = entries
                            remaining.remove(depot_id)
                            consecutive_cf = 0
                            logger.debug("SteamDB curl_cffi: depot %s -> %d entries", depot_id, len(entries))
                            continue

                    time.sleep(random.uniform(1.5, 3.0))
                    url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
                    try:
                        sb.uc_open_with_reconnect(url, 8)
                        try:
                            sb.wait_for_element('td.tabular-nums', timeout=15)
                        except Exception:
                            sb.sleep(4)
                        html = sb.get_page_source()
                        entries = _parse_steamdb_html(html)

                        if _is_cf_challenge(html):
                            consecutive_cf += 1
                            logger.debug(
                                "SteamDB batch: CF blocked depot %s (%d consecutive)",
                                depot_id, consecutive_cf,
                            )
                            if consecutive_cf >= 3:
                                logger.debug("SteamDB batch: restarting browser after %d CF blocks", consecutive_cf)
                                break
                            continue

                        consecutive_cf = 0
                        _extract_cf_cookie(sb)
                        logger.debug("SteamDB batch: depot %s -> %d entries", depot_id, len(entries))
                        results[depot_id] = entries
                        remaining.remove(depot_id)
                    except Exception as exc:
                        logger.debug("SteamDB batch depot %s failed: %s", depot_id, exc)
                        results[depot_id] = []
                        remaining.remove(depot_id)
        except Exception as exc:
            logger.debug("SteamDB batch session %d failed: %s", session_num + 1, exc)

    _cleanup_chrome_for_testing()
    if _cf_session:
        try:
            _cf_session.close()
        except Exception:
            pass
    return results


def _fetch_steamdb_all(depot_ids: list, progress_cb=None, app_id=None) -> dict:
    """
    Unified 3-layer SteamDB fetcher.
    Layer 1: curl_cffi Chrome impersonation (fast, no browser)
    Layer 2: httpx + cached cf_clearance cookie (fast, no browser)
    Layer 3: SeleniumBase batch (always works, saves cookie for next run)
    If *app_id* is given, Layer 3 also visits /app/{id}/depots/ to discover extra depots.
    Returns {depot_id: [ManifestEntry, ...]} for all depots.
    """
    if not depot_ids and not app_id:
        return {}

    results = {}
    remaining = list(depot_ids)

    # Layer 1 — curl_cffi
    if remaining:
        if progress_cb:
            try:
                progress_cb(f"SteamDB: trying fast path (Layer 1) for {len(remaining)} depots…")
            except Exception:
                pass
        layer1 = _fetch_steamdb_layer1(remaining)
        for did, entries in layer1.items():
            if entries:
                results[did] = entries
        remaining = [d for d in remaining if not results.get(d)]
        logger.debug("Layer1 done: %d hits, %d remaining", len(results), len(remaining))

    # Layer 2 — cf_clearance cookie cache
    if remaining:
        if progress_cb:
            try:
                progress_cb(f"SteamDB: trying cookie cache (Layer 2) for {len(remaining)} depots…")
            except Exception:
                pass
        layer2 = _fetch_steamdb_layer2(remaining)
        for did, entries in layer2.items():
            if entries:
                results[did] = entries
        remaining = [d for d in remaining if not results.get(d)]
        logger.debug("Layer2 done: %d total hits, %d remaining", len(results), len(remaining))

    # Layer 3A — zendriver CDP (primary browser layer, no navigator.webdriver)
    if remaining:
        import concurrent.futures as _cf_futures
        import threading as _threading
        _stop_evt_3a = _threading.Event()
        _l3a_results_out: dict = {}
        with _cf_futures.ThreadPoolExecutor(max_workers=1) as _l3a_ex:
            _l3a_fut = _l3a_ex.submit(
                _fetch_steamdb_zendriver, remaining, app_id, progress_cb,
                _stop_evt_3a, _l3a_results_out,
            )
            try:
                _l3a_results, _l3a_remaining = _l3a_fut.result(timeout=150)
            except _cf_futures.TimeoutError:
                logger.debug("Layer3A (zendriver) timed out after 150s — stopping")
                _stop_evt_3a.set()
                _l3a_results = _l3a_results_out.copy()
                _l3a_remaining = [d for d in remaining if d not in _l3a_results]
            except Exception as _l3a_exc:
                logger.debug("Layer3A (zendriver) failed: %s", _l3a_exc)
                _l3a_results = _l3a_results_out.copy()
                _l3a_remaining = [d for d in remaining if d not in _l3a_results]
        for did, entries in _l3a_results.items():
            results.setdefault(did, entries)
        remaining = [d for d in remaining if not results.get(d)]
        logger.debug("Layer3A done: %d total hits, %d remaining", len(results), len(remaining))
        _cleanup_chrome_for_testing()
        time.sleep(5)

    # Layer 3B — SeleniumBase batch (fallback when zendriver unavailable or failed)
    if remaining:
        import concurrent.futures as _cf_futures
        import threading as _threading
        _stop_evt = _threading.Event()
        _layer3_result = {}
        with _cf_futures.ThreadPoolExecutor(max_workers=1) as _l3_ex:
            _l3_fut = _l3_ex.submit(
                _fetch_steamdb_batch, remaining, progress_cb, app_id, _stop_evt
            )
            try:
                _layer3_result = _l3_fut.result(timeout=360)
            except _cf_futures.TimeoutError:
                logger.debug("Layer3B (SeleniumBase) timed out after 360s — signalling stop and killing Chrome")
                _stop_evt.set()
                _cleanup_chrome_for_testing()
            except Exception as _l3_exc:
                logger.debug("Layer3B (SeleniumBase) failed: %s", _l3_exc)
        for did, entries in _layer3_result.items():
            results.setdefault(did, entries)

    return results


def _fetch_steamdb(depot_id):
    """SteamDB: plain httpx first (likely blocked by CF), then SeleniumBase UC."""
    url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            entries = _parse_steamdb_html(resp.text)
            if entries:
                return entries
    except Exception:
        pass
    return _fetch_steamdb_seleniumbase(depot_id)


def _parse_steamdb_html(html):
    """
    Parse the SteamDB depot/manifests HTML table using BeautifulSoup.

    Actual SteamDB column layout (as of 2026):
      col 0: date text  (e.g. "13 March 2026 – 05:16:14 UTC")
      col 1: relative time  (<td data-time="2026-03-13T...">last month</td>)
      col 2: manifest ID  (<td class="tabular-nums"><a ...>NNNNN</a></td>)
      col 3: copy button  (no text content)

    We scan ALL cells for the manifest ID so column shifts don't break us.
    Date is extracted from the data-time or datetime attribute of any cell element.
    """
    from bs4 import BeautifulSoup

    entries = []
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            # Find whichever cell holds the manifest ID (15+ digit number)
            manifest_id = ""
            for cell in cells:
                text = cell.get_text(strip=True)
                if re.match(r"^\d{15,}$", text):
                    manifest_id = text
                    break
            if not manifest_id:
                continue
            # Date: prefer data-time attribute, fall back to datetime attribute
            # data-time may be on the <td> itself or on a child element
            date = "unknown"
            for cell in cells:
                for el in [cell] + cell.find_all(True):
                    dt = el.get("data-time") or el.get("datetime") or ""
                    if re.match(r"\d{4}-\d{2}-\d{2}", dt):
                        date = dt[:10]
                        break
                if date != "unknown":
                    break
            # Branch: look for a known branch word in cell text; default public
            branch = "public"
            _BRANCHES = {"public", "beta", "staging", "internal", "early_access"}
            for cell in cells:
                txt = cell.get_text(strip=True).lower()
                if txt in _BRANCHES:
                    branch = txt
                    break
            entries.append(ManifestEntry(
                manifest_id=manifest_id,
                date=date,
                branch=branch,
                size_mb=0.0,
                source="SteamDB",
            ))

    # Deduplicate by manifest_id (keep first = newest from top of table)
    seen = set()
    unique = []
    for e in entries:
        if e.manifest_id not in seen:
            seen.add(e.manifest_id)
            unique.append(e)

    return unique


def _parse_steamdb_app_depots(html: str) -> list:
    """Extract depot IDs from a SteamDB app depots page (/app/{id}/depots/).

    Finds all ``<a href="/depot/{digits}...">`` links on the page and returns
    a deduplicated list of depot ID strings.
    """
    from bs4 import BeautifulSoup

    depot_ids = []
    seen = set()
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        m = re.match(r"/depot/(\d+)", a["href"])
        if m:
            did = m.group(1)
            if did not in seen:
                seen.add(did)
                depot_ids.append(did)
    return depot_ids


_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}
_TEXT_DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")


def _parse_text_date(text: str) -> str:
    """Parse '8 May 2023' or '25 January 2017' → 'YYYY-MM-DD' or ''."""
    m = _TEXT_DATE_RE.match(text.strip())
    if m:
        day, month_name, year = m.groups()
        month = _MONTH_MAP.get(month_name.lower())
        if month:
            return f"{year}-{month}-{int(day):02d}"
    return ""


def _parse_steamdb_patchnotes(html: str) -> dict[str, str]:
    """Parse SteamDB /app/{id}/patchnotes/ page.

    Returns {date_str: build_id} mapping (YYYY-MM-DD -> build ID string).

    The patchnotes page has a table with columns:
      Date ("8 May 2023") | Day | Time | Patch Title | icons | BuildID ("11026049")
    We identify the correct table by looking for a header containing "BuildID".
    Real Steam build IDs are always 7+ digits (1 000 000+).
    """
    from bs4 import BeautifulSoup

    build_ids: dict[str, str] = {}
    soup = BeautifulSoup(html, "html.parser")

    # Find the builds table — it has a header cell containing "BuildID"
    target_table = None
    for th in soup.find_all(["th", "td"]):
        if "buildid" in th.get_text(strip=True).lower().replace(" ", ""):
            target_table = th.find_parent("table")
            break

    if not target_table:
        logger.debug("Patchnotes parser: no table with 'BuildID' header found")
        return {}

    for row in target_table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        date = ""
        bid = ""

        for cell in cells:
            text = cell.get_text(strip=True)

            # Date: try data-time/datetime attribute first
            if not date:
                for el in [cell] + cell.find_all(True):
                    dt = el.get("data-time") or el.get("datetime") or ""
                    if re.match(r"\d{4}-\d{2}-\d{2}", dt):
                        date = dt[:10]
                        break

            # Date: try plain text like "8 May 2023"
            if not date:
                parsed = _parse_text_date(text)
                if parsed:
                    date = parsed

            # BuildID: 7+ digit number (Steam build IDs are always 1M+)
            if not bid and re.match(r"^\d{7,}$", text):
                bid = text

        if date and bid:
            build_ids.setdefault(date, bid)

    return build_ids


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_depot_key(depot_id):
    """Return True if this depot has a known decryption key in fallback_depotkeys."""
    return str(depot_id) in _DEPOT_KEY_IDS


def get_depot_manifests(depot_id, fetch_dates = True,
                        force_refresh = False):
    """
    Return manifest history for a depot from GitHub mirror + local fallbacks.
    Source 5 (SteamDB) fires only if nothing is found from other sources.
    Results cached for 5 minutes per session.
    """
    depot_id = str(depot_id)
    if not force_refresh:
        cached = _RESULT_CACHE.get(depot_id)
        if cached and (time.time() - cached[0]) < _RESULT_TTL:
            return cached[1]

    entries = []
    seen = set()

    def _add(e):
        if e.manifest_id not in seen:
            seen.add(e.manifest_id)
            entries.append(e)

    # Source 2 — GitHub mirror (lazy date fetch)
    _get_mirror_tree()
    for mid in _TREE_MAP.get(depot_id, []):
        filename = f"{depot_id}_{mid}.manifest"
        date = _DATES.get(filename, "")
        if not date and fetch_dates:
            date = _fetch_file_date(filename)
        _add(ManifestEntry(manifest_id=mid, date=date or "N/A",
                           branch="public", source="GitHub mirror"))

    # Source 4a — local fallback_tokens (897 confirmed depot entries)
    if depot_id in _FALLBACK_TOKENS:
        _add(ManifestEntry(manifest_id=str(_FALLBACK_TOKENS[depot_id]),
                           date="(local fallback)", branch="public",
                           source="local fallback"))

    # Source 5 — SteamDB fast-path (cookie only; browser handled by get_depots_for_app batch)
    if not entries:
        cf_c, cf_ua = _get_valid_cf_cookie()
        if cf_c:
            try:
                url_s = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
                resp = httpx.get(
                    url_s, headers=_steamdb_headers_base(cf_ua),
                    cookies={"cf_clearance": cf_c}, timeout=8,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    for e in _parse_steamdb_html(resp.text):
                        _add(e)
            except Exception:
                pass

    def _sort_key(e):
        return e.date if re.match(r"\d{4}-\d{2}-\d{2}", e.date) else "0000-00-00"

    entries.sort(key=_sort_key, reverse=True)
    _RESULT_CACHE[depot_id] = (time.time(), entries)
    return entries


def get_depots_for_app(app_id, progress_cb=None, force_refresh=False):
    """
    Return {depot_id: [ManifestEntry, ...]} for all depots of an app.

    Depot IDs + current manifests come from Steam CM (Source 1).
    Falls back to Morrenus (Source 3) if Steam CM fails for depot IDs.
    Historical manifests come from get_depot_manifests() per depot (Sources 2/4).
    SteamDB 3-layer scrape fills gaps (Source 5).

    Results are persisted to ~/.sff/depot_cache_{app_id}.json.  On subsequent
    calls the cache is loaded first; only depots whose Steam CM manifest ID
    changed since the last run are re-scraped — the rest are served instantly.
    """
    def _sort_fn(e):
        return e.date if re.match(r"\d{4}-\d{2}-\d{2}", e.date) else "0000-00-00"

    app_id = str(app_id)

    # Source 1: Steam CM — gives depot IDs + current manifests with real dates
    steam_entries = _fetch_steam_cm_entries(app_id)
    depot_ids = list(steam_entries.keys())

    # Source 3: Hubcap/SteamCMD fallback if Steam CM returned nothing
    if not depot_ids:
        depot_ids = _fetch_hubcap_depots(app_id)

    if not depot_ids:
        return {}

    # ── Load disk cache ──────────────────────────────────────────────────────
    if force_refresh:
        cached_depots = None
    else:
        cached_depots, _ = _load_app_depot_cache(app_id)

    fresh_depots = []   # depot_ids whose cache is up-to-date → skip scraping
    stale_depots = []   # depot_ids that need a fresh scrape

    for depot_id in depot_ids:
        cm_manifest_ids = {e.manifest_id for e in steam_entries.get(depot_id, [])}
        if cached_depots and depot_id in cached_depots:
            cached_manifest_ids = {raw["manifest_id"] for raw in cached_depots[depot_id]}
            has_historical = any(
                raw.get("source", "") not in ("Steam CM", "Steam CM (DLC)")
                for raw in cached_depots[depot_id]
            )
            if cm_manifest_ids and cm_manifest_ids.issubset(cached_manifest_ids) and has_historical:
                fresh_depots.append(depot_id)
                continue
        stale_depots.append(depot_id)

    if fresh_depots:
        logger.debug(
            "app %s: %d depot(s) served from cache, %d need rescrape",
            app_id, len(fresh_depots), len(stale_depots),
        )

    result = {}

    # ── Fresh depots: reconstruct from cache + overlay current CM entries ────
    for depot_id in fresh_depots:
        cached_entries = [ManifestEntry(**raw) for raw in cached_depots[depot_id]]
        merged = list(steam_entries.get(depot_id, []))
        seen = {(e.manifest_id, e.date) for e in merged}
        for e in cached_entries:
            if (e.manifest_id, e.date) not in seen:
                seen.add((e.manifest_id, e.date))
                merged.append(e)
        if merged:
            merged.sort(key=_sort_fn, reverse=True)
            result[depot_id] = merged

    # ── Stale depots: full scrape pipeline ──────────────────────────────────
    for depot_id in stale_depots:
        merged = list(steam_entries.get(depot_id, []))
        seen = {(e.manifest_id, e.date) for e in merged}
        # Pre-seed with any existing cached entries (historical data still valid)
        if cached_depots and depot_id in cached_depots:
            for raw in cached_depots[depot_id]:
                e = ManifestEntry(**raw)
                if (e.manifest_id, e.date) not in seen:
                    seen.add((e.manifest_id, e.date))
                    merged.append(e)
        # fetch_dates=False: avoid exhausting the 60/hr GitHub rate limit on bulk load
        for e in get_depot_manifests(depot_id, fetch_dates=False, force_refresh=force_refresh):
            if (e.manifest_id, e.date) not in seen:
                seen.add((e.manifest_id, e.date))
                merged.append(e)
        if merged:
            merged.sort(key=_sort_fn, reverse=True)
            result[depot_id] = merged

    # Source 5 — SteamDB 3-layer fetch for stale depots not yet covered.
    # Layer 1 (curl_cffi) → Layer 2 (cf_clearance cookie) → Layer 3 (SeleniumBase).
    # Skip depots that get_depot_manifests already scraped (have SteamDB-sourced entries).
    needs_steamdb = [
        d for d in stale_depots
        if not any(e.source.startswith("SteamDB") for e in result.get(d, []))
    ]
    if needs_steamdb:
        logger.debug("SteamDB 3-layer scraping %d depots for historical data", len(needs_steamdb))
        for did, sdb_entries in _fetch_steamdb_all(needs_steamdb, progress_cb=progress_cb, app_id=app_id).items():
            # Deduplicate on (manifest_id, date) so DLC depots with a single
            # manifest still appear under their historical SteamDB date even
            # when Steam CM already reported that manifest under a different date.
            current_seen = {(e.manifest_id, e.date) for e in result.get(did, [])}
            new_entries = [e for e in sdb_entries if (e.manifest_id, e.date) not in current_seen]
            if new_entries:
                result.setdefault(did, [])
                result[did].extend(new_entries)
                result[did].sort(key=_sort_fn, reverse=True)

    # ── Persist updated result to disk cache ─────────────────────────────────
    if result:
        _save_app_depot_cache(app_id, result)

    # ── Fetch build IDs from SteamDB patchnotes (if not already cached) ────
    if app_id:
        _ensure_build_ids(app_id)

    return result


# ---------------------------------------------------------------------------
# Version grouping
# ---------------------------------------------------------------------------

@dataclass
class VersionGroup:
    """A logical game version = all depots belonging to the same (date, branch, source)."""
    label: str                           # human-readable header string
    date: str                            # ISO date or "N/A" — used for sorting
    branch: str
    source: str
    entries: list[tuple[str, str]]       # [(depot_id, manifest_id)]
    entry_map: dict[str, ManifestEntry]  # depot_id -> ManifestEntry (for metadata)
    build_id: str = ""                   # SteamDB build/changelist ID (optional)


def group_by_version(depot_history: dict[str, list[ManifestEntry]], build_ids: dict[str, str] | None = None):
    """
    Convert {depot_id: [ManifestEntry]} into a list of VersionGroup, newest-first.
    Groups by (date, branch, source). Mirror entries with non-date values
    (N/A, loading..., local fallback, etc.) are merged into one archive group
    per source.

    *build_ids*: optional {date -> build_id} from SteamDB patchnotes.
    """
    # Helper: find build_id for a date, trying exact match first then ±3 days
    def _find_bid(date_str: str) -> str:
        if not build_ids or date_str == "__archive__":
            return ""
        # Exact match
        if date_str in build_ids:
            return build_ids[date_str]
        # Nearest-date within ±3 days
        try:
            from datetime import timedelta
            target = datetime.strptime(date_str, "%Y-%m-%d")
            best_bid = ""
            best_delta = 4  # max 3 days
            for bd_str, bid_val in build_ids.items():
                try:
                    bd = datetime.strptime(bd_str, "%Y-%m-%d")
                    delta = abs((target - bd).days)
                    if delta < best_delta:
                        best_delta = delta
                        best_bid = bid_val
                except ValueError:
                    continue
            return best_bid
        except (ValueError, ImportError):
            return ""

    # bucket key -> list of (depot_id, entry)
    buckets = {}

    for depot_id, entries in depot_history.items():
        for entry in entries:
            date = entry.date
            is_real_date = bool(re.match(r"\d{4}-\d{2}-\d{2}", date))
            bucket_date = date if is_real_date else "__archive__"
            key = (bucket_date, entry.branch, entry.source)
            buckets.setdefault(key, []).append((depot_id, entry))

    groups = []
    for (bucket_date, branch, source), items in buckets.items():
        unique_depots = len({d for d, _ in items})
        depot_word = "depot" if unique_depots == 1 else "depots"
        if bucket_date == "__archive__":
            label = f"Unknown date  —  {branch}  —  {source}  ({unique_depots} {depot_word})"
            sort_date = "0000-00-00"
        else:
            label = f"{bucket_date}  —  {branch}  —  {source}  ({unique_depots} {depot_word})"
            sort_date = bucket_date
        entry_map = {}
        entries_list = []
        seen_pairs = set()
        for depot_id, entry in items:
            pair = (depot_id, entry.manifest_id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                entries_list.append(pair)
                entry_map[depot_id] = entry
        bid = _find_bid(bucket_date)
        if bid:
            label += f"  —  Build {bid}"
        groups.append(VersionGroup(
            label=label,
            date=sort_date,
            branch=branch,
            source=source,
            entries=entries_list,
            entry_map=entry_map,
            build_id=bid,
        ))

    groups.sort(key=lambda g: g.date, reverse=True)

    # ---------------------------------------------------------------------------
    # Post-process: resolve empty manifest_ids that the SteamDB app history page
    # left blank.  That page records which depots changed per build but does not
    # include manifest IDs.  For each group entry with manifest_id="", find the
    # best non-empty manifest from the depot's full history.
    # Priority: (1) non-CM dated entry with date <= group.date, (2) any non-CM
    # non-dated entry, (3) oldest non-CM dated entry, (4) Steam CM last resort.
    # ---------------------------------------------------------------------------
    for group in groups:
        for i, (depot_id, manifest_id) in enumerate(list(group.entries)):
            if manifest_id:
                continue
            all_hist = depot_history.get(depot_id, [])
            if not all_hist:
                continue
            # (1) non-CM dated, date <= group.date
            pref = [
                e for e in all_hist
                if e.manifest_id
                and e.source != "Steam CM"
                and re.match(r"\d{4}-\d{2}-\d{2}", e.date)
                and e.date <= group.date
            ]
            if pref:
                best_pp = max(pref, key=lambda e: e.date)
            else:
                # (2) any non-CM non-dated (local fallback)
                non_cm_nd = [e for e in all_hist if e.manifest_id and e.source != "Steam CM"
                             and not re.match(r"\d{4}-\d{2}-\d{2}", e.date)]
                if non_cm_nd:
                    best_pp = non_cm_nd[0]
                else:
                    # (3) oldest non-CM dated (depot debuted after this build date)
                    non_cm_d = [e for e in all_hist if e.manifest_id and e.source != "Steam CM"
                                and re.match(r"\d{4}-\d{2}-\d{2}", e.date)]
                    if non_cm_d:
                        best_pp = min(non_cm_d, key=lambda e: e.date)
                    else:
                        # (4) Steam CM — only manifest available
                        cm_pp = [e for e in all_hist if e.manifest_id and e.source == "Steam CM"]
                        if not cm_pp:
                            continue
                        best_pp = cm_pp[0]
            group.entries[i] = (depot_id, best_pp.manifest_id)
            group.entry_map[depot_id] = best_pp

    # ---------------------------------------------------------------------------
    # Fill-forward: for every dated group that is NOT Steam CM, ensure ALL known
    # depots appear.  Depots not changed on that exact date are filled in using
    # their most recent manifest entry with date <= group.date.  This makes each
    # historical group a complete snapshot of the game at that point in time,
    # matching the Steam CM behaviour of always showing all depots.
    # ---------------------------------------------------------------------------
    all_depot_ids = list(depot_history.keys())
    for group in groups:
        if group.date == "0000-00-00" or group.source == "Steam CM":
            continue  # skip archive / unknown-date groups and Steam CM (already complete)
        depots_in_group = {depot_id for depot_id, _ in group.entries}
        added = 0
        for depot_id in all_depot_ids:
            if depot_id in depots_in_group:
                continue
            # Find the most recent non-Steam-CM entry for this depot with date <= group.date.
            # Steam CM entries must never be used to fill SteamDB/mirror groups — they carry
            # the current build date (e.g. 2026-03-27) which does not represent the game state
            # at the historical group date.
            candidates = [
                e for e in depot_history.get(depot_id, [])
                if e.manifest_id
                and re.match(r"\d{4}-\d{2}-\d{2}", e.date)
                and e.date <= group.date
                and e.source != "Steam CM"
            ]
            if not candidates:
                # No dated manifest at or before this build date.
                # Check for non-dated entries (local fallback tokens).
                non_dated = [
                    e for e in depot_history.get(depot_id, [])
                    if e.source != "Steam CM"
                    and not re.match(r"\d{4}-\d{2}-\d{2}", e.date)
                ]
                if non_dated:
                    best = non_dated[0]
                else:
                    depot_entries = depot_history.get(depot_id, [])
                    if not depot_entries:
                        continue
                    # Use Steam CM manifest if available.  Depots that genuinely
                    # have no manifest on SteamDB (CM source also empty) are
                    # included with manifest_id="" so DDMod downloads them
                    # without pinning and GreenLuma handles the unlock.
                    cm_fb = [e for e in depot_entries if e.manifest_id and e.source == "Steam CM"]
                    if cm_fb:
                        best = cm_fb[0]
                    else:
                        best = ManifestEntry(
                            manifest_id="", date="", branch=group.branch, source="",
                        )
            else:
                best = max(candidates, key=lambda e: e.date)
            pair = (depot_id, best.manifest_id)
            if pair not in set(group.entries):
                group.entries.append(pair)
                group.entry_map[depot_id] = best
                added += 1
        if added:
            unique_depots = len({d for d, _ in group.entries})
            depot_word = "depot" if unique_depots == 1 else "depots"
            bid_suffix = f"  \u2014  Build {group.build_id}" if group.build_id else ""
            group.label = (
                f"{group.date}  \u2014  {group.branch}  \u2014  {group.source}"
                f"  ({unique_depots} {depot_word}){bid_suffix}"
            )

    return groups


def get_manifests_for_date(
    depot_id: str, target_date: str
):
    """Return all manifest entries for a specific date (YYYY-MM-DD)."""
    return [e for e in get_depot_manifests(depot_id) if e.date.startswith(target_date)]
