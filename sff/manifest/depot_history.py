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
        urllib.request.urlretrieve(entry["url"], str(zip_path))
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
      2. Installed system Chrome
      3. Chrome for Testing auto-downloaded to ~/.sff/
    """
    import os, sys
    # 1. Frozen EXE: check bundled chrome
    if getattr(sys, 'frozen', False):
        bundled = Path(sys._MEIPASS) / 'chrome-bundled' / 'chrome.exe'
        if bundled.exists():
            return 'chrome', str(bundled)
    # 2. System Chrome
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return 'chrome', path
    # 3. Auto-download Chrome for Testing
    chrome = _ensure_chrome_for_testing(progress_cb=progress_cb)
    if chrome:
        return 'chrome', chrome
    return 'chrome', ''   # last resort: let SeleniumBase try its own detection


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
            sb.uc_open_with_reconnect(url, 6)
            try:
                sb.wait_for_element('td.tabular-nums', timeout=6)
            except Exception:
                sb.sleep(2)
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


def _fetch_steamdb_batch(
    depot_ids: list[str],
    progress_cb=None,
    app_id=None,
):
    """
    Open ONE SeleniumBase UC browser and scrape the SteamDB depot/manifests page
    for each depot_id sequentially.  Much faster than one browser per depot.
    If *app_id* is given, the first page visit goes to /app/{id}/depots/ to solve
    CF and discover additional depot IDs in the same session.
    Returns {depot_id: [ManifestEntry, ...]}.
    progress_cb(msg: str) is called before each depot if provided.
    """
    if not depot_ids and not app_id:
        return {}
    try:
        from seleniumbase import SB
    except ImportError:
        logger.debug("seleniumbase not installed, skipping SteamDB batch scrape")
        return {}

    results = {}
    browser, binary = _detect_sb_browser(progress_cb=progress_cb)
    sb_kwargs = dict(uc=True, headless=True, block_images=True, browser=browser)
    if binary:
        sb_kwargs["binary_location"] = binary
    cookie_saved = False

    def _try_httpx_with_cookie(did, cf_clearance, user_agent):
        url_h = f"https://www.steamdb.info/depot/{did}/manifests/"
        try:
            r = httpx.get(
                url_h,
                headers=_steamdb_headers_base(user_agent),
                cookies={"cf_clearance": cf_clearance},
                timeout=8, follow_redirects=True,
            )
            if r.status_code == 200:
                return _parse_steamdb_html(r.text)
        except Exception as exc:
            logger.debug("SteamDB batch httpx depot %s failed: %s", did, exc)
        return None

    try:
        with SB(**sb_kwargs) as sb:
            sb.driver.set_page_load_timeout(30)
            sb.driver.set_script_timeout(30)

            # Step 0: visit app/depots page to solve CF + discover extra depots
            extra_depot_ids = []
            if app_id:
                try:
                    app_url = f"https://www.steamdb.info/app/{app_id}/depots/"
                    if progress_cb:
                        try:
                            progress_cb(f"SteamDB: discovering depots for app {app_id}\u2026")
                        except Exception:
                            pass
                    sb.uc_open_with_reconnect(app_url, 5)
                    try:
                        sb.wait_for_element('a[href*="/depot/"]', timeout=7)
                    except Exception:
                        sb.sleep(3)
                    app_html = sb.get_page_source()
                    discovered = _parse_steamdb_app_depots(app_html)
                    depot_id_set = set(depot_ids)
                    extra_depot_ids = [d for d in discovered if d not in depot_id_set]
                    if extra_depot_ids:
                        logger.debug("SteamDB: discovered %d extra depot(s) from app page", len(extra_depot_ids))
                    if not cookie_saved:
                        try:
                            for ck in sb.driver.get_cookies():
                                if ck.get("name") == "cf_clearance":
                                    ua = sb.driver.execute_script("return navigator.userAgent;")
                                    _save_cf_cookie_cache(ck["value"], ua or "")
                                    cookie_saved = True
                                    logger.debug("SteamDB batch: cf_clearance cookie saved from app page")
                                    break
                        except Exception:
                            pass
                except Exception as exc:
                    logger.debug("SteamDB app depots page failed for app %s: %s", app_id, exc)

            all_depot_ids = list(depot_ids) + extra_depot_ids
            n = len(all_depot_ids)

            for i, depot_id in enumerate(all_depot_ids):
                if progress_cb:
                    try:
                        progress_cb(f"SteamDB: depot {i + 1}/{n} ({depot_id})\u2026")
                    except Exception:
                        pass
                url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
                # If we have a valid cookie from this session, try httpx first
                if cookie_saved:
                    cf_c, cf_ua = _get_valid_cf_cookie()
                    if cf_c:
                        time.sleep(random.uniform(0.8, 1.5))
                        entries = _try_httpx_with_cookie(depot_id, cf_c, cf_ua)
                        if entries is not None:
                            results[depot_id] = entries
                            continue
                        # 403 or empty — fall through to browser for this depot
                if i > 0:
                    sb.sleep(1)
                try:
                    sb.uc_open_with_reconnect(url, 5)
                    try:
                        sb.wait_for_element('td.tabular-nums', timeout=7)
                    except Exception:
                        sb.sleep(3)
                    html = sb.get_page_source()
                    entries = _parse_steamdb_html(html)
                    if not entries and 'td.tabular-nums' not in html:
                        logger.debug("SteamDB batch: CF suspected for depot %s, retrying", depot_id)
                        sb.uc_open_with_reconnect(url, 6)
                        sb.sleep(5)
                        entries = _parse_steamdb_html(sb.get_page_source())
                    # After first successful browser load, extract cf_clearance and save
                    if not cookie_saved:
                        try:
                            raw_cookies = sb.driver.get_cookies()
                            for ck in raw_cookies:
                                if ck.get("name") == "cf_clearance":
                                    ua = sb.driver.execute_script("return navigator.userAgent;")
                                    _save_cf_cookie_cache(ck["value"], ua or "")
                                    cookie_saved = True
                                    logger.debug("SteamDB batch: cf_clearance cookie saved to disk")
                                    break
                        except Exception as exc:
                            logger.debug("SteamDB batch: could not extract cf_clearance: %s", exc)
                    logger.debug("SteamDB batch: depot %s -> %d entries", depot_id, len(entries))
                    results[depot_id] = entries
                except Exception as exc:
                    logger.debug("SteamDB batch depot %s failed: %s", depot_id, exc)
                    results[depot_id] = []
    except Exception as exc:
        logger.debug("SteamDB batch browser failed: %s", exc)

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

    # Layer 3 — SeleniumBase batch (guaranteed CF bypass + app depot discovery)
    if remaining or app_id:
        layer3 = _fetch_steamdb_batch(remaining, progress_cb=progress_cb, app_id=app_id)
        for did, entries in layer3.items():
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


def group_by_version(depot_history: dict[str, list[ManifestEntry]]):
    """
    Convert {depot_id: [ManifestEntry]} into a list of VersionGroup, newest-first.
    Groups by (date, branch, source). Mirror entries with non-date values
    (N/A, loading..., local fallback, etc.) are merged into one archive group
    per source.
    """
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
        groups.append(VersionGroup(
            label=label,
            date=sort_date,
            branch=branch,
            source=source,
            entries=entries_list,
            entry_map=entry_map,
        ))

    groups.sort(key=lambda g: g.date, reverse=True)

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
                if re.match(r"\d{4}-\d{2}-\d{2}", e.date)
                and e.date <= group.date
                and e.source != "Steam CM"
            ]
            if not candidates:
                continue  # no real historical data for this depot at this point in time
            best = max(candidates, key=lambda e: e.date)
            pair = (depot_id, best.manifest_id)
            if pair not in set(group.entries):
                group.entries.append(pair)
                group.entry_map[depot_id] = best
                added += 1
        if added:
            unique_depots = len({d for d, _ in group.entries})
            depot_word = "depot" if unique_depots == 1 else "depots"
            group.label = (
                f"{group.date}  \u2014  {group.branch}  \u2014  {group.source}"
                f"  ({unique_depots} {depot_word})"
            )

    return groups


def get_manifests_for_date(
    depot_id: str, target_date: str
):
    """Return all manifest entries for a specific date (YYYY-MM-DD)."""
    return [e for e in get_depot_manifests(depot_id) if e.date.startswith(target_date)]
