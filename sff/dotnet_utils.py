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
from pathlib import Path

from colorama import Fore, Style


def _get_user_dotnet_root() -> str:
    if sys.platform == "win32":
        local_app_data = os.environ.get(
            "LOCALAPPDATA", os.path.expandvars("%LocalAppData%")
        )
        return os.path.join(local_app_data, "Microsoft", "dotnet")
    else:
        return os.path.expanduser("~/.dotnet")


def _get_user_dotnet_path() -> str:
    if sys.platform == "win32":
        return os.path.join(_get_user_dotnet_root(), "dotnet.exe")
    else:
        return os.path.join(_get_user_dotnet_root(), "dotnet")


def _probe_dotnet(dotnet_exe: str) -> bool:
    try:
        run_kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": 10,
        }
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        env = os.environ.copy()
        env.setdefault("DOTNET_ROOT", os.path.dirname(dotnet_exe))
        run_kwargs["env"] = env

        result = subprocess.run([dotnet_exe, "--list-runtimes"], **run_kwargs)
        return "Microsoft.NETCore.App 9." in result.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def get_dotnet_path() -> str | None:
    candidates = []

    user_dotnet = _get_user_dotnet_path()
    if os.path.isfile(user_dotnet):
        candidates.append(user_dotnet)

    sys_dotnet = shutil.which("dotnet")
    if sys_dotnet:
        candidates.append(sys_dotnet)

    seen = set()
    for c in candidates:
        norm = os.path.normcase(os.path.realpath(c))
        if norm in seen:
            continue
        seen.add(norm)
        if _probe_dotnet(c):
            return c

    return None


def _install_dotnet_9_windows(print_fn=print) -> bool:
    import ssl
    import urllib.request

    dotnet_root = _get_user_dotnet_root()
    script_url = "https://dot.net/v1/dotnet-install.ps1"
    script_path = None

    for attempt in range(2):
        try:
            print_fn(f"Installing .NET 9 runtime (attempt {attempt + 1}/2)...")

            env = os.environ.copy()
            env["DOTNET_ROOT"] = dotnet_root

            with tempfile.NamedTemporaryFile(
                suffix=".ps1", delete=False, mode="wb"
            ) as tmp_script:
                script_path = tmp_script.name
                print_fn("Downloading dotnet-install.ps1...")
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(script_url, context=ctx, timeout=30) as resp:
                    tmp_script.write(resp.read())

            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", script_path,
                "-Channel", "9.0",
                "-Runtime", "dotnet",
                "-InstallDir", dotnet_root,
            ]

            run_kwargs = {
                "capture_output": True,
                "text": True,
                "timeout": 300,
                "env": env,
            }
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(cmd, **run_kwargs)
            if result.returncode == 0:
                dotnet_exe = os.path.join(dotnet_root, "dotnet.exe")
                if os.path.exists(dotnet_exe):
                    print_fn(Fore.GREEN + ".NET 9 installed successfully." + Style.RESET_ALL)
                    return True

        except subprocess.TimeoutExpired:
            print_fn(Fore.RED + "Timeout while installing .NET 9." + Style.RESET_ALL)
        except (OSError, subprocess.SubprocessError) as e:
            print_fn(Fore.RED + f"Error installing .NET 9: {e}" + Style.RESET_ALL)
        finally:
            if script_path and os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except OSError:
                    pass

    return False


def _install_dotnet_9_linux(print_fn=print) -> bool:
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


def ensure_dotnet_9(print_fn=print) -> bool:
    path = get_dotnet_path()
    if path:
        print_fn(Fore.GREEN + f".NET 9 found: {path}" + Style.RESET_ALL)
        return True

    print_fn(Fore.YELLOW + ".NET 9 not found. Attempting auto-install..." + Style.RESET_ALL)

    if sys.platform == "win32":
        success = _install_dotnet_9_windows(print_fn)
    else:
        success = _install_dotnet_9_linux(print_fn)

    if success:
        path = get_dotnet_path()
        if path:
            dotnet_root = os.path.dirname(path)
            os.environ["DOTNET_ROOT"] = dotnet_root
            current_path = os.environ.get("PATH", "")
            if dotnet_root not in current_path.split(os.pathsep):
                os.environ["PATH"] = dotnet_root + os.pathsep + current_path
            print_fn(Fore.GREEN + f".NET 9 installed: {path}" + Style.RESET_ALL)
            return True

    print_fn(Fore.RED + ".NET 9 installation failed. Please install manually:" + Style.RESET_ALL)
    if sys.platform == "win32":
        print_fn("  Download from: https://dotnet.microsoft.com/download/dotnet/9.0")
    else:
        print_fn("  curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 9.0 --runtime dotnet")
    return False
