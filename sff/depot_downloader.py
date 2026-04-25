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
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Tuple

from colorama import Fore, Style

from sff.dotnet_utils import get_dotnet_path
from sff.utils import root_folder

KEYS_TMP = Path(tempfile.gettempdir()) / "mistwalker_keys.vdf"
MANIFESTS_TMP = Path(tempfile.gettempdir()) / "mistwalker_manifests"


def get_deps_dir() -> Path:
    return root_folder() / "third_party" / "linux" / "deps"


def get_ddmod_dll() -> Path:
    return get_deps_dir() / "DepotDownloaderMod.dll"


def _copy_manifests_to_temp(steam_path: Path, manifests: dict) -> None:
    MANIFESTS_TMP.mkdir(parents=True, exist_ok=True)
    depotcache = steam_path / "depotcache"
    if not depotcache.exists():
        return
    for depot_id, manifest_id in manifests.items():
        src = depotcache / f"{depot_id}_{manifest_id}.manifest"
        if src.exists():
            dst = MANIFESTS_TMP / src.name
            shutil.copy2(src, dst)

    staging = Path.cwd() / "manifests"
    if staging.exists():
        for depot_id, manifest_id in manifests.items():
            src = staging / f"{depot_id}_{manifest_id}.manifest"
            if src.exists():
                dst = MANIFESTS_TMP / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)


def _read_process_output(proc: subprocess.Popen, print_fn) -> None:
    if not proc.stdout:
        return
    buffer = bytearray()
    while True:
        chunk = proc.stdout.read(1)
        if not chunk:
            if proc.poll() is not None:
                break
            time.sleep(0.01)
            continue
        if chunk in (b"\r", b"\n"):
            if buffer:
                line = buffer.decode("utf-8", errors="replace").strip()
                if line:
                    print_fn(line)
                buffer.clear()
        else:
            buffer.extend(chunk)
    if buffer:
        line = buffer.decode("utf-8", errors="replace").strip()
        if line:
            print_fn(line)


def _calculate_dir_size(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def run_download(
    game_data: dict,
    selected_depots: list,
    dest_path: Path,
    steam_path: Path,
    print_fn=print,
) -> Tuple[bool, int]:
    appid = str(game_data["appid"])
    depots = game_data.get("depots", {})
    manifests = game_data.get("manifests", {})
    installdir = game_data.get("installdir") or f"App_{appid}"

    dotnet_path = get_dotnet_path()
    if not dotnet_path:
        print_fn(Fore.RED + ".NET 9 not available. Cannot download." + Style.RESET_ALL)
        return False, 0

    dll_path = get_ddmod_dll()
    if not dll_path.exists():
        print_fn(Fore.RED + f"DepotDownloaderMod.dll not found at {dll_path}" + Style.RESET_ALL)
        return False, 0

    try:
        lines = []
        for depot_id in selected_depots:
            key = depots.get(str(depot_id), {}).get("key", "")
            if key:
                lines.append(f"{depot_id};{key}")
        KEYS_TMP.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        print_fn(Fore.RED + f"Failed to write depot keys: {e}" + Style.RESET_ALL)
        return False, 0

    _copy_manifests_to_temp(steam_path, manifests)

    dotnet_root = os.path.dirname(dotnet_path)
    env = os.environ.copy()
    env["DOTNET_ROOT"] = dotnet_root
    current_path = env.get("PATH", "")
    if dotnet_root not in current_path.split(os.pathsep):
        env["PATH"] = dotnet_root + os.pathsep + current_path

    download_dir = dest_path / "steamapps" / "common" / installdir
    download_dir.mkdir(parents=True, exist_ok=True)

    deps_dir = get_deps_dir()
    total_depots = len(selected_depots)
    all_ok = True

    for i, depot_id in enumerate(selected_depots):
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
            if manifest_file.exists():
                cmd += ["-manifest", str(manifest_id), "-manifestfile", str(manifest_file)]
            else:
                cmd += ["-manifest", str(manifest_id)]

        print_fn(
            Fore.CYAN
            + f"\n--- Downloading depot {depot_id_str} ({i + 1}/{total_depots}) ---"
            + Style.RESET_ALL
        )

        creation_flags = 0
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": False,
                "env": env,
                "cwd": str(deps_dir),
            }
            if creation_flags:
                popen_kwargs["creationflags"] = creation_flags

            proc = subprocess.Popen(cmd, **popen_kwargs)
            _read_process_output(proc, print_fn)
            proc.wait()

            if proc.returncode != 0:
                print_fn(
                    Fore.YELLOW
                    + f"Depot {depot_id_str} exited with code {proc.returncode}"
                    + Style.RESET_ALL
                )
                all_ok = False
            else:
                print_fn(
                    Fore.GREEN
                    + f"Depot {depot_id_str} downloaded successfully."
                    + Style.RESET_ALL
                )

        except FileNotFoundError:
            print_fn(
                Fore.RED
                + f"ERROR: '{dotnet_path}' not found. Ensure .NET 9 is installed."
                + Style.RESET_ALL
            )
            all_ok = False
            break
        except (OSError, subprocess.SubprocessError) as e:
            print_fn(Fore.RED + f"Error downloading depot {depot_id_str}: {e}" + Style.RESET_ALL)
            all_ok = False

    try:
        KEYS_TMP.unlink(missing_ok=True)
    except Exception:
        pass

    size_on_disk = _calculate_dir_size(download_dir)
    print_fn(
        Fore.CYAN
        + f"Total size on disk: {size_on_disk:,} bytes"
        + Style.RESET_ALL
    )

    return all_ok, size_on_disk


def move_manifests_to_depotcache(dest_path: Path, manifests_dict: dict, print_fn=print) -> None:
    depotcache = dest_path / "depotcache"
    depotcache.mkdir(parents=True, exist_ok=True)

    if MANIFESTS_TMP.exists():
        for depot_id, manifest_id in manifests_dict.items():
            manifest_filename = f"{depot_id}_{manifest_id}.manifest"
            src = MANIFESTS_TMP / manifest_filename
            dst = depotcache / manifest_filename
            if src.exists():
                try:
                    shutil.move(str(src), str(dst))
                except Exception:
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass

        try:
            shutil.rmtree(MANIFESTS_TMP, ignore_errors=True)
        except Exception:
            pass

    staging = Path.cwd() / "manifests"
    if staging.exists():
        for f in staging.glob("*.manifest"):
            dst = depotcache / f.name
            if not dst.exists():
                try:
                    shutil.copy2(f, dst)
                except Exception:
                    pass

    print_fn(Fore.GREEN + f"Manifests placed in depotcache: {depotcache}" + Style.RESET_ALL)
