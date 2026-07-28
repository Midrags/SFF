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

from dataclasses import dataclass
from typing import Iterable

from sff.lua.provider import get_entry, is_valid_key, load_provider
from sff.lua.update_pins import _REDIST_DEPOTS


@dataclass
class LuaDepot:
    depot_id: str
    key: str
    name: str = ""
    parent_appid: str = ""
    parent_name: str = ""
    manifest_id: str = ""
    manifest_size: int = 0


@dataclass
class LuaDlc:
    app_id: str
    name: str = ""
    token: str = ""


def _comment(text: str) -> str:
    text = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:180]


def _line_with_comment(line: str, text: str) -> str:
    text = _comment(text)
    return f"{line} -- {text}" if text else line


def _depot_from_any(item, manifests: dict | None = None, provider: dict | None = None) -> LuaDepot | None:
    if isinstance(item, LuaDepot):
        return item
    _prov = provider if provider is not None else {}
    if isinstance(item, dict):
        depot_id = str(item.get("depot_id") or item.get("id") or "")
        key = str(item.get("key") or item.get("decryption_key") or "")
        entry = _prov.get(depot_id) or get_entry(depot_id)
        return LuaDepot(
            depot_id=depot_id,
            key=key or str(entry.get("key") or ""),
            name=str(item.get("name") or entry.get("name") or f"Depot {depot_id}"),
            parent_appid=str(item.get("parent_appid") or entry.get("parent_appid") or ""),
            parent_name=str(item.get("parent_name") or entry.get("parent_name") or ""),
            manifest_id=str(item.get("manifest_id") or (manifests or {}).get(depot_id) or ""),
            manifest_size=int(item.get("manifest_size") or 0),
        )
    depot_id = str(getattr(item, "depot_id", ""))
    key = str(getattr(item, "decryption_key", "") or getattr(item, "key", ""))
    entry = _prov.get(depot_id) or get_entry(depot_id)
    return LuaDepot(
        depot_id=depot_id,
        key=key or str(entry.get("key") or ""),
        name=str(entry.get("name") or f"Depot {depot_id}"),
        parent_appid=str(entry.get("parent_appid") or ""),
        parent_name=str(entry.get("parent_name") or ""),
        manifest_id=str((manifests or {}).get(depot_id) or ""),
        manifest_size=int(getattr(item, "manifest_size", 0) or 0),
    )


def render_grouped_lua(
    app_id: str,
    app_name: str = "",
    depots: Iterable = (),
    manifest_overrides: dict | None = None,
    dlcs: Iterable[LuaDlc | dict | str] = (),
) -> str:
    manifests = {str(k): str(v) for k, v in (manifest_overrides or {}).items() if str(v).strip().isdigit()}
    main_depots: list[LuaDepot] = []
    shared_depots: list[LuaDepot] = []
    app_id_str = str(app_id)

    provider = load_provider()
    seen_depots: set[str] = set()
    for raw in depots:
        depot = _depot_from_any(raw, manifests, provider)
        if not depot or not depot.depot_id or depot.depot_id in seen_depots:
            continue
        if not is_valid_key(depot.key):
            continue
        depot.manifest_id = depot.manifest_id or manifests.get(depot.depot_id, "")
        seen_depots.add(depot.depot_id)
        if depot.parent_appid and depot.parent_appid != app_id_str:
            shared_depots.append(depot)
        elif int(depot.depot_id) in _REDIST_DEPOTS:
            depot.parent_appid = "1007" if int(depot.depot_id) in (1004, 1005, 1006) else "228980"
            shared_depots.append(depot)
        else:
            main_depots.append(depot)

    lines: list[str] = ["-- MAIN APPLICATION"]
    base_entry = provider.get(app_id_str, {})
    base_key = str(base_entry.get("key") or "")
    if base_key and is_valid_key(base_key):
        lines.append(_line_with_comment(
            f'addappid({app_id_str}, 1, "{base_key.lower()}")',
            app_name,
        ))
    else:
        lines.append(_line_with_comment(f"addappid({app_id_str})", app_name))

    if main_depots:
        lines.extend(["", "-- MAIN APP DEPOTS"])
        for depot in sorted(main_depots, key=lambda d: int(d.depot_id)):
            lines.append(_line_with_comment(
                f'addappid({depot.depot_id}, 1, "{depot.key.lower()}")',
                depot.name or f"Depot {depot.depot_id}",
            ))
            if depot.manifest_id:
                size_part = f", {depot.manifest_size}" if depot.manifest_size else ""
                lines.append(f'setManifestid({depot.depot_id}, "{depot.manifest_id}"{size_part})')

    if shared_depots:
        lines.extend(["", "-- SHARED DEPOTS (from other apps)"])
        for depot in sorted(shared_depots, key=lambda d: int(d.depot_id)):
            label = depot.name or f"Depot {depot.depot_id}"
            if depot.parent_appid:
                label += f" (Shared from App {depot.parent_appid})"
            lines.append(_line_with_comment(
                f'addappid({depot.depot_id}, 1, "{depot.key.lower()}")',
                label,
            ))
            if depot.manifest_id:
                size_part = f", {depot.manifest_size}" if depot.manifest_size else ""
                lines.append(f'setManifestid({depot.depot_id}, "{depot.manifest_id}"{size_part})')

    clean_dlcs: list[LuaDlc] = []
    seen_dlcs: set[str] = set()
    for raw in dlcs:
        if isinstance(raw, LuaDlc):
            dlc = raw
        elif isinstance(raw, dict):
            dlc = LuaDlc(
                app_id=str(raw.get("app_id") or raw.get("id") or ""),
                name=str(raw.get("name") or ""),
                token=str(raw.get("token") or ""),
            )
        else:
            dlc = LuaDlc(app_id=str(raw))
        if not dlc.app_id or not dlc.app_id.isdigit() or dlc.app_id == app_id_str or dlc.app_id in seen_depots:
            continue
        if dlc.app_id in seen_dlcs:
            continue
        seen_dlcs.add(dlc.app_id)
        clean_dlcs.append(dlc)

    if clean_dlcs:
        lines.extend(["", "-- DLCS WITHOUT DEDICATED DEPOTS"])
        for dlc in sorted(clean_dlcs, key=lambda d: int(d.app_id)):
            lines.append(_line_with_comment(f"addappid({dlc.app_id})", dlc.name))
            if dlc.token:
                token = str(dlc.token).replace('"', "")
                lines.append(f'addtoken({dlc.app_id}, "{token}")')

    return "\n".join(lines).rstrip() + "\n"
