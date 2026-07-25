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
import re
from pathlib import Path

import httpx

from colorama import Fore, Style

from sff.http_utils import download_to_tempfile, get_request
from sff.lua.generator import LuaDlc, render_grouped_lua
from sff.lua.provider import download_provider_update, load_provider, update_cache_from_lua_bytes
from sff.prompts import prompt_confirm, prompt_secret
from sff.storage.settings import get_setting, set_setting
from sff.structs import Settings
from sff.zip import read_lua_from_zip

logger = logging.getLogger(__name__)

_PROVIDER_CACHE: dict | None = None


def _cached_provider():
    global _PROVIDER_CACHE
    if _PROVIDER_CACHE is None:
        _PROVIDER_CACHE = load_provider()
    return _PROVIDER_CACHE


_REVO_PATTERN = re.compile(
    r'addappid\(\s*(\d+)\s*,\s*[01]\s*,\s*["\']([0-9a-fA-F]{64})["\']\s*\)'
)


def _update_fallback_depotkeys(lua_bytes):
    try:
        update_cache_from_lua_bytes(lua_bytes)
    except Exception:
        pass


def _provider_key_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for depot_id, entry in _cached_provider().items():
        if isinstance(entry, dict):
            key = str(entry.get("key") or "")
        else:
            key = str(entry or "")
        if key:
            out[str(depot_id)] = key
    return out


def _count_provider_matches(depots: list[str], keys_dict: dict[str, str]) -> int:
    return sum(1 for d in depots if keys_dict.get(d))


def _build_lua_from_provider(app_id: str, app_name: str, depots: list[str], keys_dict: dict[str, str], dlc_app_ids: list[str], manifest_map: dict[str, str] | None = None, manifest_sizes: dict[str, int] | None = None) -> str:
    provider = _cached_provider()
    depot_entries = []
    for depot_id in depots:
        key = keys_dict.get(depot_id)
        if not key:
            continue
        meta = provider.get(depot_id) or {}
        if isinstance(meta, str):
            meta = {}
        depot_entries.append({
            "id": depot_id,
            "key": key,
            "name": meta.get("name") or f"Depot {depot_id}",
            "parent_appid": meta.get("parent_appid") or str(app_id),
            "parent_name": meta.get("parent_name") or app_name,
            "manifest_id": (manifest_map or {}).get(depot_id, ""),
            "manifest_size": (manifest_sizes or {}).get(depot_id, 0),
        })
    dlcs = [LuaDlc(str(dlc_id)) for dlc_id in dlc_app_ids]
    return render_grouped_lua(app_id, app_name, depot_entries, manifest_map or {}, dlcs)


