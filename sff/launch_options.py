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

"""Read and write per-game Steam launch options via localconfig.vdf."""

import logging
from pathlib import Path
from typing import Optional

import vdf

logger = logging.getLogger(__name__)

_ONLINE_FIX_FLAG = "-onlinefix"


def _find_localconfig(steam_path: Path) -> Optional[Path]:
    userdata = steam_path / "userdata"
    if not userdata.is_dir():
        return None
    for user_dir in sorted(userdata.iterdir()):
        cfg = user_dir / "config" / "localconfig.vdf"
        if cfg.is_file():
            return cfg
    return None


def get_launch_options(steam_path: Path, app_id: str) -> str:
    """Return the current launch options string for *app_id*, or '' if none."""
    cfg = _find_localconfig(steam_path)
    if cfg is None:
        logger.warning("localconfig.vdf not found under %s", steam_path)
        return ""
    try:
        data = vdf.load(cfg.open(encoding="utf-8", errors="replace"))
        apps = (
            data.get("UserLocalConfigStore", {})
            .get("Software", {})
            .get("Valve", {})
            .get("Steam", {})
            .get("Apps", {})
        )
        return apps.get(str(app_id), {}).get("LaunchOptions", "")
    except Exception as exc:
        logger.error("Failed to read launch options: %s", exc)
        return ""


def set_launch_options(steam_path: Path, app_id: str, options: str) -> bool:
    """Overwrite the launch options for *app_id* in localconfig.vdf."""
    cfg = _find_localconfig(steam_path)
    if cfg is None:
        logger.warning("localconfig.vdf not found under %s", steam_path)
        return False
    try:
        with cfg.open(encoding="utf-8", errors="replace") as fh:
            data = vdf.load(fh)
        apps = (
            data.setdefault("UserLocalConfigStore", {})
            .setdefault("Software", {})
            .setdefault("Valve", {})
            .setdefault("Steam", {})
            .setdefault("Apps", {})
        )
        if str(app_id) not in apps:
            apps[str(app_id)] = {}
        apps[str(app_id)]["LaunchOptions"] = options
        with cfg.open("w", encoding="utf-8") as fh:
            vdf.dump(data, fh, pretty=True)
        return True
    except Exception as exc:
        logger.error("Failed to write launch options: %s", exc)
        return False


def online_fix_enabled(steam_path: Path, app_id: str) -> bool:
    """Return True when *_ONLINE_FIX_FLAG* is present in the app's launch options."""
    opts = get_launch_options(steam_path, app_id)
    return _ONLINE_FIX_FLAG in opts.split()


def toggle_online_fix(steam_path: Path, app_id: str) -> bool:
    """Add or remove *_ONLINE_FIX_FLAG* for *app_id*. Returns the new enabled state."""
    opts = get_launch_options(steam_path, app_id)
    tokens = opts.split()
    if _ONLINE_FIX_FLAG in tokens:
        tokens = [t for t in tokens if t != _ONLINE_FIX_FLAG]
        new_state = False
    else:
        tokens.append(_ONLINE_FIX_FLAG)
        new_state = True
    set_launch_options(steam_path, app_id, " ".join(tokens))
    return new_state
