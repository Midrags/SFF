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

from pathlib import Path
import shutil
import subprocess
from typing import Union

from sff.structs import OSType
from sff.utils import root_folder


def run_fzf(choices: Union[list[str], Path], os_type: OSType):
    if isinstance(choices, list):
        choices_str = "\n".join(choices)
    else:
        with choices.open(encoding="utf-8") as f:
            choices_str = f.read()

    cmd = []
    if os_type == OSType.LINUX:
        fzf_path = shutil.which("fzf")
        if fzf_path is None:
            print(
                "You don't have fzf installed. Please install it and try this again."
            )
            return
        cmd = [fzf_path]
    elif os_type == OSType.WINDOWS:
        cmd = [root_folder() / "third_party/fzf/fzf.exe"]
    proc = subprocess.run(
        cmd,
        input=choices_str,
        capture_output=True,
        encoding="utf-8",
    )
    return proc.stdout.strip("\n")
