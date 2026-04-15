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

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_MIRROR_OWNER = "qwe213312"
_MIRROR_REPO = "k25FCdfEOoEJ42S6"
_GH_API = "https://api.github.com"
_TREE_TTL = 3600
_RESULT_TTL = 300

_TREE: Optional[list] = None
_TREE_FETCHED_AT: float = 0.0
_TREE_MAP: dict[str, list[str]] = {}
_DATES: dict[str, str] = {}
_DATES_DIRTY: bool = False
_RATE_REMAINING: int = 60
_RESULT_CACHE: dict[str, tuple[float, list]] = {}


@dataclass
class ManifestEntry:
    manifest_id: str
    date: str
    branch: str = "public"
    size_mb: float = 0.0
    source: str = ""

    def __str__(self) -> str:
        size_str = f"  ({self.size_mb:.0f} MB)" if self.size_mb else ""
        return f"{self.date}  —  {self.manifest_id}  [{self.branch}]{size_str}"


# ---------------------------------------------------------------------------
# Persistent cache helpers
# ---------------------------------------------------------------------------

def _sff_dir() -> Path:
    p = Path.home() / ".sff"
    p.mkdir(exist_ok=True)
    return p


def _load_dates_cache() -> None:
    global _DATES
    try:
        p = _sff_dir() / "github_dates.json"
        if p.exists():
            _DATES = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("dates cache load error: %s", exc)


def _save_dates_cache() -> None:
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
# Local fallback data (loaded once at import)
# ---------------------------------------------------------------------------

def _load_local_fallbacks() -> tuple[frozenset, dict]:
    lua_dir = Path(__file__).parent.parent / "lua"
    dk_ids: frozenset = frozenset()
    tokens: dict = {}
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

def _gh_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h: dict = {"Accept": "application/vnd.github.v3+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _update_rate_limit(resp: httpx.Response) -> None:
    global _RATE_REMAINING
    try:
        _RATE_REMAINING = int(resp.headers.get("X-RateLimit-Remaining", _RATE_REMAINING))
    except Exception:
        pass


def _get_mirror_tree() -> list[dict]:
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


def _build_tree_map(tree: list[dict]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in tree:
        m = re.match(r"^(\d+)_(\d+)\.manifest$", item.get("path", ""))
        if m:
            result.setdefault(m.group(1), []).append(m.group(2))
    return result


def _fetch_file_date(filename: str) -> str:
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

def _fetch_steam_cm_entries(app_id: str) -> dict[str, list[ManifestEntry]]:
    """Get depot IDs + current manifests with real dates from Steam CM."""
    result: dict[str, list[ManifestEntry]] = {}
    try:
        from sff.steam_client import create_provider_for_current_thread
        prov = create_provider_for_current_thread()
        app_data = prov.get_single_app_info(int(app_id))
        if not app_data:
            return result
        depots_raw: dict = app_data.get("depots", {})
        branches_meta: dict = depots_raw.get("branches", {})
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
    except Exception as exc:
        logger.debug("Steam CM fetch failed for app %s: %s", app_id, exc)
    return result


# ---------------------------------------------------------------------------
# Source 3 — Morrenus SteamCMD
# ---------------------------------------------------------------------------

def _fetch_hubcap_depots(app_id: str) -> list[str]:
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
# Source 5 — SteamDB via SeleniumBase UC mode
# ---------------------------------------------------------------------------

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
        __import__('os').environ.get('USERNAME', '')
    ),
]


def _ensure_chrome_for_testing() -> str:
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
            return str(chrome_exe)
    except Exception as exc:
        logger.debug("Chrome for Testing download failed: %s", exc)
    return ""


def _detect_sb_browser() -> tuple[str, str]:
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
    chrome = _ensure_chrome_for_testing()
    if chrome:
        return 'chrome', chrome
    return 'chrome', ''   # last resort: let SeleniumBase try its own detection


def _fetch_steamdb_seleniumbase(depot_id: str) -> list[ManifestEntry]:
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
            sb.uc_open_with_reconnect(url, 6)
            try:
                sb.wait_for_element('td.tabular-nums', timeout=6)
            except Exception:
                sb.sleep(2)
            entries = _parse_steamdb_html(sb.get_page_source())
            if entries:
                logger.debug("SteamDB SeleniumBase: %d entries for depot %s", len(entries), depot_id)
            return entries
    except Exception as exc:
        logger.debug("SteamDB SeleniumBase failed for depot %s: %s", depot_id, exc)
        return []


