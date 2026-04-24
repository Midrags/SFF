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
Game update tracker — saves depot manifest IDs after download,
checks them against the Steam API for updates.
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


def _get_tracking_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "")
        if base:
            return Path(base) / "SteaMidra" / "depots"
    return Path.home() / ".local" / "share" / "SteaMidra" / "depots"


def save_depot_tracking(appid: str, manifests: dict, token: str = "") -> bool:
    """Save depot:manifest pairs for a game after successful download.

    File format per line: ``depot_id:manifest_id[:token]``
    Token is only written on the first line (per-app, not per-depot).
    """
    tracking_dir = _get_tracking_dir()
    tracking_dir.mkdir(parents=True, exist_ok=True)
    depot_file = tracking_dir / f"{appid}.depot"
    try:
        lines = []
        for depot_id, manifest_id in manifests.items():
            entry = f"{depot_id}:{manifest_id}"
            if token and not lines:
                entry += f":{token}"
            lines.append(entry)
        depot_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"Saved depot tracking for AppID {appid}: {len(manifests)} depots")
        return True
    except Exception as e:
        logger.error(f"Failed to save depot tracking for {appid}: {e}")
        return False


def _read_tracked_games() -> dict:
    """Read all tracked games.

    Returns ``{appid: {depot_id: manifest_id, ...}, ...}``
    Also returns tokens in a separate dict.
    """
    tracking_dir = _get_tracking_dir()
    games = {}
    tokens = {}
    if not tracking_dir.exists():
        return games
    for f in tracking_dir.glob("*.depot"):
        appid = f.stem
        try:
            content = f.read_text(encoding="utf-8").strip()
            depots = {}
            for line in content.splitlines():
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    depots[parts[0]] = parts[1]
                    if len(parts) >= 3 and parts[2].strip():
                        tokens[appid] = parts[2].strip()
            if depots:
                games[appid] = depots
        except Exception as e:
            logger.warning(f"Failed to read depot file {f}: {e}")
    return games


def check_game_updates(provider) -> List[Tuple[str, str, str]]:
    """Check all tracked games for updates.

    Returns list of ``(appid, status, detail)`` where status is one of:
    ``up_to_date``, ``update_available``, ``cannot_determine``
    """
    games = _read_tracked_games()
    if not games:
        return []

    results = []
    app_ids = list(games.keys())

    batch_size = 20
    all_info = {}
    for i in range(0, len(app_ids), batch_size):
        batch = app_ids[i : i + batch_size]
        try:
            info = provider.get_app_info([int(a) for a in batch])
            if info:
                all_info.update(info)
        except Exception as e:
            logger.warning(f"Failed to fetch product info for batch: {e}")
            for appid in batch:
                results.append((appid, "cannot_determine", f"API error: {e}"))

    for appid, saved_depots in games.items():
        if appid in [r[0] for r in results]:
            continue
        app_info = all_info.get(int(appid)) or all_info.get(appid)
        if not app_info:
            results.append((appid, "cannot_determine", "No info from Steam API"))
            continue

        try:
            depots_info = app_info.get("depots", {})
            updated = False
            details = []
            for depot_id, saved_manifest in saved_depots.items():
                depot = depots_info.get(str(depot_id), {})
                manifests = depot.get("manifests", {})
                current = manifests.get("public")
                if current and str(current) != str(saved_manifest):
                    updated = True
                    details.append(f"depot {depot_id}: {saved_manifest[:12]}.. → {str(current)[:12]}..")
            if updated:
                results.append((appid, "update_available", "; ".join(details)))
            else:
                results.append((appid, "up_to_date", ""))
        except Exception as e:
            results.append((appid, "cannot_determine", f"Parse error: {e}"))

    return results
