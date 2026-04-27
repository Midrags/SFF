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

import re
import shutil
import time
from pathlib import Path

from colorama import Fore, Style

from sff.linux import acf_writer, depot_downloader, permissions, slscheevo, slssteam, steam_process
from sff.linux.dotnet import ensure_dotnet_9
from sff.linux.depot_downloader import MANIFESTS_TMP
from sff.lua.manager import LuaManager
from sff.prompts import prompt_confirm, prompt_dir, prompt_select
from sff.steam_store import get_app_name_from_store
from sff.storage.vdf import ensure_library_has_app, get_steam_libs
from sff.structs import OSType


_MANIFEST_ID_RE = re.compile(
    r"setManifestid\s*\(\s*(\d+)\s*,\s*[\"']([0-9a-fA-F]+)[\"']\s*\)"
)


def _parse_manifest_ids(lua_text: str) -> dict:
    return {m.group(1): m.group(2) for m in _MANIFEST_ID_RE.finditer(lua_text)}


def _get_manifests_from_staging() -> dict:
    staging = Path.cwd() / "manifests"
    result = {}
    if not staging.exists():
        return result
    for f in staging.glob("*.manifest"):
        parts = f.stem.split("_", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            result[parts[0]] = parts[1]
    return result


def _build_game_data(lua_parsed, steam_path: Path) -> dict:
    appid = str(lua_parsed.app_id)

    depots_dict = {}
    for dp in lua_parsed.depots:
        depots_dict[str(dp.depot_id)] = {"key": dp.decryption_key}

    manifests = _get_manifests_from_staging()
    if not manifests:
        manifests = _parse_manifest_ids(lua_parsed.contents)

    game_name = get_app_name_from_store(int(appid)) or f"App {appid}"

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", game_name).strip()
    installdir = safe_name or f"App_{appid}"

    buildid = "0"
    try:
        from sff.steam_client import create_provider_for_current_thread
        provider = create_provider_for_current_thread()
        app_data = provider.get_single_app_info(int(appid))
        bid = (
            app_data.get("depots", {})
            .get("branches", {})
            .get("public", {})
            .get("buildid")
        )
        if bid:
            buildid = str(bid)
    except Exception:
        pass

    return {
        "appid": appid,
        "game_name": game_name,
        "installdir": installdir,
        "buildid": buildid,
        "depots": depots_dict,
        "manifests": manifests,
    }


def _select_destination(steam_path: Path) -> Path | None:
    libs = get_steam_libs(steam_path)
    if not libs:
        print(Fore.YELLOW + "No Steam libraries detected." + Style.RESET_ALL)
        custom = prompt_dir("Enter the path to your Steam library folder:")
        return custom if custom else None
    if len(libs) == 1:
        print(Fore.CYAN + f"Using Steam library: {libs[0]}" + Style.RESET_ALL)
        return libs[0]
    choice = prompt_select(
        "Install game to which Steam library?",
        [(str(p), p) for p in libs],
        cancellable=True,
    )
    return choice


def _move_manifests_to_depotcache(dest_path: Path, print_fn=print) -> None:
    depotcache = dest_path / "steamapps" / "depotcache"
    depotcache.mkdir(parents=True, exist_ok=True)

    tmp_mf = MANIFESTS_TMP
    if tmp_mf.exists():
        for f in tmp_mf.glob("*.manifest"):
            try:
                shutil.copy2(f, depotcache / f.name)
            except Exception:
                pass
        try:
            shutil.rmtree(tmp_mf, ignore_errors=True)
        except Exception:
            pass

    staging = Path.cwd() / "manifests"
    if staging.exists():
        for f in staging.glob("*.manifest"):
            try:
                dest_file = depotcache / f.name
                if not dest_file.exists():
                    shutil.copy2(f, dest_file)
            except Exception:
                pass

    print_fn(Fore.GREEN + f"Manifests placed in depotcache: {depotcache}" + Style.RESET_ALL)


def _add_to_slssteam(game_data: dict, selected_depots: list, steam_path: Path, print_fn=print) -> None:
    try:
        from sff.app_injector.sls import SLSManager
        sls = SLSManager(steam_path, None)

        appid_int = int(game_data["appid"])
        sls.add_ids(appid_int)

        token = game_data.get("token")
        if token:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            try:
                import yaml
                config_path = sls.sls_config_path
                with config_path.open(encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                if isinstance(cfg, dict):
                    tokens = cfg.setdefault("AppTokens", {})
                    tokens[str(game_data["appid"])] = token
                    with config_path.open("w", encoding="utf-8") as f:
                        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                print_fn(Fore.YELLOW + f"Could not write AppToken: {e}" + Style.RESET_ALL)

        dlcs = [
            dp for dp in selected_depots
            if str(dp) != str(game_data["appid"])
        ]
        if len(dlcs) > 64:
            try:
                import yaml
                config_path = sls.sls_config_path
                with config_path.open(encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                if isinstance(cfg, dict):
                    dlc_data = cfg.setdefault("DlcData", {})
                    app_entry = dlc_data.setdefault(str(game_data["appid"]), {})
                    for dlc_id in dlcs:
                        app_entry[str(dlc_id)] = {}
                    with config_path.open("w", encoding="utf-8") as f:
                        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
                    print_fn(f"Added {len(dlcs)} DLCs to SLSsteam DlcData.")
            except Exception as e:
                print_fn(Fore.YELLOW + f"Could not write DlcData: {e}" + Style.RESET_ALL)

    except Exception as e:
        print_fn(Fore.YELLOW + f"SLSsteam config update failed: {e}" + Style.RESET_ALL)


def handle_linux_download(steam_path: Path) -> None:
    print(Fore.CYAN + "\n=== Download Game (Linux) ===" + Style.RESET_ALL)

    if not ensure_dotnet_9():
        if not prompt_confirm("Continue anyway (download will fail without .NET 9)?", false_msg="Cancel"):
            return
    else:
        if not slssteam.is_installed():
            print(Fore.YELLOW + "SLSsteam is not installed. Run 'Set up Linux tools' first." + Style.RESET_ALL)

    lua_manager = LuaManager(OSType.LINUX)
    lua_parsed = lua_manager.fetch_lua()
    if lua_parsed is None:
        return

    if not lua_parsed.depots:
        print(Fore.RED + "No depots with keys found in this lua." + Style.RESET_ALL)
        return

    game_data = _build_game_data(lua_parsed, steam_path)
    appid = game_data["appid"]
    game_name = game_data["game_name"]

    print(Fore.GREEN + f"\nGame: {game_name} (AppID: {appid})" + Style.RESET_ALL)
    if game_data["manifests"]:
        print(f"Manifest IDs found: {len(game_data['manifests'])}")
    else:
        print(Fore.YELLOW + "No manifest IDs found — will download latest from CDN." + Style.RESET_ALL)

    depot_choices = [
        (f"{dp.depot_id} — {dp.decryption_key[:12]}...", int(dp.depot_id))
        for dp in lua_parsed.depots
        if dp.decryption_key
    ]
    if not depot_choices:
        print(Fore.RED + "No depots with decryption keys available." + Style.RESET_ALL)
        return

    selected_depots = prompt_select(
        "Select depots to download:",
        depot_choices,
        multiselect=True,
        long_instruction="Space to select, Enter to confirm. Ctrl+Z to cancel.",
        mandatory=False,
        cancellable=True,
    )
    if not selected_depots:
        print("No depots selected.")
        return
    if not isinstance(selected_depots, list):
        selected_depots = [selected_depots]

    dest_path = _select_destination(steam_path)
    if dest_path is None:
        print("No destination selected. Aborting.")
        return

    print(Fore.CYAN + f"\nDownloading to: {dest_path}" + Style.RESET_ALL)

    ok, size_on_disk = depot_downloader.run_download(
        game_data, selected_depots, dest_path, steam_path,
    )

    acf_writer.create_acf(game_data, dest_path, selected_depots, size_on_disk=size_on_disk)

    _move_manifests_to_depotcache(dest_path)

    try:
        ensure_library_has_app(steam_path, dest_path, int(appid))
    except Exception:
        pass

    _add_to_slssteam(game_data, selected_depots, steam_path)

    game_dir = dest_path / "steamapps" / "common" / game_data["installdir"]
    if game_dir.exists():
        permissions.set_executable_permissions(game_dir)
        print(Fore.CYAN + "\nRunning Steamless DRM removal..." + Style.RESET_ALL)
        from sff.linux import steamless as sl
        sl.process_game(game_dir, game_name)
    else:
        print(Fore.YELLOW + f"Game directory not found at {game_dir}" + Style.RESET_ALL)

    if ok:
        print(Fore.GREEN + f"\n✓ Download complete: {game_name}" + Style.RESET_ALL)
    else:
        print(Fore.YELLOW + "\nDownload finished with warnings. Check output above." + Style.RESET_ALL)

    if prompt_confirm("Generate achievements with SLScheevo?"):
        slscheevo.generate([int(appid)])


def handle_linux_setup(steam_path: Path) -> None:
    print(Fore.CYAN + "\n=== Linux Tools Setup ===" + Style.RESET_ALL)

    print("\n[1/2] Checking .NET 9 runtime...")
    ensure_dotnet_9()

    print("\n[2/2] SLSsteam setup...")
    if slssteam.is_installed():
        print(Fore.GREEN + "SLSsteam is already installed." + Style.RESET_ALL)
        installed_ver = slssteam.get_installed_version()
        if installed_ver:
            print(f"  Installed version: {installed_ver}")
        action = prompt_select(
            "What would you like to do?",
            [
                ("Check for updates", "check"),
                ("Reinstall/update from GitHub", "reinstall"),
                ("Skip", "skip"),
            ],
            cancellable=True,
        )
        if action is None or action == "skip":
            print(Fore.GREEN + "\nSetup complete." + Style.RESET_ALL)
            return
        if action == "check":
            info = slssteam.check_update_available()
            if info["update_available"]:
                print(
                    Fore.YELLOW
                    + f"Update available: {info['installed']} → {info['latest']}"
                    + Style.RESET_ALL
                )
                if not prompt_confirm("Install update now?", default=True):
                    print(Fore.GREEN + "\nSetup complete." + Style.RESET_ALL)
                    return
            else:
                latest = info.get("latest") or "unknown"
                current = info.get("installed") or "unknown"
                print(
                    Fore.GREEN
                    + f"Already up to date (installed: {current}, latest: {latest})."
                    + Style.RESET_ALL
                )
                return
    else:
        print("SLSsteam is not installed.")

    install_ok = slssteam.install_from_github(steam_path)

    if install_ok:
        print(Fore.GREEN + "\nSLSteam installed successfully." + Style.RESET_ALL)
        if prompt_confirm("Restart Steam now to activate SLSteam? (recommended)"):
            print("Stopping Steam...")
            steam_process.kill_steam()
            time.sleep(2)
            print("Starting Steam with SLSteam injection...")
            result = steam_process.start_steam()
            if result == "NEEDS_USER_PATH":
                print(
                    Fore.YELLOW
                    + "SLSteam libraries not found at default paths.\n"
                    + "Please restart Steam manually — it will pick up SLSteam via steam.sh."
                    + Style.RESET_ALL
                )
        else:
            print(
                Fore.YELLOW
                + "Remember to restart Steam manually for SLSteam to take effect."
                + Style.RESET_ALL
            )

    print(Fore.GREEN + "\nSetup complete." + Style.RESET_ALL)


def handle_linux_achievements(steam_path: Path) -> None:
    print(Fore.CYAN + "\n=== Generate Achievements (SLScheevo) ===" + Style.RESET_ALL)

    if not slscheevo.is_available():
        print(Fore.RED + "SLScheevo not found. It should be in third_party/linux/slscheevo/." + Style.RESET_ALL)
        return

    raw = prompt_select(
        "How do you want to specify the AppID?",
        [
            ("Enter App ID manually", "manual"),
            ("Choose from SLSsteam config", "sls"),
        ],
        cancellable=True,
    )
    if not raw:
        return

    app_ids = []
    if raw == "manual":
        from sff.prompts import prompt_text
        appid_str = prompt_text(
            "Enter App ID(s) separated by commas:",
            validator=lambda x: all(p.strip().isdigit() for p in x.split(",") if p.strip()),
            invalid_msg="Enter numbers only, separated by commas.",
        )
        if not appid_str:
            return
        app_ids = [int(x.strip()) for x in appid_str.split(",") if x.strip().isdigit()]
    elif raw == "sls":
        try:
            from sff.app_injector.sls import SLSManager
            sls = SLSManager(steam_path, None)
            ids = sls.get_local_ids()
            if not ids:
                print(Fore.YELLOW + "No App IDs in SLSsteam config." + Style.RESET_ALL)
                return
            selected = prompt_select(
                "Select App ID(s):",
                [(str(i), i) for i in ids],
                multiselect=True,
                mandatory=False,
                cancellable=True,
            )
            if not selected:
                return
            app_ids = list(selected) if isinstance(selected, list) else [selected]
        except Exception as e:
            print(Fore.RED + f"Could not read SLSsteam config: {e}" + Style.RESET_ALL)
            return

    if not app_ids:
        print("No App IDs selected.")
        return

    slscheevo.generate(app_ids)