def _fetch_steamdb_batch(
    depot_ids: list[str],
    progress_cb=None,
) -> dict[str, list[ManifestEntry]]:
    """
    Open ONE SeleniumBase UC browser and scrape the SteamDB depot/manifests page
    for each depot_id sequentially.  Much faster than one browser per depot.
    Returns {depot_id: [ManifestEntry, ...]}.
    progress_cb(msg: str) is called before each depot if provided.
    """
    if not depot_ids:
        return {}
    try:
        from seleniumbase import SB
    except ImportError:
        logger.debug("seleniumbase not installed, skipping SteamDB batch scrape")
        return {}

    n = len(depot_ids)
    results: dict[str, list[ManifestEntry]] = {}
    browser, binary = _detect_sb_browser()
    sb_kwargs = dict(uc=True, headless=True, block_images=True, browser=browser)
    if binary:
        sb_kwargs["binary_location"] = binary
    try:
        with SB(**sb_kwargs) as sb:
            for i, depot_id in enumerate(depot_ids):
                if progress_cb:
                    try:
                        progress_cb(f"SteamDB: depot {i + 1}/{n} ({depot_id})…")
                    except Exception:
                        pass
                # Short pause between requests to avoid Cloudflare rate-limiting
                if i > 0:
                    sb.sleep(1)
                url = f"https://www.steamdb.info/depot/{depot_id}/manifests/"
                try:
                    sb.uc_open_with_reconnect(url, 4)
                    # Wait for manifest table cell; fall back to short sleep if absent
                    try:
                        sb.wait_for_element('td.tabular-nums', timeout=3)
                    except Exception:
                        sb.sleep(1)
                    html = sb.get_page_source()
                    entries = _parse_steamdb_html(html)
                    # If 0 entries and page looks like a CF challenge, retry once
                    if not entries and 'td.tabular-nums' not in html:
                        logger.debug("SteamDB batch: CF suspected for depot %s, retrying", depot_id)
                        sb.uc_open_with_reconnect(url, 5)
                        sb.sleep(3)
                        entries = _parse_steamdb_html(sb.get_page_source())
                    logger.debug(
                        "SteamDB batch: depot %s -> %d entries", depot_id, len(entries)
                    )
                    results[depot_id] = entries
                except Exception as exc:
                    logger.debug("SteamDB batch depot %s failed: %s", depot_id, exc)
                    results[depot_id] = []
    except Exception as exc:
        logger.debug("SteamDB batch browser failed: %s", exc)

    return results


def _fetch_steamdb(depot_id: str) -> list[ManifestEntry]:
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


def _parse_steamdb_html(html: str) -> list[ManifestEntry]:
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

    entries: list[ManifestEntry] = []
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Find whichever cell holds the manifest ID (15+ digit number)
            manifest_id: str = ""
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
    seen: set[str] = set()
    unique: list[ManifestEntry] = []
    for e in entries:
        if e.manifest_id not in seen:
            seen.add(e.manifest_id)
            unique.append(e)

    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_depot_key(depot_id: str) -> bool:
    """Return True if this depot has a known decryption key in fallback_depotkeys."""
    return str(depot_id) in _DEPOT_KEY_IDS


def get_depot_manifests(depot_id: str, fetch_dates: bool = True,
                        force_refresh: bool = False) -> list[ManifestEntry]:
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

    entries: list[ManifestEntry] = []
    seen: set[str] = set()

    def _add(e: ManifestEntry) -> None:
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

    # Source 5 — SteamDB last resort
    if not entries:
        for e in _fetch_steamdb(depot_id):
            _add(e)

    def _sort_key(e: ManifestEntry) -> str:
        return e.date if re.match(r"\d{4}-\d{2}-\d{2}", e.date) else "0000-00-00"

    entries.sort(key=_sort_key, reverse=True)
    _RESULT_CACHE[depot_id] = (time.time(), entries)
    return entries