def get_oureverday(dest, app_id):
    import json
    import httpx as _httpx
    from sff.steam_client import create_provider_for_current_thread

    if not app_id or not str(app_id).strip().isdigit():
        print(Fore.RED + f"Invalid App ID: '{app_id}'" + Style.RESET_ALL)
        return None

    # Try cached Lua first — avoids re-fetching Steam CM and provider
    # keys on every download. The caller (download_lua_direct) targets
    # <cwd>/saved_lua/, and _run_windows_fastest copies the result back
    # there, so a subsequent download of the same app_id hits the cache.
    lua_path = Path(dest) / f"{app_id}.lua"
    if lua_path.exists() and lua_path.stat().st_size > 0:
        print(Fore.GREEN + f"[Cached] Using existing Lua for {app_id}" + Style.RESET_ALL)
        return lua_path

    # Step 1: Steam native query for depot IDs
    print(Fore.CYAN + f"[Step 1] Fetching depot list for {app_id} from Steam client..." + Style.RESET_ALL)
    try:
        # Build the SteamClient INSIDE the executor task. SteamClient binds
        # gevent's hub to whichever OS thread constructed it, so if we make
        # the client out here and then submit() get_single_app_info, the
        # executor thread has no hub for that client and gevent fires
        # "This operation would block forever". Building it inside keeps
        # the client + the hub on the same thread.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FT
        def _fetch_app_info():
            from sff.steam_client import create_provider_for_current_thread as _mk
            _provider = _mk()
            return _provider.get_single_app_info(int(app_id))
        with ThreadPoolExecutor(max_workers=1) as _ex:
            _fut = _ex.submit(_fetch_app_info)
            try:
                app_info = _fut.result(timeout=30)
            except _FT:
                print(Fore.RED + f"Steam app-info timed out for {app_id} (CM probably down)." + Style.RESET_ALL)
                return None
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

    # Pull latest manifest GIDs from Steam app info so we can write
    # setManifestid lines into the generated Lua.
    manifest_map: dict[str, str] = {}
    manifest_sizes: dict[str, int] = {}
    for depot_id in depots:
        depot_info = app_info.get("depots", {}).get(depot_id, {})
        manifests = depot_info.get("manifests", {})
        public = manifests.get("public", {}) if isinstance(manifests, dict) else {}
        gid = str(public.get("gid", ""))
        if gid and gid.isdigit():
            manifest_map[depot_id] = gid
            size = public.get("size")
            if isinstance(size, (int, str)) and str(size).isdigit():
                manifest_sizes[depot_id] = int(size)

    # Pull every DLC app id Steam reports for this game from extended.listofdlc.
    # These are DLCs with no depot of their own (cosmetic, soundtrack, in-game
    # currency, etc) — the keyed addappid(depot, 1, "key") lines won't cover
    # them because they have no depot_id. Adding plain addappid(<dlc_id>) lines
    # tells LumaCore to mark them as owned without any depot data.
    dlc_app_ids: list[str] = []
    try:
        listofdlc = (
            app_info.get("extended", {}).get("listofdlc", "")
            if isinstance(app_info.get("extended"), dict) else ""
        )
        if isinstance(listofdlc, str) and listofdlc.strip():
            dlc_app_ids = [
                x.strip()
                for x in listofdlc.split(",")
                if x.strip().isdigit()
            ]
    except Exception:
        dlc_app_ids = []

    # Step 2: Bundled local key database
    print(Fore.CYAN + f"[Step 2] Loading bundled key database..." + Style.RESET_ALL)
    keys_dict = _provider_key_map()
    if keys_dict:
        print(Fore.GREEN + f"[OK] Loaded provider key database ({len(keys_dict):,} keyed entries)." + Style.RESET_ALL)
    else:
        print(Fore.YELLOW + f"Provider key database not found or contains no keys." + Style.RESET_ALL)

    # Generate the Lua File Dynamically
    found = _count_provider_matches(depots, keys_dict)

    if found < len(depots):
        missing = len(depots) - found
        print(
            Fore.YELLOW
            + f"Provider is missing {missing} depot key(s). Refreshing provider once..."
            + Style.RESET_ALL
        )
        try:
            update_result = download_provider_update(timeout=20.0)
            if update_result.get("ok"):
                global _PROVIDER_CACHE
                _PROVIDER_CACHE = None
                print(
                    Fore.GREEN
                    + f"[OK] Provider refreshed from {update_result.get('url', '')} "
                      f"({update_result.get('count', 0):,} entries)."
                    + Style.RESET_ALL
                )
                keys_dict = _provider_key_map()
                found = _count_provider_matches(depots, keys_dict)
            else:
                print(
                    Fore.YELLOW
                    + "Provider refresh did not complete: "
                    + "; ".join(update_result.get("errors") or [])
                    + Style.RESET_ALL
                )
        except Exception as exc:
            print(Fore.YELLOW + f"Provider refresh failed ({exc})." + Style.RESET_ALL)

    if found == 0:
        print(Fore.RED + f"No known keys found in any database for {app_id}." + Style.RESET_ALL)
        # Step 3: revobd.club — parse keys and inject into keys_dict (last resort)
        print(Fore.CYAN + f"[Step 3] Trying revobd.club pre-built Lua archive..." + Style.RESET_ALL)
        # _REVO_PATTERN is defined at module level
        try:
            revo_resp = _httpx.get(
                f"https://api.luagen.revobd.club/{app_id}.zip",
                timeout=20,
                follow_redirects=True,
            )
            if revo_resp.status_code == 200 and revo_resp.content:
                lua_bytes = read_lua_from_zip(io.BytesIO(revo_resp.content), decode=False)
                if lua_bytes:
                    revo_keys = dict(_REVO_PATTERN.findall(lua_bytes.decode("utf-8", errors="ignore")))
                    injected = 0
                    for d in depots:
                        if d not in keys_dict and d in revo_keys:
                            keys_dict[d] = revo_keys[d]
                            injected += 1
                    if injected > 0:
                        print(Fore.GREEN + f"\u2705 revobd.club: Injected {injected} key(s) for {app_id}" + Style.RESET_ALL)
                        found = 0
                        for d in depots:
                            if keys_dict.get(d):
                                found += 1
                        if found > 0:
                            # Append every depotless DLC the game declares so
                            # LumaCore marks them as owned alongside the keyed
                            # depots above.
                            lua_path = dest / f"{app_id}.lua"
                            lua_path.write_text(
                                _build_lua_from_provider(app_id, app_info.get("common", {}).get("name", ""), depots, keys_dict, dlc_app_ids, manifest_map, manifest_sizes),
                                encoding="utf-8",
                            )
                            print(Fore.GREEN + f"\u2705 Built Lua for {app_id} using revobd.club keys ({found} depot(s))" + Style.RESET_ALL)
                            return lua_path
            print(Fore.YELLOW + f"revobd.club: No usable keys for {app_id} (HTTP {revo_resp.status_code})." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.YELLOW + f"revobd.club unreachable ({e})." + Style.RESET_ALL)
        return None

    # Append every depotless DLC the game declares so LumaCore marks them as
    # owned alongside the keyed depots above. Skipping the base appid and any
    # id that already appears as a depot avoids duplicates.
    appended_dlcs = len([d for d in dlc_app_ids if d != str(app_id) and d not in depots])

    lua_path = dest / f"{app_id}.lua"
    with lua_path.open("w", encoding="utf-8") as f:
        f.write(_build_lua_from_provider(app_id, app_info.get("common", {}).get("name", ""), depots, keys_dict, dlc_app_ids, manifest_map, manifest_sizes))

    try:
        from sff.lua.dlc_appid_enricher import append_depotless_dlcs
        append_depotless_dlcs(lua_path, app_id)
    except Exception:
        pass

    if appended_dlcs:
        print(Fore.GREEN + f"[OK] Built custom Lua for {app_id} (Resolved {found} keys natively, +{appended_dlcs} DLC appid(s))" + Style.RESET_ALL)
    else:
        print(Fore.GREEN + f"[OK] Built custom Lua for {app_id} (Resolved {found} keys natively)" + Style.RESET_ALL)
    return lua_path


