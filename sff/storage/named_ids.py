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

import json
from pathlib import Path

from sff.http_utils import get_game_name
from sff.structs import NamedIDs


def _load_named_ids(file: Path) -> NamedIDs:
    if not file.exists():
        return NamedIDs({})
    with file.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_named_ids(file: Path, data: NamedIDs):
    with file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_named_ids(folder: Path) -> NamedIDs:
    if not folder.exists():
        folder.mkdir()
        return NamedIDs({})

    id_names_file = folder / "names.json"
    named_ids: NamedIDs = _load_named_ids(id_names_file)

    new_ids = False
    saved_ids = [x.stem for x in folder.glob("*.lua")]
    for saved_id in saved_ids:
        if saved_id not in named_ids:
            new_ids = True
            named_ids[saved_id] = get_game_name(saved_id)

    if new_ids:
        _save_named_ids(id_names_file, named_ids)
    return named_ids
