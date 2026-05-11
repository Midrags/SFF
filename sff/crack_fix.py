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

import shutil
import tempfile
from pathlib import Path

import httpx
from colorama import Fore, Style

from sff.hv_fix import (
    _download_buzzheavier,
    _extract_file_id_from_url,
    _extract_to_game_folder,
)
from sff.prompts import prompt_select

CRACK_JSON_URL = "https://raw.githubusercontent.com/KoriaPolis/CrakFiles/main/crackfiles.json"


def fetch_crack_games() -> list[dict]:
    """Fetch the crackfiles.json list from GitHub. Returns a list of game dicts."""
    try:
        print(Fore.CYAN + "Fetching fixes list from GitHub..." + Style.RESET_ALL)
        resp = httpx.get(CRACK_JSON_URL, follow_redirects=True, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(Fore.RED + f"Error fetching fixes list: {e}" + Style.RESET_ALL)
        return []


def search_crack_games(query: str, all_games: list[dict]) -> list[dict]:
    """Search for a game by name. Exact matches first, then contains matches."""
    q = query.lower().strip()
    exact = [g for g in all_games if g.get("name", "").lower() == q]
    contains = [
        g for g in all_games
        if q in g.get("name", "").lower() and g not in exact
    ]
    return exact + contains


def _badge_summary(game: dict) -> str:
    badges = set(
        b
        for f in game.get("fixes", [])
        for b in f.get("badges", [])
    )
    return ", ".join(sorted(badges)) if badges else ""


def apply_crack_fix(game_name: str, game_folder) -> bool:
    """Fetch list, let user pick, download from buzzheavier, extract into game folder."""
    game_folder = Path(game_folder)

    all_games = fetch_crack_games()
    if not all_games:
        return False

    matches = search_crack_games(game_name, all_games)

    def _fmt(g: dict) -> str:
        summary = _badge_summary(g)
        return f"{g['name']}  [{summary}]" if summary else g["name"]

    if not matches:
        print(Fore.YELLOW + f"No match for '{game_name}'. Select manually." + Style.RESET_ALL)
        options = [(_fmt(g), g) for g in sorted(all_games, key=lambda x: x.get("name", ""))]
    else:
        print(Fore.GREEN + f"Found {len(matches)} match(es)." + Style.RESET_ALL)
        matched_set = set(id(g) for g in matches)
        options = [(_fmt(g), g) for g in matches]
        options += [
            (_fmt(g), g)
            for g in sorted(all_games, key=lambda x: x.get("name", ""))
            if id(g) not in matched_set
        ]

    chosen_game = prompt_select(
        "Select fix to download:",
        options,
        fuzzy=True,
        max_height=15,
        cancellable=True,
    )
    if chosen_game is None:
        return False

    fixes = chosen_game.get("fixes", [])
    if not fixes:
        print(Fore.RED + "No download links for this game." + Style.RESET_ALL)
        return False

    if len(fixes) == 1:
        chosen_fix = fixes[0]
    else:
        fix_options = [
            (
                f"{f.get('filename', f.get('href', ''))}  {' '.join(f.get('badges', []))}",
                f,
            )
            for f in fixes
        ]
        chosen_fix = prompt_select("Select download source:", fix_options, cancellable=True)
        if chosen_fix is None:
            return False

    href = chosen_fix.get("href", "")
    if not href:
        print(Fore.RED + "No download URL." + Style.RESET_ALL)
        return False

    host_type, file_id = _extract_file_id_from_url(href)

    temp_dir = Path(tempfile.mkdtemp(prefix="sff_crack_fix_"))
    try:
        if host_type == "buzzheavier":
            archive_path = _download_buzzheavier(file_id, temp_dir)
            if archive_path is None:
                return False
        else:
            print(Fore.YELLOW + f"Unknown host '{host_type}'. Cannot auto-download." + Style.RESET_ALL)
            return False

        if not archive_path.exists() or archive_path.stat().st_size == 0:
            print(Fore.RED + "Downloaded file is empty or missing." + Style.RESET_ALL)
            return False

        print(
            Fore.GREEN
            + f"Downloaded: {archive_path.name} ({archive_path.stat().st_size // 1024} KB)"
            + Style.RESET_ALL
        )

        if not _extract_to_game_folder(archive_path, game_folder, game_name):
            return False

        print()
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(Fore.GREEN + "  FIX APPLIED!" + Style.RESET_ALL)
        print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
        print(f"Game:   {game_name}")
        print(f"Folder: {game_folder}")
        print()
        return True

    except Exception as e:
        print(Fore.RED + f"Error applying fix: {e}" + Style.RESET_ALL)
        return False
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
