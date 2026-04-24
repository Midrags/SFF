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
Linux desktop shortcut creator with Steam CDN fallback and optional SteamGridDB icons.
"""

import logging
import re
import sys
from io import BytesIO
from pathlib import Path

import requests
from colorama import Fore, Style

logger = logging.getLogger(__name__)

STEAM_CDN_HEADER = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
SGDB_API_BASE = "https://www.steamgriddb.com/api/v2"


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "game"


def _detect_exec_cmd(appid: str) -> str:
    flatpak_dir = Path.home() / ".var" / "app" / "com.valvesoftware.Steam"
    if flatpak_dir.exists():
        return f"flatpak run com.valvesoftware.Steam steam://rungameid/{appid}"
    return f"steam steam://rungameid/{appid}"


def _fetch_icon_steam_cdn(appid: str) -> bytes | None:
    """Download header image from Steam CDN, crop center square, resize to 256×256."""
    try:
        resp = requests.get(STEAM_CDN_HEADER.format(appid=appid), timeout=15)
        if resp.status_code != 200:
            return None
        from PIL import Image
        img = Image.open(BytesIO(resp.content))
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((256, 256), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"Steam CDN icon fetch failed: {e}")
        return None


def _fetch_icon_steamgriddb(appid: str, api_key: str) -> bytes | None:
    """Fetch icon from SteamGridDB API."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(
            f"{SGDB_API_BASE}/games/steam/{appid}",
            headers=headers, timeout=15,
        )
        if resp.status_code != 200:
            return None
        game_data = resp.json().get("data")
        if not game_data:
            return None
        game_id = game_data.get("id")
        if not game_id:
            return None

        resp = requests.get(
            f"{SGDB_API_BASE}/icons/game/{game_id}",
            params={"types": "static", "limit": "1"},
            headers=headers, timeout=15,
        )
        if resp.status_code != 200:
            return None
        icons = resp.json().get("data", [])
        if not icons:
            return None

        icon_url = icons[0].get("url")
        if not icon_url:
            return None
        icon_resp = requests.get(icon_url, timeout=15)
        if icon_resp.status_code != 200:
            return None

        from PIL import Image
        img = Image.open(BytesIO(icon_resp.content))
        img = img.resize((256, 256), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"SteamGridDB icon fetch failed: {e}")
        return None


def _install_icon(appid: str, icon_data: bytes) -> Path | None:
    icon_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    icon_path = icon_dir / f"steam_icon_{appid}.png"
    try:
        icon_path.write_bytes(icon_data)
        return icon_path
    except Exception as e:
        logger.error(f"Failed to save icon: {e}")
        return None


def create_shortcut(
    appid: str,
    game_name: str,
    sgdb_api_key: str = "",
    print_fn=print,
) -> bool:
    """Create a Linux .desktop shortcut for a Steam game.

    Tries SteamGridDB (if key provided) first for a better icon,
    falls back to Steam CDN header image.
    Returns True on success.
    """
    if sys.platform != "linux":
        print_fn(Fore.YELLOW + "Desktop shortcuts are Linux-only." + Style.RESET_ALL)
        return False

    icon_data = None
    if sgdb_api_key:
        print_fn("Fetching icon from SteamGridDB...")
        icon_data = _fetch_icon_steamgriddb(appid, sgdb_api_key)

    if not icon_data:
        print_fn("Fetching icon from Steam CDN...")
        icon_data = _fetch_icon_steam_cdn(appid)

    icon_name = f"steam_icon_{appid}"
    if icon_data:
        installed = _install_icon(appid, icon_data)
        if installed:
            print_fn(Fore.GREEN + f"Icon saved: {installed}" + Style.RESET_ALL)
    else:
        print_fn(Fore.YELLOW + "No icon available — shortcut will use default icon." + Style.RESET_ALL)
        icon_name = "steam"

    safe_name = _safe_filename(game_name)
    exec_cmd = _detect_exec_cmd(appid)
    desktop_content = (
        "[Desktop Entry]\n"
        f"Name={game_name}\n"
        "Comment=Play this game on Steam\n"
        f"Exec={exec_cmd}\n"
        f"Icon={icon_name}\n"
        "Terminal=false\n"
        "Type=Application\n"
        "Categories=Game;\n"
    )

    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / f"{safe_name}.desktop"

    try:
        desktop_file.write_text(desktop_content, encoding="utf-8")
        desktop_file.chmod(0o755)
        print_fn(Fore.GREEN + f"Desktop shortcut created: {desktop_file}" + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.RED + f"Failed to create shortcut: {e}" + Style.RESET_ALL)
        return False
