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
import subprocess
from pathlib import Path

from colorama import Fore, Style

from sff.linux import dotnet
from sff.utils import root_folder

SKIP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^unins.*\.exe$", r"^setup.*\.exe$", r"^config.*\.exe$",
        r"^launcher.*\.exe$", r"^updater.*\.exe$", r"^patch.*\.exe$",
        r"^redist.*\.exe$", r"^vcredist.*\.exe$", r"^dxsetup.*\.exe$",
        r"^physx.*\.exe$", r".*crash.*\.exe$", r".*handler.*\.exe$",
        r"^unity.*\.exe$", r".*unity.*\.exe$", r".*\.original\.exe$",
    ]
]
MIN_EXE_SIZE = 100 * 1024


def get_steamless_dir() -> Path:
    return root_folder() / "third_party" / "linux" / "deps" / "Steamless"


def find_game_executables(game_dir: Path, game_name: str = "") -> list:
    results = []
    try:
        for f in game_dir.rglob("*.exe"):
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except Exception:
                continue
            if size < MIN_EXE_SIZE:
                continue
            name_lower = f.name.lower()
            if any(p.match(name_lower) for p in SKIP_PATTERNS):
                continue
            priority = 0
            if game_name and game_name.lower().replace(" ", "") in name_lower.replace(" ", ""):
                priority += 3
            try:
                depth = len(f.relative_to(game_dir).parts)
                if depth == 1:
                    priority += 2
            except Exception:
                pass
            priority += size // (10 * 1024 * 1024)
            results.append({"path": f, "name": f.name, "size": size, "priority": priority})
    except Exception:
        pass
    results.sort(key=lambda x: x["priority"], reverse=True)
    return results


def process_game(game_dir: Path, game_name: str = "", print_fn=print) -> bool:
    if not dotnet.ensure_dotnet_9(print_fn):
        return False

    exe_files = find_game_executables(game_dir, game_name)
    if not exe_files:
        print_fn(Fore.YELLOW + "No suitable .exe files found for Steamless." + Style.RESET_ALL)
        return False

    dotnet_path = dotnet.get_dotnet_path()
    dll = get_steamless_dir() / "Steamless.CLI.dll"
    if not dll.exists():
        print_fn(Fore.RED + f"Steamless.CLI.dll not found at {dll}" + Style.RESET_ALL)
        return False

    dotnet_root = str(Path(dotnet_path).parent.parent)
    env = os.environ.copy()
    env["DOTNET_ROOT"] = dotnet_root

    success_count = 0
    for exe_info in exe_files:
        exe_path = exe_info["path"]
        print_fn(f"Running Steamless on: {exe_info['name']}")
        try:
            result = subprocess.run(
                [dotnet_path, str(dll), "-f", str(exe_path), "--quiet", "--realign"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(get_steamless_dir()),
                timeout=120,
            )
            if result.returncode == 0:
                print_fn(Fore.GREEN + f"  DRM removed: {exe_info['name']}" + Style.RESET_ALL)
                success_count += 1
            elif result.returncode == 1:
                print_fn(f"  No DRM found: {exe_info['name']}")
            else:
                print_fn(Fore.YELLOW + f"  Steamless error ({result.returncode}): {exe_info['name']}" + Style.RESET_ALL)
                if result.stdout:
                    print_fn(result.stdout[:300])
        except subprocess.TimeoutExpired:
            print_fn(Fore.YELLOW + f"  Steamless timed out on {exe_info['name']}" + Style.RESET_ALL)
        except Exception as e:
            print_fn(Fore.RED + f"  Steamless exception: {e}" + Style.RESET_ALL)

    return success_count > 0
