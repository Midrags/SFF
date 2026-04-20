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
import tempfile
from pathlib import Path

from colorama import Fore, Style


def get_dotnet_path() -> str | None:
    dotnet_home = Path.home() / ".dotnet" / "dotnet"
    if dotnet_home.exists():
        try:
            result = subprocess.run(
                [str(dotnet_home), "--list-runtimes"],
                capture_output=True, text=True, timeout=10
            )
            if "Microsoft.NETCore.App 9." in result.stdout:
                return str(dotnet_home)
        except Exception:
            pass

    sys_dotnet = shutil.which("dotnet")
    if sys_dotnet:
        try:
            result = subprocess.run(
                [sys_dotnet, "--list-runtimes"],
                capture_output=True, text=True, timeout=10
            )
            if "Microsoft.NETCore.App 9." in result.stdout:
                return sys_dotnet
        except Exception:
            pass

    return None


def ensure_dotnet_9(print_fn=print) -> bool:
    path = get_dotnet_path()
    if path:
        print_fn(Fore.GREEN + f".NET 9 found: {path}" + Style.RESET_ALL)
        return True
    print_fn(Fore.YELLOW + ".NET 9 not found. Attempting auto-install..." + Style.RESET_ALL)
    success = install_dotnet_9_linux(print_fn)
    if success:
        path = get_dotnet_path()
        if path:
            print_fn(Fore.GREEN + f".NET 9 installed: {path}" + Style.RESET_ALL)
            return True
    print_fn(Fore.RED + ".NET 9 installation failed. Please install manually:" + Style.RESET_ALL)
    print_fn("  curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 9.0 --runtime dotnet")
    return False


def install_dotnet_9_linux(print_fn=print) -> bool:
    script_path = Path(tempfile.gettempdir()) / "dotnet-install.sh"
    try:
        import httpx
        print_fn("Downloading dotnet-install.sh...")
        resp = httpx.get(
            "https://dot.net/v1/dotnet-install.sh",
            follow_redirects=True,
            timeout=60,
        )
        resp.raise_for_status()
        script_path.write_bytes(resp.content)
    except Exception as e:
        print_fn(Fore.RED + f"Failed to download dotnet-install.sh: {e}" + Style.RESET_ALL)
        return False

    try:
        script_path.chmod(0o755)
        env = os.environ.copy()
        env["DOTNET_ROOT"] = str(Path.home() / ".dotnet")
        print_fn("Installing .NET 9 runtime (this may take a minute)...")
        proc = subprocess.Popen(
            [str(script_path), "--channel", "9.0", "--runtime", "dotnet"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print_fn(line)
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        print_fn(Fore.RED + f"dotnet-install.sh failed: {e}" + Style.RESET_ALL)
        return False
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass
