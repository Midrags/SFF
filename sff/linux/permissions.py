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

import stat
from pathlib import Path

from colorama import Fore, Style

ELF_MAGIC = b"\x7fELF"
LINUX_EXTS = {".sh", ".x86", ".x86_64", ".bin"}


def set_executable_permissions(game_dir: Path, print_fn=print) -> int:
    count = 0
    try:
        for f in game_dir.rglob("*"):
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            should_chmod = False
            if suffix in LINUX_EXTS:
                should_chmod = True
            elif not suffix:
                try:
                    if f.stat().st_size >= 1024:
                        with f.open("rb") as fh:
                            magic = fh.read(4)
                        if magic == ELF_MAGIC:
                            should_chmod = True
                except Exception:
                    pass
            if should_chmod:
                try:
                    current = f.stat().st_mode
                    new_mode = current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                    if new_mode != current:
                        f.chmod(new_mode)
                        count += 1
                        print_fn(f"  chmod +x: {f.name}")
                except Exception as e:
                    print_fn(Fore.YELLOW + f"  chmod failed for {f.name}: {e}" + Style.RESET_ALL)
    except Exception as e:
        print_fn(Fore.RED + f"Permission scan error: {e}" + Style.RESET_ALL)
    if count:
        print_fn(Fore.GREEN + f"Set executable on {count} file(s)." + Style.RESET_ALL)
    return count
