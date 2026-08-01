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

import os
import re
from pathlib import Path

from colorama import Fore, Style


def _sanitize_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def _normalise_manifest_map(manifests: dict) -> dict[str, str]:
    clean: dict[str, str] = {}
    for depot_id, manifest_id in (manifests or {}).items():
        depot_str = str(depot_id).strip()
        manifest_str = str(manifest_id).strip()
        if depot_str.isdigit() and manifest_str.isdigit():
            clean[depot_str] = manifest_str
    return clean


def _depot_size(depots: dict, depot_id: str) -> str:
    info = depots.get(depot_id) or depots.get(int(depot_id) if depot_id.isdigit() else depot_id) or {}
    value = info.get("size", "0") if isinstance(info, dict) else "0"
    value_str = str(value).strip()
    return value_str if value_str.isdigit() else "0"


def create_acf(
    game_data: dict,
    dest_path: Path,
    selected_depots: list,
    size_on_disk: int = 0,
    print_fn=print,
    steam_path: Path | None = None,
) -> bool:
    appid = str(game_data["appid"])
    game_name = game_data.get("game_name", f"App {appid}")
    installdir = game_data.get("installdir") or _sanitize_name(game_name) or f"App_{appid}"
    buildid = str(game_data.get("buildid", "0"))
    manifests = _normalise_manifest_map(game_data.get("manifests", {}))
    depots = game_data.get("depots", {})

    steamapps_dir = dest_path / "steamapps"
    steamapps_dir.mkdir(parents=True, exist_ok=True)
    acf_path = steamapps_dir / f"appmanifest_{appid}.acf"

    installed_depots_lines = []
    for depot_id in selected_depots:
        depot_id_str = str(depot_id)
        manifest_gid = manifests.get(depot_id_str, "")
        if manifest_gid:
            depot_size = _depot_size(depots, depot_id_str)
            depot_info = depots.get(depot_id_str) or depots.get(int(depot_id_str) if depot_id_str.isdigit() else depot_id_str) or {}
            dlcappid = depot_info.get("dlcappid", "") if isinstance(depot_info, dict) else ""
            dlc_line = f'\t\t\t"dlcappid"\t\t"{dlcappid}"\n' if dlcappid else ""
            installed_depots_lines.append(
                f'\t\t"{depot_id_str}"\n\t\t{{\n'
                f'\t\t\t"manifest"\t\t"{manifest_gid}"\n'
                f'\t\t\t"size"\t\t"{depot_size}"\n'
                f'{dlc_line}'
                f'\t\t}}'
            )

    if selected_depots and not installed_depots_lines:
        print_fn(Fore.RED + "Refusing to write ACF: no manifest IDs for selected depots." + Style.RESET_ALL)
        return False

    installed_depots_block = "\n".join(installed_depots_lines)

    import time as _time
    _now = str(int(_time.time()))
    _last_owner = "0"
    try:
        from sff.storage.settings import get_setting
        from sff.structs import Settings
        sid = get_setting(Settings.STEAM_ID)
        if sid and str(sid).strip():
            _last_owner = str(sid).strip()
    except Exception:
        pass
    _launcher_path = ""
    if steam_path:
        _launcher_path = str(steam_path / "steam.exe" if sys.platform == "win32" else steam_path / "ubuntu12_32" / "steam")
    acf_content = (
        '"AppState"\n'
        '{\n'
        f'\t"appid"\t\t"{appid}"\n'
        f'\t"Universe"\t\t"1"\n'
        f'\t"name"\t\t"{game_name}"\n'
        f'\t"StateFlags"\t\t"4"\n'
        f'\t"installdir"\t\t"{installdir}"\n'
        f'\t"LastUpdated"\t\t"{_now}"\n'
        f'\t"SizeOnDisk"\t\t"{size_on_disk}"\n'
        f'\t"StagingSize"\t\t"0"\n'
        f'\t"buildid"\t\t"{buildid}"\n'
        f'\t"LastOwner"\t\t"{_last_owner}"\n'
        f'\t"UpdateResult"\t\t"0"\n'
        f'\t"BytesToDownload"\t\t"{size_on_disk}"\n'
        f'\t"BytesDownloaded"\t\t"{size_on_disk}"\n'
        f'\t"BytesToStage"\t\t"0"\n'
        f'\t"BytesStaged"\t\t"0"\n'
        f'\t"TargetBuildID"\t\t"{buildid}"\n'
        f'\t"AutoUpdateBehavior"\t\t"0"\n'
        f'\t"AllowOtherDownloadsWhileRunning"\t\t"0"\n'
        f'\t"ScheduledAutoUpdate"\t\t"0"\n'
        f'\t"DownloadType"\t\t"1"\n'
        f'\t"InstalledDepots"\n'
        f'\t{{\n'
        f'{installed_depots_block}\n'
        f'\t}}\n'
        f'\t"UserConfig"\n'
        f'\t{{\n'
        f'\t\t"language"\t\t"english"\n'
        f'\t}}\n'
        f'\t"MountedConfig"\n'
        f'\t{{\n'
        f'\t\t"language"\t\t"english"\n'
        f'\t}}\n'
        '}\n'
    )

    try:
        acf_path.write_text(acf_content, encoding="utf-8")
        os.chmod(acf_path, 0o444)
        print_fn(Fore.GREEN + f"ACF written: {acf_path}" + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.RED + f"Failed to write ACF: {e}" + Style.RESET_ALL)
        return False
