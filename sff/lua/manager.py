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

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from colorama import Fore, Style

from sff.lua.choices import add_new_lua, download_lua, select_from_saved_luas
from sff.prompts import prompt_select
from sff.storage.named_ids import get_named_ids
from sff.structs import (
    DepotKeyPair,
    LuaChoice,
    LuaChoiceReturnCode,
    LuaEndpoint,
    LuaParsedInfo,
    OSType,
    RawLua,
)

logger = logging.getLogger(__name__)

# Compiled regexes for Lua parsing (reused across calls)
_DEPOT_NO_KEY_REGEX = re.compile(
    r"^\s*addappid\s*\(\s*(\d+)\s*\)", flags=re.MULTILINE
)
_DEPOT_DEC_KEY_REGEX = re.compile(
    r"^\s*addappid\s*\(\s*(\d+)\s*,\s*\d\s*,\s*(?:\"|\')(\S+)(?:\"|\')\s*\)",
    flags=re.MULTILINE,
)
_GENERAL_ADDAPPID_REGEX = re.compile(r"^\s*addappid\s*\(\s*(\d+)", flags=re.MULTILINE)
_SETMANIFESTID_REGEX = re.compile(
    r"^\s*setManifestid\s*\(\s*(\d+)\s*,\s*[\"'](\d+)[\"']\s*(?:,\s*\d+\s*)?\)",
    flags=re.MULTILINE,
)
_SETMANIFESTID_LINE_REGEX = re.compile(
    r"^(\s*)setManifestid\s*\(\s*(\d+)\s*,\s*[\"']\d+[\"']\s*(?:,\s*\d+\s*)?\)\s*$",
    flags=re.IGNORECASE,
)
_COMMENTED_SETMANIFESTID_REGEX = re.compile(
    r"^\s*--\s*setManifestid\s*\(",
    flags=re.IGNORECASE,
)
_KEYED_ADDAPPID_LINE_REGEX = re.compile(
    r"addappid\s*\(\s*(\d+)\s*,\s*\d\s*,\s*(?:\"|\')\S+(?:\"|\')\s*\)",
    flags=re.IGNORECASE,
)
_ADDTOKEN_REGEX = re.compile(
    r"^\s*addtoken\s*\(\s*(\d+)\s*,\s*[\"']([^\"']+)[\"']\s*\)",
    flags=re.MULTILINE,
)


def parse_lua_contents(contents, path):
    """
    Parse Lua contents into LuaParsedInfo without prompts.
    Returns None if parsing fails (no app ID or no decryption keys).
    """
    if not (any_addappid := _GENERAL_ADDAPPID_REGEX.search(contents)):
        return None
    app_id = any_addappid.group(1)
    ids_with_no_key = _DEPOT_NO_KEY_REGEX.findall(contents)
    depot_dec_key = _DEPOT_DEC_KEY_REGEX.findall(contents)
    if not depot_dec_key:
        return None
    depot_pairs = [DepotKeyPair(*x) for x in depot_dec_key]
    depot_pairs.extend([DepotKeyPair(x, "") for x in ids_with_no_key])
    manifest_overrides = dict(_SETMANIFESTID_REGEX.findall(contents))
    token_overrides = dict(_ADDTOKEN_REGEX.findall(contents))
    return LuaParsedInfo(path, contents, app_id, depot_pairs, manifest_overrides, token_overrides)


