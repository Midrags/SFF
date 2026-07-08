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

import html
import re
from pathlib import Path


_DEPOT_PAIR_RE = re.compile(
    r"/depot/(?P<depot>\d+)/history/\?changeid=M:(?P<manifest>\d+)",
    re.IGNORECASE,
)
_DEPOT_RE_LIST = (
    re.compile(r"\bdata-depotid=[\"'](?P<depot>\d+)[\"']", re.IGNORECASE),
    re.compile(r"/depot/(?P<depot>\d+)(?:/|[\"'#?])", re.IGNORECASE),
    re.compile(r"\bDepot\s+(?P<depot>\d+)\b", re.IGNORECASE),
)
_MANIFEST_RE_LIST = (
    re.compile(r"\bchangeid=M:(?P<manifest>\d+)\b", re.IGNORECASE),
    re.compile(r"\bManifestID\b(?P<trail>.{0,1200})", re.IGNORECASE | re.DOTALL),
)
_BIG_NUMBER_RE = re.compile(r"\b\d{9,20}\b")
_TR_RE = re.compile(r"<tr\b(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
_BRANCH_RE = re.compile(r"\bdata-branch=[\"'](?P<branch>[^\"']+)[\"']", re.IGNORECASE)
_DATE_CELL_RE = re.compile(r"<td\b[^>]*class=[\"'][^\"']*text-right[^\"']*[\"'][^>]*>(?P<date>.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_depot_manifest_html(raw_html: str) -> list[dict[str, str]]:
    text = html.unescape(raw_html or "")
    if not text.strip():
        raise ValueError("HTML file is empty")

    paired = _rows_from_manifest_table(text)
    if paired:
        return paired

    paired = _pairs_from_history_links(text)
    if paired:
        return paired

    depot_id = _first_depot_id(text)
    if not depot_id:
        raise ValueError("No depot ID found in the HTML")

    manifest_id = _first_manifest_id(text, depot_id)
    if not manifest_id:
        raise ValueError("No manifest ID found in the HTML")

    return [{"depot_id": depot_id, "manifest_id": manifest_id}]


def parse_depot_manifest_html_file(path: Path) -> list[dict[str, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return parse_depot_manifest_html(raw)


def parse_depot_manifest_html_files(paths: list[Path]) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        try:
            parsed = parse_depot_manifest_html_file(path)
        except ValueError:
            continue
        entries = []
        for entry in parsed:
            depot_id = entry.get("depot_id", "")
            manifest_id = entry.get("manifest_id", "")
            seen_key = f"{depot_id}:{manifest_id}"
            if not depot_id or not manifest_id or seen_key in seen:
                continue
            seen.add(seen_key)
            entries.append(entry)
        if entries:
            depots = {entry["depot_id"] for entry in entries}
            group = {
                "label": path.name,
                "date": "Imported",
                "branch": "manual",
                "source": "Imported HTML",
                "entries": entries,
            }
            if len(depots) == 1 and len(entries) > 1:
                group["single_depot_choices"] = True
            groups.append(group)
    return groups


def flatten_manifest_groups(groups: list[dict[str, object]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for group in groups:
        for entry in group.get("entries", []):
            if isinstance(entry, dict):
                depot_id = str(entry.get("depot_id", ""))
                manifest_id = str(entry.get("manifest_id", ""))
                if depot_id and manifest_id:
                    entries.append({"depot_id": depot_id, "manifest_id": manifest_id})
    return entries


def format_manifest_entries(entries: list[dict[str, str]]) -> str:
    return "\n".join(
        f"{entry['depot_id']}={entry['manifest_id']}"
        for entry in entries
        if entry.get("depot_id") and entry.get("manifest_id")
    )


def _pairs_from_history_links(text: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for match in _DEPOT_PAIR_RE.finditer(text):
        depot_id = match.group("depot")
        manifest_id = match.group("manifest")
        seen_key = f"{depot_id}:{manifest_id}"
        if not depot_id.isdigit() or not manifest_id.isdigit():
            continue
        if seen_key in seen:
            continue
        seen.add(seen_key)
        entries.append({"depot_id": depot_id, "manifest_id": manifest_id})
    return entries


def _rows_from_manifest_table(text: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for row in _TR_RE.finditer(text):
        body = row.group("body")
        pair = _DEPOT_PAIR_RE.search(body)
        if not pair:
            continue
        depot_id = pair.group("depot")
        manifest_id = pair.group("manifest")
        seen_key = f"{depot_id}:{manifest_id}"
        if seen_key in seen:
            continue
        seen.add(seen_key)
        entry = {"depot_id": depot_id, "manifest_id": manifest_id}
        branch = _BRANCH_RE.search(row.group("attrs"))
        if branch:
            entry["branch"] = branch.group("branch")
        date = _DATE_CELL_RE.search(body)
        if date:
            entry["date"] = _clean_cell_text(date.group("date"))
        entries.append(entry)
    return entries


def _clean_cell_text(value: str) -> str:
    cleaned = _TAG_RE.sub("", html.unescape(value or ""))
    return " ".join(cleaned.split())


def _first_depot_id(text: str) -> str | None:
    for pattern in _DEPOT_RE_LIST:
        match = pattern.search(text)
        if match:
            return match.group("depot")
    return None


def _first_manifest_id(text: str, depot_id: str) -> str | None:
    for pattern in _MANIFEST_RE_LIST:
        match = pattern.search(text)
        if not match:
            continue
        if "manifest" in match.groupdict():
            manifest_id = match.group("manifest")
            if manifest_id != depot_id:
                return manifest_id
            continue
        trail = match.groupdict().get("trail", "")
        for candidate in _BIG_NUMBER_RE.findall(trail):
            if candidate != depot_id:
                return candidate

    marker = re.search(r"Previously seen manifests|id=[\"']manifests[\"']", text, re.IGNORECASE)
    section = text[marker.start():] if marker else text
    for candidate in _BIG_NUMBER_RE.findall(section):
        if candidate != depot_id:
            return candidate
    return None
