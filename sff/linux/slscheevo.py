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

import shutil
import subprocess
import sys
from pathlib import Path

from colorama import Fore, Style

from sff.utils import root_folder

SUCCESS_CODES = (0, 10)


def get_slscheevo_script() -> Path:
    return root_folder() / "third_party" / "linux" / "slscheevo" / "SLScheevo.py"


def get_save_dir() -> Path:
    save_dir = Path.home() / ".local" / "share" / "SteaMidra" / "SLScheevo"
    save_dir.mkdir(parents=True, exist_ok=True)
    data_dir = save_dir / "data"
    data_dir.mkdir(exist_ok=True)
    template_src = get_slscheevo_script().parent / "data" / "UserGameStats_TEMPLATE.bin"
    template_dst = data_dir / "UserGameStats_TEMPLATE.bin"
    if template_src.exists() and not template_dst.exists():
        shutil.copy2(template_src, template_dst)
    return save_dir


def is_available() -> bool:
    return get_slscheevo_script().exists()


def generate(app_ids, print_fn=print) -> bool:
    if not is_available():
        print_fn(Fore.RED + "SLScheevo not found. Cannot generate achievements." + Style.RESET_ALL)
        return False

    save_dir = get_save_dir()
    script = get_slscheevo_script()

    venv_python = script.parent / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    if isinstance(app_ids, int):
        app_ids = [app_ids]

    cmd = [
        python_cmd, str(script),
        "--noclear",
        "--save-dir", str(save_dir),
        "--silent",
        "--max-tries", "101",
        "--appid", ",".join(str(i) for i in app_ids),
    ]

    print_fn(Fore.CYAN + f"Running SLScheevo for AppID(s): {app_ids}" + Style.RESET_ALL)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(script.parent),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print_fn(line)
        proc.wait()
        if proc.returncode in SUCCESS_CODES:
            print_fn(Fore.GREEN + "Achievement generation complete." + Style.RESET_ALL)
            return True
        else:
            print_fn(Fore.YELLOW + f"SLScheevo exited with code {proc.returncode}" + Style.RESET_ALL)
            return False
    except Exception as e:
        print_fn(Fore.RED + f"SLScheevo error: {e}" + Style.RESET_ALL)
        return False
