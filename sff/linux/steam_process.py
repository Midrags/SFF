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

"""
Steam process management for Linux.

Provides kill_steam() and start_steam() with SLSteam injection support.
Before killing Steam, the running process's /proc/maps is scanned to cache
the live on-disk paths of SLSteam.so and library-inject.so so they can be
re-injected on the next Steam launch.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from colorama import Fore, Style

logger = logging.getLogger(__name__)

# Cached live paths read from /proc/{pid}/maps before the last kill
_slssteam_so_path_cache: str | None = None
_library_inject_so_path_cache: str | None = None

# Default locations where SLSteam installs its .so files
_DEFAULT_SLSSTEAM_PATHS = [
    str(Path.home() / ".local" / "share" / "SLSsteam" / "SLSsteam.so"),
    str(Path.home() / ".var" / "app" / "com.valvesoftware.Steam" /
        ".local" / "share" / "SLSsteam" / "SLSsteam.so"),
]
_DEFAULT_LIBRARY_INJECT_PATHS = [
    str(Path.home() / ".local" / "share" / "SLSsteam" / "library-inject.so"),
    str(Path.home() / ".var" / "app" / "com.valvesoftware.Steam" /
        ".local" / "share" / "SLSsteam" / "library-inject.so"),
]


def kill_steam(print_fn=print) -> bool:
    """Kill the running Steam process.

    On Linux, reads /proc/{pid}/maps first to cache the live on-disk paths
    of SLSteam.so and library-inject.so so start_steam() can re-inject them.

    Returns True if Steam was found and killed, False otherwise.
    """
    global _slssteam_so_path_cache, _library_inject_so_path_cache

    if sys.platform != "linux":
        print_fn(Fore.YELLOW + "kill_steam() is only supported on Linux." + Style.RESET_ALL)
        return False

    try:
        import psutil
    except ImportError:
        print_fn(Fore.RED + "psutil is not installed — cannot detect Steam process." + Style.RESET_ALL)
        return False

    # Reset caches before scanning
    _slssteam_so_path_cache = None
    _library_inject_so_path_cache = None

    steam_proc = next(
        (p for p in psutil.process_iter(["pid", "name"])
         if p.info["name"].lower() == "steam"),
        None,
    )

    if not steam_proc:
        print_fn(Fore.YELLOW + "Steam process not found (may already be stopped)." + Style.RESET_ALL)
        return False

    # Scan /proc/{pid}/maps to find live .so paths before killing
    maps_file = f"/proc/{steam_proc.pid}/maps"
    try:
        with open(maps_file, "r") as f:
            for line in f:
                if "SLSsteam.so" in line:
                    parts = line.split()
                    if len(parts) > 5 and os.path.exists(parts[-1]):
                        _slssteam_so_path_cache = parts[-1]
                        logger.info(f"Cached SLSsteam.so path from maps: {_slssteam_so_path_cache}")
                elif "library-inject.so" in line or "libSLS-library-inject.so" in line:
                    parts = line.split()
                    if len(parts) > 5 and os.path.exists(parts[-1]):
                        _library_inject_so_path_cache = parts[-1]
                        logger.info(f"Cached library-inject.so path from maps: {_library_inject_so_path_cache}")
    except PermissionError:
        logger.warning(f"Permission denied reading {maps_file} — .so paths not cached.")
    except Exception as e:
        logger.warning(f"Could not read {maps_file}: {e}")

    try:
        steam_proc.kill()
        steam_proc.wait(timeout=5)
        print_fn(Fore.GREEN + f"Steam process killed (PID {steam_proc.pid})." + Style.RESET_ALL)
        return True
    except Exception as e:
        print_fn(Fore.RED + f"Failed to kill Steam: {e}" + Style.RESET_ALL)
        logger.error(f"kill_steam error: {e}", exc_info=True)
        return False


def start_steam(print_fn=print) -> str:
    """Start Steam on Linux, injecting SLSteam if available.

    Lookup order for SLSteam.so / library-inject.so:
      1. Paths cached by kill_steam() from /proc/maps (most reliable)
      2. Default installation paths (~/.local/share/SLSteam/, Flatpak)

    Returns one of:
      "SUCCESS"        — Steam launched successfully
      "FAILED"         — Could not launch Steam
      "NEEDS_USER_PATH"— SLSteam files not found at any known location
    """
    if sys.platform != "linux":
        print_fn(Fore.YELLOW + "start_steam() is only supported on Linux." + Style.RESET_ALL)
        return "FAILED"

    global _slssteam_so_path_cache, _library_inject_so_path_cache

    # Resolve SLSteam.so path
    slssteam_path = _slssteam_so_path_cache
    if not slssteam_path or not os.path.exists(slssteam_path):
        for candidate in _DEFAULT_SLSSTEAM_PATHS:
            if os.path.exists(candidate):
                slssteam_path = candidate
                logger.info(f"Found SLSteam.so at default path: {slssteam_path}")
                break

    # Resolve library-inject.so path
    library_inject_path = _library_inject_so_path_cache
    if not library_inject_path or not os.path.exists(library_inject_path):
        for candidate in _DEFAULT_LIBRARY_INJECT_PATHS:
            if os.path.exists(candidate):
                library_inject_path = candidate
                logger.info(f"Found library-inject.so at default path: {library_inject_path}")
                break

    if slssteam_path and library_inject_path:
        result = start_steam_with_slssteam(slssteam_path, library_inject_path, print_fn)
        if result == "SUCCESS":
            # Clear caches after a successful launch
            _slssteam_so_path_cache = None
            _library_inject_so_path_cache = None
        return result
    else:
        missing = []
        if not slssteam_path:
            missing.append("SLSteam.so")
        if not library_inject_path:
            missing.append("library-inject.so")
        print_fn(Fore.YELLOW + f"SLSteam libraries not found: {', '.join(missing)}" + Style.RESET_ALL)
        print_fn(Fore.YELLOW + "Starting Steam without SLSteam injection." + Style.RESET_ALL)

        # Fall back to plain steam launch
        try:
            subprocess.Popen(["steam"])
            print_fn(Fore.GREEN + "Steam started (without SLSteam)." + Style.RESET_ALL)
            return "SUCCESS"
        except FileNotFoundError:
            print_fn(Fore.RED + "steam command not found in PATH." + Style.RESET_ALL)
            return "FAILED"
        except Exception as e:
            print_fn(Fore.RED + f"Failed to start Steam: {e}" + Style.RESET_ALL)
            return "FAILED"


def start_steam_with_slssteam(
    slssteam_path: str,
    library_inject_path: str,
    print_fn=print,
) -> str:
    """Start Steam with SLSteam injection via LD_AUDIT.

    Both .so files must exist. Sets LD_AUDIT=library-inject.so:SLSteam.so
    and launches the `steam` command.

    Returns "SUCCESS", "FAILED", or "NEEDS_USER_PATH".
    """
    if sys.platform != "linux":
        return "FAILED"

    if not slssteam_path or not os.path.exists(slssteam_path):
        print_fn(Fore.RED + f"SLSteam.so not found: {slssteam_path}" + Style.RESET_ALL)
        return "NEEDS_USER_PATH"

    if not library_inject_path or not os.path.exists(library_inject_path):
        print_fn(Fore.RED + f"library-inject.so not found: {library_inject_path}" + Style.RESET_ALL)
        return "NEEDS_USER_PATH"

    try:
        env = os.environ.copy()
        env["LD_AUDIT"] = f"{library_inject_path}:{slssteam_path}"
        logger.info(f"Starting Steam with LD_AUDIT={env['LD_AUDIT']}")
        subprocess.Popen(["steam"], env=env)
        print_fn(Fore.GREEN + "Steam started with SLSteam injection." + Style.RESET_ALL)
        return "SUCCESS"
    except FileNotFoundError:
        print_fn(Fore.RED + "steam command not found in PATH." + Style.RESET_ALL)
        return "FAILED"
    except Exception as e:
        print_fn(Fore.RED + f"Failed to start Steam with SLSteam: {e}" + Style.RESET_ALL)
        logger.error(f"start_steam_with_slssteam error: {e}", exc_info=True)
        return "FAILED"
