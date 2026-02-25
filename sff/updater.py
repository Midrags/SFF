import asyncio
import re
from typing import Any, Optional
import httpx
import json

from sff.http_utils import get_request
from sff.strings import (
    GITHUB_UPDATE_USERNAME,
    REPO_UPDATE_NAME,
    VERSION,
)


def _parse_version(tag: str) -> tuple[int, ...]:
    """Normalize version tag to a tuple of integers for comparison (e.g. '4.5' -> (4, 5), '4.5.0' -> (4, 5, 0))."""
    # Strip leading 'v' if present (e.g. v4.5.0)
    s = tag.strip().lstrip("vV")
    parts = re.split(r"[.\-]", s)
    out: list[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            break
    return tuple(out)


def is_newer_version(remote_tag: str, current: str) -> bool:
    """Return True if remote_tag is a newer version than current (e.g. 4.6 > 4.5.0)."""
    r = _parse_version(remote_tag)
    c = _parse_version(current)
    # Pad with zeros so (4, 5) compares equal to (4, 5, 0)
    n = max(len(r), len(c))
    r = r + (0,) * (n - len(r))
    c = c + (0,) * (n - len(c))
    return r > c


class Updater:
    """Checks and fetches updates from https://github.com/Midrags/SFF/releases/"""

    _LATEST_URL = (
        f"https://api.github.com/repos/{GITHUB_UPDATE_USERNAME}/{REPO_UPDATE_NAME}/releases/latest"
    )
    _RELEASES_URL = (
        f"https://api.github.com/repos/{GITHUB_UPDATE_USERNAME}/{REPO_UPDATE_NAME}/releases"
    )
    _HEADERS = {"Accept": "application/vnd.github.v3+json", "User-Agent": "SFF-Updater"}

    @staticmethod
    def get_latest_stable() -> Optional[dict[str, Any]]:
        """Fetch the latest stable release from Midrags/SMD_2. Returns None on error."""
        resp = asyncio.run(
            get_request(
                Updater._LATEST_URL,
                "json",
                headers=Updater._HEADERS,
            )
        )
        if resp is not None:
            return resp
        # Fallback: /releases/latest can 404 if latest is draft; fetch list and take first non-draft
        list_resp = asyncio.run(
            get_request(
                Updater._RELEASES_URL,
                "json",
                headers=Updater._HEADERS,
            )
        )
        if not isinstance(list_resp, list):
            return None
        for release in list_resp:
            if release.get("draft") is True or release.get("prerelease") is True:
                continue
            return release
        return None

    @staticmethod
    def get_latest_prerelease() -> Optional[dict[str, Any]]:
        """Returns first prerelease newer than current version, or None."""
        url = Updater._RELEASES_URL
        while True:
            resp = httpx.get(url, headers=Updater._HEADERS)
            releases = json.loads(resp.text)
            for release in releases:
                tag = release.get("tag_name")
                if tag and is_newer_version(tag, VERSION) and release.get("prerelease") is True:
                    return release
            if "next" in resp.links:
                url = resp.links["next"]["url"]
            else:
                break
        return None

    @staticmethod
    def update_available() -> tuple[bool, Optional[dict[str, Any]]]:
        """
        Check if an update is available from Midrags/SMD_2.
        Returns (is_newer, latest_release_dict).
        If fetch fails, returns (False, None). If current >= latest, returns (False, release_dict).
        """
        release = Updater.get_latest_stable()
        if not release:
            return False, None
        remote_tag = release.get("tag_name") or ""
        if not is_newer_version(remote_tag, VERSION):
            return False, release
        return True, release
