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

import json
import os
import re
from pathlib import Path
from typing import Iterable

logger_name = __name__

_ACTIVE_PIN_RE = re.compile(r"^(\s*)setManifestid\s*\(", re.IGNORECASE)
_COMMENTED_PIN_RE = re.compile(r"^(\s*)--\s*(setManifestid\s*\()", re.IGNORECASE)
_PIN_DEPOT_RE = re.compile(r"^\s*(?:--\s*)?setManifestid\s*\(\s*(\d+)", re.IGNORECASE)
_ADDAPPID_RE = re.compile(r"addappid\s*\(\s*(\d+)", re.IGNORECASE)
_ADDAPPID_COMMENT_RE = re.compile(r"addappid\s*\(\s*(\d+)[^)]*\)\s*--\s*(.+)", re.IGNORECASE)
_LOCAL_NAME_CACHE: dict[str, str] | None = None

_SKIP_NAMES = {
    "00_letupdate_override.lua",
    "letupdate_override.lua",
}

_REDIST_DEPOTS: frozenset[int] = frozenset({
    1004, 1005, 1006,
    228500, 228980, 228981, 228982, 228983, 228984, 228985, 228986,
    228987, 228988, 228989, 228990, 229000, 229001, 229002, 229003,
    229004, 229005, 229006, 229007, 229010, 229011, 229012, 229020,
    229030, 229031, 229032, 229033,
})


def stplugin_root(steam_path: str | os.PathLike[str] | None) -> Path | None:
    if not steam_path:
        return None
    root = Path(steam_path).expanduser()
    if not root.is_dir():
        return None
    return root / "config" / "stplug-in"


def _looks_like_game_lua(path: Path) -> bool:
    if path.suffix.lower() != ".lua":
        return False
    name = path.name.lower()
    if name in _SKIP_NAMES or "letupdate_override" in name:
        return False
    return True


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _appid_from_lua(path: Path, text: str) -> str:
    stem = path.stem.strip()
    if stem.isdigit():
        return stem
    match = _ADDAPPID_RE.search(text)
    return match.group(1) if match else ""


def _name_from_lua_comment(app_id: str, text: str) -> str:
    for match in _ADDAPPID_COMMENT_RE.finditer(text):
        if match.group(1) == app_id:
            name = match.group(2).strip()
            if name and not name.lower().startswith(("depot ", "shared from app")):
                return name
    return ""


def _load_local_name_cache() -> dict[str, str]:
    global _LOCAL_NAME_CACHE
    if _LOCAL_NAME_CACHE is not None:
        return _LOCAL_NAME_CACHE
    names: dict[str, str] = {}
    try:
        from sff.utils import sff_data_dir

        cache_dir = sff_data_dir() / "store_metadata"
        paths = [
            cache_dir / "games_appid.json",
            cache_dir / "software_appid.json",
            cache_dir / "games.json",
        ]
        for path in paths:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                for appid, value in data.items():
                    name = ""
                    if isinstance(value, str):
                        name = value
                    elif isinstance(value, dict):
                        name = str(value.get("name") or "")
                    if str(appid).isdigit() and name and str(appid) not in names:
                        names[str(appid)] = name
            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    appid = item.get("appid") or item.get("app_id") or item.get("id")
                    name = item.get("name")
                    if str(appid).isdigit() and name and str(appid) not in names:
                        names[str(appid)] = str(name)
    except Exception:
        pass
    _LOCAL_NAME_CACHE = names
    return names


def _name_from_catalog(app_id: str) -> str:
    if not app_id.isdigit():
        return ""
    return _load_local_name_cache().get(app_id, "") or f"App {app_id}"


def helper_status(steam_path: str | os.PathLike[str] | None) -> dict:
    try:
        from sff.update_prompt_override import _override_path, get_excluded_depots

        target = _override_path(Path(steam_path)) if steam_path else None
        exists = bool(target and target.exists())
        return {
            "exists": exists,
            "path": str(target) if target else "",
            "excluded_depots": sorted(get_excluded_depots(Path(steam_path)) if steam_path else set(), key=int),
        }
    except Exception as exc:
        return {"exists": False, "path": "", "excluded_depots": [], "error": str(exc)}


def _count_pins(text: str) -> tuple[int, int]:
    active = 0
    commented = 0
    for line in text.splitlines():
        if _COMMENTED_PIN_RE.match(line):
            commented += 1
        elif _ACTIVE_PIN_RE.match(line):
            active += 1
    return active, commented


def _pin_depots(text: str) -> set[str]:
    depots: set[str] = set()
    for line in text.splitlines():
        match = _PIN_DEPOT_RE.match(line)
        if match:
            depots.add(match.group(1))
    return depots