def write_manifest_pins_to_lua(path: Path, manifest_map: dict) -> int:
    pins = {
        str(depot): str(gid)
        for depot, gid in (manifest_map or {}).items()
        if str(depot).isdigit() and str(gid).isdigit()
    }
    if not pins:
        return 0

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # First pass: know which depots already have a real setManifestid line anywhere.
    # This prevents inserting a new line after addappid when the existing line appears below it.
    existing_pin_depots: set[str] = set()
    for line in lines:
        if _COMMENTED_SETMANIFESTID_REGEX.match(line):
            continue

        manifest_line = _SETMANIFESTID_LINE_REGEX.match(line)
        if manifest_line:
            existing_pin_depots.add(manifest_line.group(2))

    rewritten: list[str] = []
    written: set[str] = set()

    for line in lines:
        # Drop old commented-out pins completely, same behavior as before.
        if _COMMENTED_SETMANIFESTID_REGEX.match(line):
            continue

        manifest_line = _SETMANIFESTID_LINE_REGEX.match(line)
        if manifest_line:
            indent, depot_id = manifest_line.groups()

            if depot_id in pins:
                # Rewrite only the first active setManifestid for this depot.
                # Any later duplicates are skipped.
                if depot_id in written:
                    continue

                rewritten.append(f'{indent}setManifestid({depot_id}, "{pins[depot_id]}")')
                written.add(depot_id)
            else:
                rewritten.append(line)

            continue

        rewritten.append(line)

        addappid = _KEYED_ADDAPPID_LINE_REGEX.search(line)
        if addappid:
            depot_id = addappid.group(1)

            # Only insert after addappid when the lua has no active setManifestid
            # for this depot anywhere in the file.
            if (
                depot_id in pins
                and depot_id not in existing_pin_depots
                and depot_id not in written
            ):
                rewritten.append(f'setManifestid({depot_id}, "{pins[depot_id]}")')
                written.add(depot_id)

    # If a selected depot was not next to an addappid line, append it at the end.
    for depot_id in sorted(set(pins) - written, key=int):
        rewritten.append(f'setManifestid({depot_id}, "{pins[depot_id]}")')
        written.add(depot_id)

    new_text = "\n".join(rewritten).rstrip() + "\n"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")

    return len(written)


def remove_depots_from_lua(path: Path, depot_ids: set[str]) -> int:
    """Remove addappid and setManifestid lines for given depot IDs from a lua file.

    Returns the number of lines removed."""
    if not depot_ids or not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    _depot_re = re.compile(
        r"^\s*(?:set[Mm]anifestid|addappid)\s*\(\s*(\d+)\b"
    )
    kept = []
    removed = 0
    for line in lines:
        m = _depot_re.search(line)
        if m and m.group(1) in depot_ids:
            removed += 1
            continue
        kept.append(line)
    if removed:
        path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    return removed


class LuaManager:
    def __init__(
        self, os_type: OSType
    ):
        """Might need refactor. Does I/O on init"""
        self.saved_lua = Path().cwd() / "saved_lua"
        self.named_ids = get_named_ids(self.saved_lua)
        self.os_type = os_type
        self.last_endpoint: Optional[LuaEndpoint] = None

    def get_raw_lua(
        self, choice: LuaChoice, override: Optional[Path] = None
    ):
        while True:
            if choice == LuaChoice.SELECT_SAVED_LUA:
                result = select_from_saved_luas(self.saved_lua, self.named_ids)
            elif choice == LuaChoice.ADD_LUA:
                result = add_new_lua(override)
            elif choice == LuaChoice.AUTO_DOWNLOAD:
                result = download_lua(self.saved_lua, self.os_type)
                if result.endpoint is not None:
                    self.last_endpoint = result.endpoint
            switch = result.switch_choice
            if isinstance(switch, LuaChoice):
                choice = switch
            elif switch == LuaChoiceReturnCode.GO_BACK:
                return None
            if result.path is not None:
                lua_path = result.path
                if result.contents is not None:  # Usually a zip
                    lua_contents = result.contents
                else:
                    try:
                        lua_contents = result.path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        print(
                            Fore.RED + "This file is not a text file!" + Style.RESET_ALL
                        )
                        override = None
                        continue
                break
        return RawLua(lua_path, lua_contents)

    def fetch_lua(
        self,
        override_choice = None,
        override_path = None,
    ):
        while True:
            choice = (
                override_choice
                if override_choice
                else prompt_select("Choose:", list(LuaChoice), cancellable=True)
            )
            if choice is None:
                return None
            lua = self.get_raw_lua(choice, override_path)
            if lua is None:
                continue
            parsed = parse_lua_contents(lua.contents, lua.path)
            if parsed is None:
                if not _GENERAL_ADDAPPID_REGEX.search(lua.contents):
                    print("App ID not found. Try again.")
                else:
                    print("Decryption keys not found. Try again.")
                continue
            print(f"App ID is {parsed.app_id}")
            return parsed

    def backup_lua(self, lua):
        target = self.saved_lua / f"{lua.app_id}.lua"
        if lua.path.suffix == ".zip":
            with target.open("w", encoding="utf-8") as f:
                f.write(lua.contents)
        else:
            try:
                shutil.copyfile(lua.path, target)
            except shutil.SameFileError:
                logger.debug("Skipped backup because it's the same file")
                pass