def get_hubcap(dest, app_id, depotcache = None):
    if not app_id or not str(app_id).strip().isdigit():
        print(Fore.RED + f"Invalid App ID: '{app_id}'" + Style.RESET_ALL)
        return None
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
            detail = ""
            try:
                detail = stats_resp.json().get("detail", "")
            except Exception:
                pass
            if detail:
                print(Fore.RED + f"\nHubcap error: {detail}" + Style.RESET_ALL)
                if "discord" in detail.lower():
                    print(
                        Fore.YELLOW
                        + "You must be a member of the Hubcap Discord server to use this API.\n"
                          "Join at: https://discord.gg/hubcap — then re-authenticate to get a valid key."
                        + Style.RESET_ALL
                    )
                elif "state" in detail.lower():
                    print(
                        Fore.YELLOW
                        + "OAuth state error — your authentication session expired or was already used.\n"
                          "Go to https://hubcapmanifest.com and log in again to get a fresh API key."
                        + Style.RESET_ALL
                    )
            else:
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
                    # Try to decode server response for a useful error message.
                    # Hubcap sometimes returns an HTML 404 page (or Cloudflare
                    # interstitial) wrapped in HTTP 200. Detect that shape
                    # specifically so users get a clear "not on Hubcap" line
                    # instead of a wall of HTML in the log.
                    try:
                        decoded = data.decode("utf-8", errors="replace")
                    except Exception:
                        decoded = repr(data[:200])
                    stripped = decoded.lstrip().lower()
                    looks_html = stripped.startswith("<!doctype") or stripped.startswith("<html")
                    if looks_html:
                        if "page not found" in decoded.lower() or "page-not-found" in decoded.lower():
                            print(
                                Fore.RED
                                + f"Hubcap: app {app_id} is not in the Hubcap database. "
                                "Try Ryuu or oureveryday for this game."
                                + Style.RESET_ALL
                            )
                        else:
                            print(
                                Fore.RED
                                + "Hubcap returned an HTML page instead of a Lua zip "
                                "(rate limit, Cloudflare challenge, or service down). "
                                "Try again in a minute or pick a different provider."
                                + Style.RESET_ALL
                            )
                        break
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
            _update_fallback_depotkeys(lua_bytes)
            try:
                from sff.lua.dlc_appid_enricher import append_depotless_dlcs
                appended = append_depotless_dlcs(lua_path, app_id)
                if appended:
                    logger.debug(
                        "hubcap: appended %d depotless dlc line(s) for %s",
                        appended, app_id,
                    )
            except Exception as e:
                logger.debug("hubcap: dlc enricher raised for %s: %s", app_id, e)
            return lua_path
        return None


