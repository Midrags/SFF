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
from pathlib import Path

from colorama import Fore, Style


def _sanitize_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def create_acf(
    game_data: dict,
    dest_path: Path,
    selected_depots: list,
    size_on_disk: int = 0,
    print_fn=print,
) -> bool:
    appid = str(game_data["appid"])
    game_name = game_data.get("game_name", f"App {appid}")
    installdir = game_data.get("installdir") or _sanitize_name(game_name) or f"App_{appid}"
    buildid = str(game_data.get("buildid", "0"))
    manifests = game_data.get("manifests", {})
    depots = game_data.get("depots", {})

    steamapps_dir = dest_path / "steamapps"
    steamapps_dir.mkdir(parents=True, exist_ok=True)
    acf_path = steamapps_dir / f"appmanifest_{appid}.acf"

    installed_depots_lines = []
    has_windows_depot = False
    for depot_id in selected_depots:
        depot_id_str = str(depot_id)
        manifest_gid = manifests.get(depot_id_str, "")
        depot_info = depots.get(depot_id_str, {})
        oslist = depot_info.get("oslist", "")
        if "windows" in oslist.lower():
            has_windows_depot = True
        if manifest_gid:
            installed_depots_lines.append(
                f'\t\t"{depot_id_str}"\n\t\t{{\n'
                f'\t\t\t"manifest"\t\t"{manifest_gid}"\n'
                f'\t\t\t"size"\t\t"0"\n'
                f'\t\t}}'
            )

    installed_depots_block = "\n".join(installed_depots_lines)

    if has_windows_depot:
        user_config = (
            '\t"UserConfig"\n\t{\n'
            '\t\t"platform_override_source"\t\t"windows"\n'
            '\t\t"platform_override_dest"\t\t"linux"\n'
            '\t}\n'
            '\t"MountedConfig"\n\t{\n'
            '\t\t"platform_override_source"\t\t"windows"\n'
            '\t\t"platform_override_dest"\t\t"linux"\n'
            '\t}\n'
        )
    else:
        user_config = '\t"UserConfig"\n\t{\n\t}\n\t"MountedConfig"\n\t{\n\t}\n'

    acf_content = (
        '"AppState"\n'
        '{\n'
        f'\t"appid"\t\t"{appid}"\n'
        f'\t"Universe"\t\t"1"\n'
        f'\t"name"\t\t"{game_name}"\n'
        f'\t"StateFlags"\t\t"4"\n'
        f'\t"installdir"\t\t"{installdir}"\n'
        f'\t"SizeOnDisk"\t\t"{size_on_disk}"\n'
        f'\t"buildid"\t\t"{buildid}"\n'
        f'\t"InstalledDepots"\n'
        f'\t{{\n'
        f'{installed_depots_block}\n'
        f'\t}}\n'
        f'{user_config}'
        '}\n'
    )

    try:
        acf_path.write_text(acf_content, encoding="utf-8")
        print_fn(Fore.GREEN + f"ACF written: {acf_path}" + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.RED + f"Failed to write ACF: {e}" + Style.RESET_ALL)
        return False
