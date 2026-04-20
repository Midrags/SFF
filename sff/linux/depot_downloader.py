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
import subprocess
from pathlib import Path

from colorama import Fore, Style

from sff.linux import dotnet
from sff.utils import root_folder

KEYS_TMP = Path("/tmp/mistwalker_keys.vdf")
MANIFESTS_TMP = Path("/tmp/mistwalker_manifests")


def get_deps_dir() -> Path:
    return root_folder() / "third_party" / "linux" / "deps"


def run_download(
    game_data: dict,
    selected_depots: list,
    dest_path: Path,
    print_fn=print,
) -> bool:
    appid = str(game_data["appid"])
    depots = game_data.get("depots", {})
    manifests = game_data.get("manifests", {})
    installdir = game_data.get("installdir") or f"App_{appid}"

    dotnet_path = dotnet.get_dotnet_path()
    if not dotnet_path:
        print_fn(Fore.RED + ".NET 9 not available. Cannot download." + Style.RESET_ALL)
        return False

    dll_path = get_deps_dir() / "DepotDownloaderMod.dll"
    if not dll_path.exists():
        print_fn(Fore.RED + f"DepotDownloaderMod.dll not found at {dll_path}" + Style.RESET_ALL)
        return False

    try:
        lines = []
        for depot_id in selected_depots:
            key = depots.get(str(depot_id), {}).get("key", "")
            if key:
                lines.append(f"{depot_id};{key}")
        KEYS_TMP.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        print_fn(Fore.RED + f"Failed to write depot keys: {e}" + Style.RESET_ALL)
        return False

    MANIFESTS_TMP.mkdir(parents=True, exist_ok=True)

    dotnet_root = str(Path(dotnet_path).parent.parent)
    env = os.environ.copy()
    env["DOTNET_ROOT"] = dotnet_root

    download_dir = dest_path / "steamapps" / "common" / installdir
    download_dir.mkdir(parents=True, exist_ok=True)

    all_ok = True
    for depot_id in selected_depots:
        depot_id_str = str(depot_id)
        manifest_id = manifests.get(depot_id_str)

        cmd = [
            dotnet_path, str(dll_path),
            "-app", appid,
            "-depot", depot_id_str,
            "-depotkeys", str(KEYS_TMP),
            "-max-downloads", "255",
            "-dir", str(download_dir),
            "-validate",
        ]

        if manifest_id:
            manifest_file = MANIFESTS_TMP / f"{depot_id_str}_{manifest_id}.manifest"
            cmd += ["-manifest", manifest_id, "-manifestfile", str(manifest_file)]

        print_fn(Fore.CYAN + f"\nDownloading depot {depot_id_str}..." + Style.RESET_ALL)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=str(get_deps_dir()),
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    print_fn(line)
            proc.wait()
            if proc.returncode != 0:
                print_fn(Fore.YELLOW + f"Depot {depot_id_str} exited with code {proc.returncode}" + Style.RESET_ALL)
                all_ok = False
        except Exception as e:
            print_fn(Fore.RED + f"Error downloading depot {depot_id_str}: {e}" + Style.RESET_ALL)
            all_ok = False

    try:
        KEYS_TMP.unlink(missing_ok=True)
    except Exception:
        pass

    return all_ok