def get_depots_for_app(app_id: str, progress_cb=None) -> dict[str, list[ManifestEntry]]:
    """
    Return {depot_id: [ManifestEntry, ...]} for all depots of an app.
    Depot IDs + current manifests come from Steam CM (Source 1).
    Falls back to Morrenus (Source 3) if Steam CM fails for depot IDs.
    Historical manifests come from get_depot_manifests() per depot.
    progress_cb(msg: str) is forwarded to the SteamDB batch scraper.
    """
    app_id = str(app_id)

    # Source 1: Steam CM — gives depot IDs + current manifests with real dates
    steam_entries = _fetch_steam_cm_entries(app_id)
    depot_ids = list(steam_entries.keys())

    # Source 3: Hubcap/SteamCMD fallback if Steam CM returned nothing
    if not depot_ids:
        depot_ids = _fetch_hubcap_depots(app_id)

    if not depot_ids:
        return {}

    result: dict[str, list[ManifestEntry]] = {}
    for depot_id in depot_ids:
        merged: list[ManifestEntry] = list(steam_entries.get(depot_id, []))
        seen: set[str] = {e.manifest_id for e in merged}
        # fetch_dates=False: avoid exhausting the 60/hr GitHub rate limit on bulk load
        for e in get_depot_manifests(depot_id, fetch_dates=False):
            if e.manifest_id not in seen:
                seen.add(e.manifest_id)
                merged.append(e)
        if merged:
            def _sort_key(e: ManifestEntry) -> str:
                return e.date if re.match(r"\d{4}-\d{2}-\d{2}", e.date) else "0000-00-00"
            merged.sort(key=_sort_key, reverse=True)
            result[depot_id] = merged

    # Source 5 — SteamDB batch: scrape ALL Steam CM depots so every depot gets real dated
    # history (DLC depots with undated mirror entries would otherwise be silently skipped).
    needs_steamdb = list(depot_ids)  # Steam CM is authoritative — always scrape all
    if needs_steamdb:
        logger.debug("SteamDB batch scraping all %d Steam CM depots for historical data", len(needs_steamdb))
        for did, sdb_entries in _fetch_steamdb_batch(needs_steamdb, progress_cb=progress_cb).items():
            # Deduplicate on (manifest_id, date) so a depot that only has 1 manifest
            # (DLC depots) still appears under its historical date even when Steam CM
            # already reported the same manifest under the current build date.
            current_seen = {(e.manifest_id, e.date) for e in result.get(did, [])}
            new_entries = [e for e in sdb_entries if (e.manifest_id, e.date) not in current_seen]
            if new_entries:
                result.setdefault(did, [])
                result[did].extend(new_entries)
                def _sort_key2(e: ManifestEntry) -> str:
                    return e.date if re.match(r"\d{4}-\d{2}-\d{2}", e.date) else "0000-00-00"
                result[did].sort(key=_sort_key2, reverse=True)

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


def group_by_version(depot_history: dict[str, list[ManifestEntry]]) -> list["VersionGroup"]:
    """
    Convert {depot_id: [ManifestEntry]} into a list of VersionGroup, newest-first.
    Groups by (date, branch, source). Mirror entries with non-date values
    (N/A, loading..., local fallback, etc.) are merged into one archive group
    per source.
    """
    # bucket key -> list of (depot_id, entry)
    buckets: dict[tuple, list[tuple[str, ManifestEntry]]] = {}

    for depot_id, entries in depot_history.items():
        for entry in entries:
            date = entry.date
            is_real_date = bool(re.match(r"\d{4}-\d{2}-\d{2}", date))
            bucket_date = date if is_real_date else "__archive__"
            key = (bucket_date, entry.branch, entry.source)
            buckets.setdefault(key, []).append((depot_id, entry))

    groups: list[VersionGroup] = []
    for (bucket_date, branch, source), items in buckets.items():
        unique_depots = len({d for d, _ in items})
        depot_word = "depot" if unique_depots == 1 else "depots"
        if bucket_date == "__archive__":
            label = f"Unknown date  —  {branch}  —  {source}  ({unique_depots} {depot_word})"
            sort_date = "0000-00-00"
        else:
            label = f"{bucket_date}  —  {branch}  —  {source}  ({unique_depots} {depot_word})"
            sort_date = bucket_date

        entry_map: dict[str, ManifestEntry] = {}
        entries_list: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
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

        depots_in_group: set[str] = {depot_id for depot_id, _ in group.entries}
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
) -> list[ManifestEntry]:
    """Return all manifest entries for a specific date (YYYY-MM-DD)."""
    return [e for e in get_depot_manifests(depot_id) if e.date.startswith(target_date)]
