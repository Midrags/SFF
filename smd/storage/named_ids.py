import json
from pathlib import Path

from smd.http_utils import get_game_name
from smd.structs import NamedIDs


def _load_named_ids(file: Path) -> NamedIDs:
    if not file.exists():
        return NamedIDs({})
    with file.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_named_ids(file: Path, data: NamedIDs):
    with file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_named_ids(folder: Path) -> NamedIDs:
    """Gets names of games from lua files.
    Try to read saved names first, then request names of newer files.
    If there are untracked files, update `names.json` accordingly

    Args:
        folder (Path): Folder with .lua files in it

    Returns:
        dict: a dict in the format (game_id, game_name)
    """
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
