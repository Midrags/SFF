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

"""API endpoints are in here"""

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from colorama import Fore, Style

from sff.http_utils import download_to_tempfile, get_request
from sff.prompts import prompt_confirm, prompt_secret
from sff.storage.settings import get_setting, set_setting
from sff.structs import Settings
from sff.zip import read_lua_from_zip

logger = logging.getLogger(__name__)


def get_oureverday(dest: Path, app_id: str):
    import json
    import httpx as _httpx
    from sff.steam_client import create_provider_for_current_thread

    # Step 1: The Original GitHub source (Primary)
    print(Fore.CYAN + f"\n[Step 1] Attempting to download Lua for {app_id} from SteamAutoCracks GitHub..." + Style.RESET_ALL)
    try:
        resp = _httpx.get(
            f"https://raw.githubusercontent.com/SteamAutoCracks/ManifestHub/refs/heads/{app_id}/{app_id}.lua",
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code == 200 and resp.text.strip():
            lua_path = dest / f"{app_id}.lua"
            lua_path.write_text(resp.text, encoding="utf-8")
            print(Fore.GREEN + f"✅ GitHub: Succesfully downloaded Lua for {app_id}" + Style.RESET_ALL)
            return lua_path
        else:
            print(Fore.YELLOW + f"GitHub returned HTTP {resp.status_code}. Moving to GitLab / Steam Client Fallback..." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.YELLOW + f"GitHub unreachable ({e}). Moving to GitLab / Steam Client Fallback..." + Style.RESET_ALL)

    # Sub-Step 2A: Query Steam Connection Manager natively for the depot IDs!
    print(Fore.CYAN + f"[Step 2] Native Fallback - Fetching valid depots for {app_id} natively from Steam Client..." + Style.RESET_ALL)
    try:
        provider = create_provider_for_current_thread()
        app_info = provider.get_single_app_info(int(app_id))
        if not app_info:
            print(Fore.RED + f"Failed to query Steam App Info for {app_id}." + Style.RESET_ALL)
            return None
        depots = [d for d in app_info.get("depots", {}).keys() if d.isdigit()]
    except Exception as e:
        print(Fore.RED + f"Steam query failed while checking depots: {e}" + Style.RESET_ALL)
        return None

    if not depots:
        print(Fore.RED + f"No valid depots exist on Steam for this App ID." + Style.RESET_ALL)
        return None

    # Step 2: The GitLab Database
    print(Fore.CYAN + f"[Step 3] Fetching latest Decryption Key database from GitLab..." + Style.RESET_ALL)
    keys_dict = {}
    try:
        resp = _httpx.get(
            "https://gitlab.com/SteamAutoCracks/ManifestHub/-/raw/main/depotkeys.json",
            timeout=25,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            keys_dict = resp.json()
            print(Fore.GREEN + f"✅ Successfully downloaded key database from GitLab!" + Style.RESET_ALL)
        else:
            print(Fore.YELLOW + f"GitLab returned HTTP {resp.status_code}. Moving to local file final resort..." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.YELLOW + f"GitLab repository unreachable ({e}). Moving to local file final resort..." + Style.RESET_ALL)

    # Step 3: "Last Complete Resort" Local Database
    if not keys_dict:
        print(Fore.CYAN + f"[Final Resort] Loading local keys from C:\\Users\\Syrer\\Downloads database backup..." + Style.RESET_ALL)
        local_db = Path(__file__).parent / "fallback_depotkeys.json"
        if local_db.exists():
            try:
                keys_dict = json.loads(local_db.read_text(encoding="utf-8"))
                print(Fore.GREEN + f"✅ Successfully loaded local key database!" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"Failed to load local DB: {e}" + Style.RESET_ALL)
                return None
        else:
            print(Fore.RED + f"Local DB '{local_db.name}' not found." + Style.RESET_ALL)
            return None

    # Generate the Lua File Dynamically
    lua_lines = [f"addappid({app_id})"]
    found = 0
    for d in depots:
        if d in keys_dict:
            # SteamAutoCrack uses addappid(depot_id, 1, "key") format
            lua_lines.append(f"addappid({d}, 1, \"{keys_dict[d]}\")")
            found += 1

    if found == 0:
        print(Fore.RED + f"No known keys were found for the depots of App ID {app_id} in any database." + Style.RESET_ALL)
        return None

    lua_path = dest / f"{app_id}.lua"
    with lua_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lua_lines))
    
    print(Fore.GREEN + f"✅ Built custom Lua for {app_id} (Resolved {found} keys natively)" + Style.RESET_ALL)
    return lua_path

    print(
        Fore.RED
        + f"\nFailed to download Lua for App ID {app_id} from oureveryday."
        + Style.RESET_ALL
    )
    print(
        Fore.YELLOW
        + "The game may not be available on this source, or there is a network error."
        + Style.RESET_ALL
    )
    return None