def discover_games(steam_path: str | os.PathLike[str] | None) -> list[dict]:
    root = stplugin_root(steam_path)
    if root is None or not root.is_dir():
        return []

    try:
        from sff.update_prompt_override import get_excluded_depots

        global_excluded = get_excluded_depots(steam_path)
    except Exception:
        global_excluded = set()

    seen: set[str] = set()
    games: list[dict] = []
    candidates = sorted(root.glob("*.lua"), key=lambda p: p.name.lower())
    candidates.extend(sorted(root.glob("*/*.lua"), key=lambda p: str(p).lower()))

    for path in candidates:
        if not _looks_like_game_lua(path):
            continue
        text = _read_text(path)
        app_id = _appid_from_lua(path, text)
        if not app_id or app_id in seen:
            continue
        active, commented = _count_pins(text)
        pin_depots = _pin_depots(text)
        if active == 0 and commented == 0:
            continue
        allow_update = active == 0 and commented > 0
        if global_excluded:
            allow_update = not bool(pin_depots & global_excluded)
        seen.add(app_id)
        games.append(
            {
                "app_id": app_id,
                "name": _name_from_lua_comment(app_id, text) or _name_from_catalog(app_id),
                "path": str(path),
                "allow_update": allow_update,
                "active_pins": active,
                "commented_pins": commented,
                "pin_depots": sorted(pin_depots, key=int),
            }
        )

    games.sort(key=lambda g: (g.get("name") or "").lower())
    return games


def set_helper_enabled(steam_path: str | os.PathLike[str] | None, enabled: bool) -> dict:
    try:
        from sff.update_prompt_override import install, remove

        ok = install(Path(steam_path)) if enabled else remove(Path(steam_path))
        status = helper_status(steam_path)
        return {"ok": bool(ok), "enabled": bool(status.get("exists")), "status": status}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "enabled": False, "status": helper_status(steam_path)}


def _rewrite_pin_lines(text: str, allow_update: bool) -> tuple[str, int]:
    changed = 0
    out: list[str] = []
    for line in text.splitlines():
        if allow_update:
            if _COMMENTED_PIN_RE.match(line):
                out.append(line)
                continue
            match = _ACTIVE_PIN_RE.match(line)
            if match:
                out.append(f"{match.group(1)}-- {line[len(match.group(1)):]}")
                changed += 1
                continue
            out.append(line)
            continue

        match = _COMMENTED_PIN_RE.match(line)
        if match:
            out.append(f"{match.group(1)}{line[match.end(1):].lstrip('-').lstrip()}")
            changed += 1
            continue
        out.append(line)

    ending = "\n" if text.endswith(("\n", "\r\n")) else ""
    return "\n".join(out) + ending, changed


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def apply_selection(
    steam_path: str | os.PathLike[str] | None,
    allow_update_app_ids: Iterable[str],
) -> dict:
    allowed = {str(x).strip() for x in allow_update_app_ids if str(x).strip().isdigit()}
    games = discover_games(steam_path)
    changed_games = 0
    changed_lines = 0
    errors: list[dict] = []

    for game in games:
        app_id = str(game.get("app_id") or "")
        path = Path(str(game.get("path") or ""))
        try:
            text = _read_text(path)
            new_text, lines = _rewrite_pin_lines(text, app_id in allowed)
            if lines and new_text != text:
                _atomic_write(path, new_text)
                changed_games += 1
                changed_lines += lines
        except Exception as exc:
            errors.append({"app_id": app_id, "path": str(path), "error": str(exc)})

    global_ok = False
    try:
        from sff.update_prompt_override import install_with_exclusions

        excluded_depots: set[str] = set()
        for game in games:
            app_id = str(game.get("app_id") or "")
            if app_id not in allowed:
                excluded_depots.update(
                    str(x) for x in game.get("pin_depots") or []
                    if str(x).isdigit() and int(x) not in _REDIST_DEPOTS
                )
        global_ok = install_with_exclusions(steam_path, excluded_depots)
    except Exception as exc:
        errors.append({"app_id": "", "path": "00_LetUpdate_override.lua", "error": str(exc)})

    return {
        "ok": not errors,
        "changed_games": changed_games,
        "changed_lines": changed_lines,
        "global_override": global_ok,
        "global_override_removed": False,
        "errors": errors,
        "games": discover_games(steam_path),
    }


def set_game_allow_update(
    steam_path: str | os.PathLike[str] | None,
    app_id: str | int,
    allow_update: bool,
) -> dict:
    target = str(app_id).strip()
    if not target.isdigit():
        return {"ok": False, "error": "invalid app_id", "target_found": False}

    games = discover_games(steam_path)
    target_found = any(str(g.get("app_id") or "") == target for g in games)
    if not target_found:
        return {"ok": False, "error": "no pinned lua found for app_id", "target_found": False}

    selected = {
        str(g.get("app_id") or "")
        for g in games
        if g.get("allow_update") and str(g.get("app_id") or "").isdigit()
    }
    if allow_update:
        selected.add(target)
    else:
        selected.discard(target)

    result = apply_selection(steam_path, selected)
    result["target_app_id"] = target
    result["target_found"] = True
    result["target_allow_update"] = bool(allow_update)
    return result


def apply_selection_json(steam_path: str | os.PathLike[str] | None, payload_json: str) -> str:
    try:
        payload = json.loads(payload_json or "{}")
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"Invalid request: {exc}"})
    selected = payload.get("allow_updates") or []
    if not isinstance(selected, list):
        return json.dumps({"ok": False, "error": "allow_updates must be a list"})
    return json.dumps(apply_selection(steam_path, selected))