def get_ryuu(dest, app_id, depotcache=None, request_update=None, branch=None, file_type=None):
    if not app_id or not str(app_id).strip().isdigit():
        print(Fore.RED + f"Invalid App ID: '{app_id}'" + Style.RESET_ALL)
        return None

    branch = (branch or "").strip() or "public"
    file_type = (file_type or "").strip().lower() or "zip"

    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        if not (ryuu_key := get_setting(Settings.RYUU_KEY)):
            ryuu_key = prompt_secret(
                "Paste your Ryuu API key: ",
                lambda x: bool(x.strip()),
                "API key cannot be empty.",
                long_instruction="Contact Ryuu staff to get an API key.",
            ).strip()
            set_setting(Settings.RYUU_KEY, ryuu_key)

        if request_update:
            try:
                upd_resp = httpx.get(
                    "https://generator.ryuu.lol/resellerrequestupdate",
                    params={"appid": str(app_id), "auth_code": ryuu_key},
                    timeout=30, follow_redirects=True,
                )
                if upd_resp.status_code == 200:
                    msg = upd_resp.json().get("message", "OK")
                    print(Fore.GREEN + f"Ryuu update: {msg}" + Style.RESET_ALL)
                elif upd_resp.status_code == 400:
                    body = (upd_resp.text or "")[:4096]
                    print(Fore.YELLOW + f"ryuu rejected update: 400 (appid not in db) {body}" + Style.RESET_ALL)
                else:
                    body = (upd_resp.text or "")[:4096]
                    print(Fore.YELLOW + f"ryuu rejected update: {upd_resp.status_code} {body}" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.YELLOW + f"Ryuu update request failed ({e}). Continuing..." + Style.RESET_ALL)
            request_update = False

        # Try old endpoint first (auth_code param, works for normal reseller users)
        lua_bytes = _ryuu_download_old(app_id, ryuu_key, dest, depotcache, file_type)
        if lua_bytes is not None:
            return _ryuu_save_lua(lua_bytes, dest, app_id)

        # Try new endpoint with API key (X-Auth-Key header, premium users)
        api_key = (get_setting(Settings.RYUU_API_KEY) or "").strip()
        if api_key:
            lua_bytes = _ryuu_download_new(app_id, api_key, branch, file_type)
            if lua_bytes is not None:
                return _ryuu_save_lua(lua_bytes, dest, app_id)

        # Fall back: try old endpoint with API key too
        lua_bytes = _ryuu_download_new(app_id, ryuu_key, branch, file_type)
        if lua_bytes is not None:
            return _ryuu_save_lua(lua_bytes, dest, app_id)

        attempt += 1
        print(Fore.RED + f"ryuu: both endpoints failed (Attempt {attempt}/{max_attempts})" + Style.RESET_ALL)
        if attempt >= max_attempts:
            print(Fore.RED + "Ryuu: Max attempts reached. Check your API key in Settings." + Style.RESET_ALL)
            return None
        if prompt_confirm("Do you want to enter a new API key?"):
            set_setting(Settings.RYUU_KEY, "")
            continue
        return None
    return None


def _ryuu_download_old(app_id, ryuu_key, dest, depotcache, file_type):
    """Old endpoint: auth_code URL param. Works for normal users."""
    url = "https://generator.ryuu.lol/secure_download"
    params = {"appid": str(app_id), "auth_code": ryuu_key}
    if file_type == "lua":
        url = "https://generator.ryuu.lol/resellerlua"
    try:
        resp = httpx.get(url, params=params, timeout=60, follow_redirects=True)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return _ryuu_extract_lua(resp, depotcache, file_type)


def _ryuu_download_new(app_id, ryuu_key, branch="public", file_type="zip"):
    """New endpoint: X-Auth-Key header. Works for premium users."""
    headers = {"X-Auth-Key": ryuu_key}
    params: dict = {"branch": branch}
    if file_type != "zip":
        params["file_type"] = file_type
    try:
        resp = httpx.get(
            "https://generator.ryuu.lol/api/download/" + str(app_id),
            params=params, headers=headers, timeout=60, follow_redirects=True,
        )
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return _ryuu_extract_lua(resp, None, file_type)


def _ryuu_extract_lua(resp, depotcache, file_type):
    if file_type == "lua":
        return resp.content
    return read_lua_from_zip(io.BytesIO(resp.content), decode=False, depotcache=depotcache)


def _ryuu_save_lua(lua_bytes, dest, app_id):
    if lua_bytes is None:
        print(Fore.RED + "Ryuu: downloaded but no .lua content found." + Style.RESET_ALL)
        return None
    lua_path = dest / f"{app_id}.lua"
    with lua_path.open("wb") as f:
        f.write(lua_bytes)
    _update_fallback_depotkeys(lua_bytes)
    try:
        from sff.lua.dlc_appid_enricher import append_depotless_dlcs
        append_depotless_dlcs(lua_path, app_id)
    except Exception:
        pass
    print(Fore.GREEN + f"[OK] Ryuu: Downloaded Lua for {app_id}" + Style.RESET_ALL)
    return lua_path
