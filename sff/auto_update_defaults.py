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

from __future__ import annotations

import logging
import os
import sys
from typing import Callable

from sff.storage.settings import get_setting
from sff.structs import Settings

logger = logging.getLogger(__name__)


def auto_enable_new_games_enabled() -> bool:
    # LumaCore is Windows-only. The LetUpdate override has no effect on
    # Linux where SLSsteam handles update blocking through its own config.
    if sys.platform != "win32":
        return False
    raw = get_setting(Settings.AUTO_ENABLE_UPDATES_NEW_GAMES)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def steam_game_has_pins(steam_path: str | os.PathLike[str] | None, app_id: str | int) -> bool:
    target = str(app_id).strip()
    if not target.isdigit():
        return False
    try:
        from sff.lua.update_pins import discover_games

        return any(str(g.get("app_id") or "") == target for g in discover_games(steam_path))
    except Exception as exc:
        logger.debug("steam_game_has_pins failed for %s: %s", target, exc)
        return False


def apply_new_game_update_default(
    steam_path: str | os.PathLike[str] | None,
    app_id: str | int,
    *,
    was_registered: bool = False,
    log: Callable[[str], None] | None = None,
) -> dict:
    target = str(app_id).strip()
    if not target.isdigit():
        return {"ok": False, "applied": False, "reason": "invalid_app_id"}
    if was_registered:
        return {"ok": True, "applied": False, "reason": "already_registered"}
    if not auto_enable_new_games_enabled():
        return {"ok": True, "applied": False, "reason": "setting_off"}

    try:
        from sff.lua.update_pins import set_game_allow_update

        result = set_game_allow_update(steam_path, target, True)
        applied = bool(result.get("ok") and result.get("target_found"))
        result["applied"] = applied
        if applied and log:
            log(f"Auto Update enabled for new game {target}.")
        return result
    except Exception as exc:
        logger.debug("apply_new_game_update_default failed for %s: %s", target, exc)
        return {"ok": False, "applied": False, "reason": str(exc)}
