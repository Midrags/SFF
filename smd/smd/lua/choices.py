import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from colorama import Fore, Style

from smd.fzf import run_fzf
from smd.http_utils import download_to_tempfile
from smd.lua.endpoints import get_morrenus, get_oureverday
from smd.prompts import prompt_confirm, prompt_file, prompt_select, prompt_text
from smd.storage.settings import get_setting, set_setting
from smd.strings import STEAM_WEB_API_KEY
from smd.structs import (
    LuaChoice,
    LuaChoiceReturnCode,
    LuaEndpoint,
    LuaResult,
    NamedIDs,
    OSType,
    Settings,
)
from smd.utils import enter_path, root_folder
from smd.zip import read_lua_from_zip


def select_from_saved_luas(saved_lua: Path, named_ids: NamedIDs) -> LuaResult:
    """Prompt the user to select a saved lua file

    Args:
        saved_lua (Path): Path to the folder with saved lua files
        named_ids (dict[str, str]): A dict of (game_id, game_name)

    Returns:
        LuaResult:
    """
    if len(named_ids) == 0:
        print("You don't have any saved .lua files. Try adding some first.")
        return LuaResult(None, None, LuaChoice.ADD_LUA)
    lua_path: Optional[Path] = prompt_select(
        "Choose a game:",
        [(name, saved_lua / f"{app_id}.lua") for app_id, name in named_ids.items()],
        fuzzy=True,
        max_height=10,
        cancellable=True
    )
    if lua_path is None or not lua_path.exists():
        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)
    return LuaResult(lua_path, None, LuaChoiceReturnCode.LOOP)


def add_new_lua(file: Optional[Path] = None) -> LuaResult:
    """Prompts user to add a new .lua or ZIP file

    Returns:
        LuaResult:
    """
    lua_path = file if file else prompt_file(
        "Drag a .lua file (or .zip w/ .lua inside) into here "
        "then press Enter.\n"
        "Leave it blank to go back:",
        allow_blank=True,
    )

    if lua_path.samefile(Path.cwd()):  # Blank input
        # Switch to other option
        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)

    if lua_path.suffix == ".zip":
        lua_contents = read_lua_from_zip(lua_path)
        if lua_contents is None:
            print("Could not find .lua in ZIP file.")
            return LuaResult(None, None, LuaChoiceReturnCode.LOOP)
        return LuaResult(lua_path, lua_contents, LuaChoiceReturnCode.LOOP)
    return LuaResult(lua_path, None, LuaChoiceReturnCode.LOOP)


def search_game(os_type: OSType) -> Optional[str]:
    """Using fzf, lets a user search for a game, then returns game ID"""
    all_games_file = (root_folder() / "all_games.txt")
    if all_games_file.exists():
        mtime = all_games_file.stat().st_mtime
        mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %I:%M %p")
        download = prompt_confirm(
            "Do you want to update the list of every Game ID? "
            f"(Last Modified: {mtime_str})",
            default=False,
        )
    else:
        download = True
    if download:
        if (api_key := get_setting(Settings.STEAM_WEB_API_KEY)) is None:
            print("You don't have a Steam Web API Key yet. "
                  "Steam needs this in order to browse through all the games.\n\n"
                  "No worries though. I'll just give you one (It's not mine) "
                  "You can change this later with your own in settings if you'd like.")
            api_key = STEAM_WEB_API_KEY
            set_setting(Settings.STEAM_WEB_API_KEY, api_key)
        params: dict[str, str] = {"key": api_key, "max_results": "50000"}
        games: list[dict[str, Any]] = []
        print("Steam has limited this endpoint to 50k IDs per requests, so "
              "it'll be downloading a couple times. Don't be alarmed.")
        while True:
            with download_to_tempfile(
                "https://api.steampowered.com/IStoreService/GetAppList/v1/",
                params=params
            ) as tf:
                if tf is None:
                    continue
                resp = json.load(tf)
            games.extend(enter_path(resp, "response", "apps"))
            more = enter_path(resp, "response", "have_more_results")
            if not more:
                break
            params['last_appid'] = enter_path(resp, "response", "last_appid")
        games_str = [
            x.get("name", "UNKNOWN GAME") + f" [ID={x.get('appid')}]" for x in games
        ]
        with all_games_file.open("w", encoding="utf=-8") as f:
            f.write('\n'.join(games_str))
    else:
        games_str = all_games_file
    selection = run_fzf(games_str, os_type)
    if selection:
        match = re.search(r"(?<=\[ID=)\d+(?=\]$)", selection)
        assert match is not None
        res = match.group()
        print(f"{Fore.YELLOW + selection + Style.RESET_ALL} has been selected")
        return res


def download_lua(dest: Path, os_type: OSType) -> LuaResult:
    """Downloads a lua file from the available endpoints"""

    reg = re.compile(r"(?<=store\.steampowered\.com\/app\/)\d+|\d+")

    def validate_app_id(x: str) -> bool:
        return bool(reg.search(x)) or x == ''

    def filter_app_id(x: str) -> str:
        if x == "":
            return x
        match = reg.search(x)
        assert match is not None  # lmao
        return match.group()

    source: Optional[LuaEndpoint] = prompt_select(
        "Select an endpoint:", list(LuaEndpoint), cancellable=True
    )
    if source is None:
        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)

    app_id: str = prompt_text(
        "Enter the App ID or Store link. Leave it blank to search for games:",
        validator=validate_app_id,
        invalid_msg="Not a valid format.",
        filter=filter_app_id,
    )

    if not app_id:
        if x := search_game(os_type):
            app_id = x
        else:
            return LuaResult(None, None, LuaChoiceReturnCode.LOOP)

    if source == LuaEndpoint.OUREVERYDAY:
        lua_path = get_oureverday(dest, app_id)
    elif source == LuaEndpoint.MORRENUS:
        lua_path = get_morrenus(dest, app_id)

    if lua_path is None:
        return LuaResult(None, None, LuaChoiceReturnCode.LOOP)

    return LuaResult(lua_path, None, LuaChoiceReturnCode.LOOP)
