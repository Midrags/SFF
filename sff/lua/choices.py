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

import re

from datetime import datetime

from pathlib import Path


from colorama import Fore, Style


from sff.fzf import run_fzf

from sff.http_utils import download_to_tempfile

from sff.lua.endpoints import get_hubcap, get_oureverday

from sff.prompts import prompt_confirm, prompt_file, prompt_select, prompt_text

from sff.storage.settings import get_setting, set_setting

from sff.strings import STEAM_WEB_API_KEY

from sff.structs import (

    LuaChoice,

    LuaChoiceReturnCode,

    LuaEndpoint,

    LuaResult,

    NamedIDs,

    OSType,

    Settings,

)

from sff.utils import enter_path, root_folder

from sff.zip import read_lua_from_zip


def select_from_saved_luas(saved_lua, named_ids):

    if len(named_ids) == 0:

        print("You don't have any saved .lua files. Try adding some first.")
        return LuaResult(None, None, LuaChoice.ADD_LUA)

    lua_path = prompt_select(

        "Choose a game:",
        [(name, saved_lua / f"{app_id}.lua") for app_id, name in named_ids.items()],
        fuzzy=True,
        max_height=10,
        cancellable=True

    )

    if lua_path is None or not lua_path.exists():

        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)

    return LuaResult(lua_path, None, LuaChoiceReturnCode.LOOP)


def add_new_lua(file = None):

    lua_path = file if file else prompt_file(

        "Drag a .lua file (or .zip w/ .lua inside) into here "
        "then press Enter.\n"
        "Leave it blank to go back:",
        allow_blank=True,

    )

    if lua_path.samefile(Path.cwd()):  # Blank input

        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)

    if lua_path.suffix == ".zip":

        lua_contents = read_lua_from_zip(lua_path)
        if lua_contents is None:
            print("Could not find .lua in ZIP file.")
            return LuaResult(None, None, LuaChoiceReturnCode.LOOP)
        return LuaResult(lua_path, lua_contents, LuaChoiceReturnCode.LOOP)

    return LuaResult(lua_path, None, LuaChoiceReturnCode.LOOP)


def search_game(os_type):

    all_games_file = (root_folder(outside_internal=True) / "all_games.txt")

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
        params = {"key": api_key, "max_results": "50000"}
        games = []
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


def download_lua(dest, os_type):

    reg = re.compile(r"(?<=store\.steampowered\.com\/app\/)\d+|\d+")

    def validate_app_id(x):

        return bool(reg.search(x)) or x == ''

    def filter_app_id(x):

        if x == "":
            return x
        match = reg.search(x)
        assert match is not None
        return match.group()

    source = prompt_select(

        "Select an endpoint:", list(LuaEndpoint), cancellable=True

    )

    if source is None:

        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)

    app_id = prompt_text(

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

    elif source == LuaEndpoint.HUBCAP:

        # Pass depotcache so manifests from the ZIP land in Steam immediately
        steam_root = get_setting(Settings.STEAM_PATH)
        depotcache = (Path(steam_root) / "depotcache") if steam_root else None
        lua_path = get_hubcap(dest, app_id, depotcache=depotcache)

    if lua_path is None:

        return LuaResult(None, None, LuaChoiceReturnCode.GO_BACK)

    return LuaResult(lua_path, None, LuaChoiceReturnCode.LOOP, endpoint=source)


def download_lua_direct(dest, app_id, source, steam_path=None):
    """Download Lua for a known app_id from a known source endpoint, no CLI prompts.

    Used by the Store tab when the user has already selected the app and source
    through the GUI. Returns the saved lua Path on success, or None on failure.
    """
    from sff.structs import LuaEndpoint
    app_id = str(app_id)
    if source == LuaEndpoint.OUREVERYDAY:
        return get_oureverday(dest, app_id)
    elif source == LuaEndpoint.HUBCAP:
        depotcache = (Path(steam_path) / "depotcache") if steam_path else None
        return get_hubcap(dest, app_id, depotcache=depotcache)
    return None
