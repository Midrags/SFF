"""
Fetch game names and app details from Steam store (HTTP). No Steam client login.
Used when local ACF is missing and as fallback for DLC check when Steam API times out.
"""

import re
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Store page title: "Game Name on Steam" or "Save 60% on Game Name on Steam"
_STEAM_TITLE_RE = re.compile(
    r"<title>\s*(.+)\s+(?:on|en)\s+Steam\s*</title>",
    re.IGNORECASE | re.DOTALL,
)
_STORE_TIMEOUT = 12.0
_STORE_API_DELAY = 0.4  # seconds between store API calls to avoid rate limit
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _store_get_json(url: str) -> Optional[dict]:
    """GET URL and return JSON. None on failure."""
    try:
        resp = httpx.get(
            url,
            timeout=_STORE_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except (httpx.TimeoutException, httpx.RequestError, ValueError) as e:
        logger.debug("Store API request failed: %s", e)
        return None


def get_app_details_from_store(app_id: int) -> Optional[dict]:
    """
    Fetch app details from Steam Store API (no login).
    Returns dict with "name" (str) and "dlc" (list of int app ids), or None on failure.
    """
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
    data = _store_get_json(url)
    if not data or not isinstance(data, dict):
        return None
    app_data = data.get(str(app_id))
    if not app_data or not app_data.get("success") or "data" not in app_data:
        return None
    inner = app_data["data"]
    name = inner.get("name") or ""
    dlc = inner.get("dlc")
    if not isinstance(dlc, list):
        dlc = []
    dlc_ids = [int(x) for x in dlc if isinstance(x, (int, str)) and str(x).isdigit()]
    return {"name": name, "dlc": dlc_ids}


def get_dlc_list_from_store(base_id: int) -> Optional[tuple[str, list[int]]]:
    """
    Get base app name and DLC app id list from Store API (no Steam client).
    Returns (base_name, dlc_ids) or None on failure.
    """
    details = get_app_details_from_store(base_id)
    if not details:
        return None
    return (details["name"] or f"App {base_id}", details["dlc"])


def get_dlc_names_from_store(dlc_ids: list[int]) -> dict[int, str]:
    """
    Fetch DLC names from Store API (one request per id, with short delay).
    Returns dict mapping app_id -> name; missing names are "DLC <id>".
    """
    result: dict[int, str] = {}
    for i, app_id in enumerate(dlc_ids):
        if i > 0:
            time.sleep(_STORE_API_DELAY)
        details = get_app_details_from_store(app_id)
        if details and details.get("name"):
            result[app_id] = details["name"]
        else:
            result[app_id] = f"DLC {app_id}"
    return result


def get_app_name_from_store(app_id: int) -> Optional[str]:
    """
    Fetch app name from Steam store page (no Steam client login).
    Returns None on failure or if title cannot be parsed.
    """
    url = f"https://store.steampowered.com/app/{app_id}/"
    try:
        resp = httpx.get(
            url,
            timeout=_STORE_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.debug("Store fetch failed for %s: %s", app_id, e)
        return None

    m = _STEAM_TITLE_RE.search(html)
    if not m:
        return None
    name = m.group(1).strip()
    # Trim " en " suffix if present (e.g. Spanish page)
    if " en " in name:
        name = name.split(" en ")[-1].strip()
    # Optional: strip "Save N% on " prefix for cleaner display
    if name.lower().startswith("save ") and " on " in name:
        parts = name.split(" on ", 1)
        if len(parts) == 2 and parts[0].strip().endswith("%"):
            name = parts[1].strip()
    return name if name else None