def get_hubcap(dest: Path, app_id: str, depotcache: Optional[Path] = None) -> Optional[Path]:
    url = f"https://hubcapmanifest.com/api/v1/manifest/{app_id}"

    # Loop to allow retry with new API key
    while True:
        if not (hubcap_key := get_setting(Settings.HUBCAP_KEY)):
            hubcap_key = prompt_secret(
                "Paste your Hubcap API key here: ",
                lambda x: x.startswith("smm"),
                "That's not a Hubcap API key!",
                long_instruction=(
                    "Go to the Hubcap Manifest website and request an API key. It's free."
                ),
            ).strip()
            set_setting(Settings.HUBCAP_KEY, hubcap_key)

        headers = {
            "Authorization": f"Bearer {hubcap_key}",
        }

        try:
            stats_resp = httpx.get(
                "https://hubcapmanifest.com/api/v1/user/stats",
                headers=headers,
                timeout=15,
                follow_redirects=True,
            )
        except httpx.ConnectError:
            print(
                Fore.RED
                + "\nNetwork error: Cannot reach Hubcap Manifest API."
                  " Check your internet connection."
                + Style.RESET_ALL
            )
            return None
        except httpx.RequestError as e:
            print(Fore.RED + f"\nNetwork error connecting to Hubcap Manifest: {e}" + Style.RESET_ALL)
            return None

        if stats_resp.status_code == 401:
            print(Fore.RED + "\nHubcap API key is invalid or expired." + Style.RESET_ALL)
            if prompt_confirm("Do you want to enter a new API key?"):
                set_setting(Settings.HUBCAP_KEY, "")
                continue
            else:
                print(Fore.YELLOW + "\nYou can update your API key in Settings later." + Style.RESET_ALL)
                return None
        elif stats_resp.status_code != 200:
            print(
                Fore.RED
                + f"\nHubcap Manifest API returned HTTP {stats_resp.status_code}."
                + Style.RESET_ALL
            )
            return None

        data = stats_resp.json()
        break
            
    usage = data.get("daily_usage")
    limit = data.get("daily_limit")
    state = data.get("can_make_requests")

    if not state:
        print(
            Fore.RED
            + f"Daily limit exceeded! You used {usage}/{limit}"
            + Style.RESET_ALL
        )
        return None
    else:
        logger.debug(f"Downloading lua files from {url}")
        lua_bytes = b''
        while True:
            with download_to_tempfile(url, headers) as tf:
                if tf is None:
                    if prompt_confirm("Try again?"):
                        continue
                    break

                data = tf.read()
                print(
                    Fore.GREEN
                    + f"Hubcap Daily Limit: {usage+1}/{limit}"
                    + Style.RESET_ALL
                )
                lua_bytes = read_lua_from_zip(io.BytesIO(data), decode=False, depotcache=depotcache)
                if lua_bytes is None:
                    # Try to decode server response for a useful error message
                    try:
                        decoded = data.decode("utf-8", errors="replace")
                    except Exception:
                        decoded = repr(data[:200])
                    try:
                        parsed = json.loads(decoded)
                        print(
                            Fore.RED
                            + json.dumps(parsed, indent=2)
                            + Style.RESET_ALL
                        )
                    except json.JSONDecodeError:
                        print(
                            "Did not receive a ZIP file or JSON:\n"
                            + decoded[:500]
                        )
            break

        lua_path = dest / f"{app_id}.lua"
        if lua_bytes:
            with lua_path.open("wb") as f:
                f.write(lua_bytes)
            return lua_path
        return None

