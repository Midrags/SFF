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
from typing import Optional, Tuple

import vdf

logger = logging.getLogger(__name__)

_ONLINE_FIX_FLAG = "-onlinefix"


def _is_steam_running() -> bool:
    """True when steam.exe is alive — local check to avoid pulling sff.processes."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                if (proc.info.get("name") or "").lower() == "steam.exe":
                    return True
            except psutil.Error:
                continue
    except Exception:
        pass
    return False


def _active_steamid3(steam_path: Path) -> Optional[str]:
    """Return the SteamID3 (the userdata folder name) of the most recently used account.

    Reads `<steam>/config/loginusers.vdf` and picks the entry with `MostRecent=1`,
    falling back to `Timestamp` when no MostRecent flag is set. Result is the lower
    32 bits of SteamID64, which is what the userdata folder uses.
    """
    cfg = steam_path / "config" / "loginusers.vdf"
    if not cfg.is_file():
        return None
    try:
        with cfg.open(encoding="utf-8", errors="replace") as fh:
            data = vdf.load(fh)
    except Exception as exc:
        logger.warning("loginusers.vdf parse failed: %s", exc)
        return None

    users = data.get("users", {}) if isinstance(data, dict) else {}
    if not isinstance(users, dict) or not users:
        return None

    def _flag(entry: dict, key: str) -> int:
        val = entry.get(key, "0")
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    # Prefer MostRecent=1, then highest Timestamp.
    chosen_id64 = None
    chosen_ts = -1
    for sid64, entry in users.items():
        if not isinstance(entry, dict):
            continue
        if _flag(entry, "MostRecent") == 1:
            chosen_id64 = sid64
            break
        ts = _flag(entry, "Timestamp")
        if ts > chosen_ts:
            chosen_ts = ts
            chosen_id64 = sid64

    if not chosen_id64:
        return None
    try:
        return str(int(chosen_id64) & 0xFFFFFFFF)
    except ValueError:
        return None


def _find_localconfig(steam_path: Path) -> Optional[Path]:
    """Return localconfig.vdf for the active account, falling back to first folder."""
    userdata = steam_path / "userdata"
    if not userdata.is_dir():
        return None

    sid3 = _active_steamid3(steam_path)
    if sid3:
        cfg = userdata / sid3 / "config" / "localconfig.vdf"
        if cfg.is_file():
            return cfg
        logger.warning("active SteamID3 %s has no localconfig.vdf, falling back", sid3)

    for user_dir in sorted(userdata.iterdir()):
        cfg = user_dir / "config" / "localconfig.vdf"
        if cfg.is_file():
            return cfg
    return None


def _get_ci(d: dict, key: str):
    """Case-insensitive dict.get for VDF keys (Steam mixes Apps/apps, Software/software etc.)."""
    if not isinstance(d, dict):
        return None, None
    target = key.lower()
    for k, v in d.items():
        if isinstance(k, str) and k.lower() == target:
            return k, v
    return None, None


def _setdefault_ci(d: dict, key: str, default):
    """Case-insensitive setdefault. Reuses the existing key casing if present."""
    real_key, val = _get_ci(d, key)
    if real_key is None:
        d[key] = default
        return d[key]
    if val is None:
        d[real_key] = default
        return d[real_key]
    return val


def _navigate_apps(data: dict, create: bool = False) -> tuple[dict | None, str | None]:
    """Walk to UserLocalConfigStore/Software/Valve/Steam/apps respecting actual key case.

    Returns (apps_dict, "ok"|reason). When create=True, missing levels are created
    using the canonical case Steam itself uses (lowercase apps, capitalised parents).
    """
    path = [
        ("UserLocalConfigStore", "UserLocalConfigStore"),
        ("Software",             "Software"),
        ("Valve",                "Valve"),
        ("Steam",                "Steam"),
        ("apps",                 "apps"),
    ]
    node = data
    for label, default_case in path:
        if not isinstance(node, dict):
            return None, f"{label}: parent is not a dict"
        real_key, child = _get_ci(node, label)
        if child is None:
            if not create:
                return None, f"{label}: missing"
            node[default_case] = {}
            child = node[default_case]
        node = child
    return node, "ok"


def get_launch_options(steam_path: Path, app_id: str) -> str:
    """Return the current launch options string for *app_id*, or '' if none."""
    cfg = _find_localconfig(steam_path)
    if cfg is None:
        logger.warning("localconfig.vdf not found under %s", steam_path)
        return ""
    try:
        with cfg.open(encoding="utf-8", errors="replace") as fh:
            data = vdf.load(fh)
        apps, _ = _navigate_apps(data, create=False)
        if apps is None:
            return ""
        _, app_block = _get_ci(apps, str(app_id))
        if not isinstance(app_block, dict):
            return ""
        _, opts = _get_ci(app_block, "LaunchOptions")
        return opts if isinstance(opts, str) else ""
    except Exception as exc:
        logger.error("Failed to read launch options: %s", exc)
        return ""


def set_launch_options(steam_path: Path, app_id: str, options: str) -> bool:
    """Overwrite the launch options for *app_id* in localconfig.vdf.

    Refuses to write while Steam is running — Steam holds its own copy in memory
    and writes it back on shutdown, silently clobbering external edits.
    """
    if _is_steam_running():
        logger.error("Refusing to write launch options while Steam is running")
        return False

    cfg = _find_localconfig(steam_path)
    if cfg is None:
        logger.warning("localconfig.vdf not found under %s", steam_path)
        return False
    try:
        with cfg.open(encoding="utf-8", errors="replace") as fh:
            data = vdf.load(fh)
        apps, status = _navigate_apps(data, create=True)
        if apps is None:
            logger.error("could not navigate to apps section: %s", status)
            return False

        # Reuse existing app key casing if present, otherwise create with the
        # numeric app_id as-is (Steam writes them as raw digits anyway).
        real_app_key, app_block = _get_ci(apps, str(app_id))
        if app_block is None:
            apps[str(app_id)] = {}
            app_block = apps[str(app_id)]
        elif real_app_key and real_app_key != str(app_id):
            # unusual, but keep the casing Steam already chose
            pass

        # Reuse existing LaunchOptions key casing.
        real_opts_key, _ = _get_ci(app_block, "LaunchOptions")
        opts_key = real_opts_key or "LaunchOptions"
        app_block[opts_key] = options

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


def toggle_online_fix(steam_path: Path, app_id: str) -> Tuple[bool, str]:
    """Add or remove *_ONLINE_FIX_FLAG* for *app_id*.

    Returns ``(success, message)`` where message describes the resulting state
    or the reason for failure (e.g. Steam still running).
    """
    if _is_steam_running():
        return False, (
            "Steam is running — close Steam first. Steam keeps localconfig.vdf "
            "in memory and overwrites external edits on exit."
        )

    opts = get_launch_options(steam_path, app_id)
    tokens = opts.split()
    if _ONLINE_FIX_FLAG in tokens:
        tokens = [t for t in tokens if t != _ONLINE_FIX_FLAG]
        new_state = False
    else:
        tokens.append(_ONLINE_FIX_FLAG)
        new_state = True

    if not set_launch_options(steam_path, app_id, " ".join(tokens)):
        return False, "Failed to write localconfig.vdf — see log"

    state = "enabled" if new_state else "disabled"
    return True, f"LC Online Fix {state} for App {app_id}. Start Steam to apply."
