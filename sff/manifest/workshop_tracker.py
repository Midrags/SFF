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

"""Track downloaded workshop items for update detection."""

import json
import logging
from pathlib import Path
from typing import Any

from sff.utils import root_folder

logger = logging.getLogger(__name__)

TRACKER_FILE = root_folder(outside_internal=True) / "workshop_tracker.json"


def _load() -> dict[str, Any]:
    try:
        if TRACKER_FILE.exists():
            with TRACKER_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Failed to load workshop tracker: %s", e)
    return {"items": []}


def _save(data: dict[str, Any]) -> None:
    try:
        TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TRACKER_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save workshop tracker: %s", e)


def _key(app_id: str, workshop_id: int) -> str:
    return f"{app_id}:{workshop_id}"


def add(app_id: str, workshop_id: int, time_updated: int) -> None:
    data = _load()
    key = _key(app_id, workshop_id)
    items = {_key(str(i.get("app_id", "")), int(i.get("workshop_id", 0))): i for i in data.get("items", [])}
    items[key] = {
        "app_id": app_id,
        "workshop_id": workshop_id,
        "time_updated": time_updated,
    }
    data["items"] = list(items.values())
    _save(data)


def get_all() -> list[tuple[str, int, int]]:
    data = _load()
    result = []
    for item in data.get("items", []):
        try:
            app_id = str(item.get("app_id", ""))
            workshop_id = int(item.get("workshop_id", 0))
            time_updated = int(item.get("time_updated", 0))
            if app_id and workshop_id:
                result.append((app_id, workshop_id, time_updated))
        except (TypeError, ValueError):
            continue
    return result


def update_time(app_id: str, workshop_id: int, time_updated: int) -> None:
    add(app_id, workshop_id, time_updated)


def remove(app_id: str, workshop_id: int) -> None:
    data = _load()
    key = _key(app_id, workshop_id)
    items = [
        i
        for i in data.get("items", [])
        if _key(str(i.get("app_id", "")), int(i.get("workshop_id", 0))) != key
    ]
    data["items"] = items
    _save(data)
