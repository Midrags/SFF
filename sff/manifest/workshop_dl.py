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

"""Workshop item file downloader — 4 cascading methods."""

import logging
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_STEAMAPI_DETAILS_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
)
_GGNETWORK_URL = "https://api.ggntw.com/steam.request"
_STEAMCMD_DL_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _steamcmd_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "SteaMidra" / "steamcmd"


def _steamcmd_exe() -> Path:
    d = _steamcmd_dir()
    return d / ("steamcmd.exe" if sys.platform == "win32" else "steamcmd.sh")


def ensure_steamcmd(log: Callable[[str], None] = print) -> Optional[Path]:
    """Download and extract SteamCMD if not present. Returns path or None."""
    exe = _steamcmd_exe()
    if exe.exists():
        return exe
    log("SteamCMD not found — downloading...")
    d = _steamcmd_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        resp = httpx.get(_STEAMCMD_DL_URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        zip_path = d / "steamcmd.zip"
        zip_path.write_bytes(resp.content)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(d)
        zip_path.unlink(missing_ok=True)
        if exe.exists():
            log(f"SteamCMD ready at {exe}")
            return exe
        log("[!] SteamCMD extraction failed — exe not found after extract")
        return None
    except Exception as e:
        log(f"[!] SteamCMD download failed: {e}")
        return None


def _get_workshop_file_url(item_id: str) -> Optional[str]:
    """SteamWebAPI: fetch file_url from published file details."""
    try:
        resp = httpx.post(
            _STEAMAPI_DETAILS_URL,
            data={"itemcount": "1", "publishedfileids[0]": item_id},
            headers={"User-Agent": _CHROME_UA},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            details = (
                data.get("response", {})
                .get("publishedfiledetails", [{}])[0]
            )
            url = details.get("file_url", "")
            return url if url else None
    except Exception as e:
        logger.debug("SteamWebAPI file_url fetch failed: %s", e)
    return None


def _ggnetwork_download_url(item_id: str) -> Optional[str]:
    """GGNetwork API: returns a time-limited direct download URL."""
    item_url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"
    try:
        resp = httpx.post(
            _GGNETWORK_URL,
            json={"url": item_url},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://ggntw.com",
                "Referer": "https://ggntw.com/",
                "User-Agent": _CHROME_UA,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            dl = (
                data.get("download_url")
                or data.get("url")
                or data.get("link")
                or data.get("file")
                or data.get("download")
            )
            if not dl and isinstance(data.get("data"), dict):
                dl = (
                    data["data"].get("download_url")
                    or data["data"].get("url")
                    or data["data"].get("link")
                    or data["data"].get("file")
                )
            return dl if dl else None
        logger.debug("GGNetwork returned HTTP %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.debug("GGNetwork request failed: %s", e)
    return None


def _download_file(url: str, dest: Path, log: Callable[[str], None]) -> bool:
    """Stream-download url to dest. Returns True on success."""
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": _CHROME_UA},
            timeout=120,
            follow_redirects=True,
        ) as resp:
            if resp.status_code != 200:
                log(f"[!] HTTP {resp.status_code} downloading from {url}")
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    fh.write(chunk)
        return dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        log(f"[!] Download error: {e}")
        return False


def _run_steamcmd(
    game_id: str,
    item_id: str,
    output_dir: Path,
    username: str = "anonymous",
    password: str = "",
    log: Callable[[str], None] = print,
) -> bool:
    """Run SteamCMD to download a workshop item. Returns True if output dir has files."""
    steamcmd = ensure_steamcmd(log)
    if steamcmd is None:
        return False
    output_dir.mkdir(parents=True, exist_ok=True)
    if username.lower() == "anonymous":
        login_args = ["+login", "anonymous"]
    else:
        login_args = ["+login", username, password] if password else ["+login", username]
    cmd = (
        [str(steamcmd)]
        + login_args
        + [
            "+force_install_dir", str(output_dir),
            "+workshop_download_item", str(game_id), str(item_id), "validate",
            "+quit",
        ]
    )
    log(f"Running SteamCMD: {' '.join(cmd[:5])} ...")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=False,
            timeout=300,
            cwd=str(_steamcmd_dir()),
        )
        item_dir = (
            output_dir
            / "steamapps"
            / "workshop"
            / "content"
            / str(game_id)
            / str(item_id)
        )
        if item_dir.exists() and any(item_dir.iterdir()):
            log(f"[OK] SteamCMD download complete: {item_dir}")
            return True
        log(f"[!] SteamCMD exited {proc.returncode} — output dir empty")
        return False
    except subprocess.TimeoutExpired:
        log("[!] SteamCMD timed out after 5 minutes")
        return False
    except Exception as e:
        log(f"[!] SteamCMD error: {e}")
        return False


def download_workshop_item(
    item_id: str,
    game_id: str,
    output_dir: Path,
    steam_username: str = "anonymous",
    steam_password: str = "",
    log: Callable[[str], None] = print,
) -> dict:
    """Try all 4 methods to download a workshop item.

    Returns {
        "success": bool,
        "method": str,
        "path": str | None,
        "error": str | None,
    }
    """
    result = {"success": False, "method": "", "path": None, "error": None}

    # Method 1: SteamWebAPI direct file_url
    log("Method 1: SteamWebAPI direct download...")
    file_url = _get_workshop_file_url(item_id)
    if file_url:
        dest = output_dir / f"{item_id}_direct{Path(file_url.split('?')[0]).suffix or '.zip'}"
        if _download_file(file_url, dest, log):
            log(f"[OK] Method 1 succeeded: {dest.name}")
            result.update({"success": True, "method": "SteamWebAPI", "path": str(dest)})
            return result
        log("[!] Method 1: download failed")
    else:
        log("Method 1: no direct file_url (not a legacy item)")

    # Method 2: GGNetwork API
    log("Method 2: GGNetwork API...")
    gg_url = _ggnetwork_download_url(item_id)
    if gg_url:
        dest = output_dir / f"{item_id}_ggnetwork.zip"
        if _download_file(gg_url, dest, log):
            log(f"[OK] Method 2 succeeded: {dest.name}")
            result.update({"success": True, "method": "GGNetwork", "path": str(dest)})
            return result
        log("[!] Method 2: GGNetwork URL expired or download failed")
    else:
        log("[!] Method 2: GGNetwork did not return a download URL (item not cached)")

    # Method 3: SteamCMD anonymous
    log("Method 3: SteamCMD anonymous...")
    steamcmd_out = output_dir / "steamcmd_content"
    if _run_steamcmd(game_id, item_id, steamcmd_out, "anonymous", "", log):
        item_dir = (
            steamcmd_out
            / "steamapps"
            / "workshop"
            / "content"
            / str(game_id)
            / str(item_id)
        )
        result.update({"success": True, "method": "SteamCMD (anonymous)", "path": str(item_dir)})
        return result

    # Method 4: SteamCMD authenticated
    if steam_username and steam_username.lower() != "anonymous":
        log("Method 4: SteamCMD authenticated...")
        if _run_steamcmd(game_id, item_id, steamcmd_out, steam_username, steam_password, log):
            item_dir = (
                steamcmd_out
                / "steamapps"
                / "workshop"
                / "content"
                / str(game_id)
                / str(item_id)
            )
            result.update(
                {"success": True, "method": "SteamCMD (authenticated)", "path": str(item_dir)}
            )
            return result
    else:
        log("Method 4: skipped (no Steam username configured)")

    result["error"] = (
        "All 4 methods failed. "
        "The item may require authentication or may not be publicly available."
    )
    log(f"[!] {result['error']}")
    return result


def parse_workshop_item_id(url_or_id: str) -> Optional[str]:
    """Extract item ID from a Steam Workshop URL or bare ID string."""
    match = re.search(r"(?:id=|filedetails/\?id=|workshopdetails/\?id=)(\d+)", url_or_id)
    if match:
        return match.group(1)
    if url_or_id.strip().isdigit():
        return url_or_id.strip()
    return None
