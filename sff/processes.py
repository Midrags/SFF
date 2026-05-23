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


from functools import partial

import logging

import os

import subprocess

import threading

import time

from pathlib import Path


import psutil


from sff.extras import Konami, replace_boot_image

from sff.prompts import prompt_confirm


logger = logging.getLogger(__name__)


def is_proc_running(process_name: str):

    for proc in psutil.process_iter(["pid", "name"]):

        try:
            if process_name.lower() == proc.info["name"].lower():
                return True
        except psutil.Error:
            pass

    return False


def is_running_elevated() -> bool:
    """Return True when the current process has admin/elevated rights on Windows."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def launch_steam_unelevated(steam_exe: Path, cwd: Path | None = None) -> tuple[bool, str]:
    """Launch Steam without inheriting our elevation.

    Steam's manifest is `asInvoker`. When SteaMidra runs elevated and tries to
    spawn steam.exe directly, Windows refuses with WinError 740 because an
    elevated parent cannot drop integrity for a child. We work around it by
    asking explorer.exe (always medium integrity) to launch Steam.

    Returns (success, message).
    """
    steam_exe = Path(steam_exe)
    if not steam_exe.exists():
        return False, f"steam.exe not found at {steam_exe}"

    cwd_str = str(cwd) if cwd else str(steam_exe.parent)

    # Non-elevated path — direct Popen works.
    if not is_running_elevated():
        try:
            subprocess.Popen(
                [str(steam_exe)],
                cwd=cwd_str,
                creationflags=subprocess.CREATE_NO_WINDOW
                if os.name == "nt" else 0,
            )
            return True, "Steam launched"
        except Exception as exc:
            logger.warning("direct Popen launch failed: %s", exc)
            # fall through to the elevated workaround

    # Elevated path — bounce through explorer.exe to drop integrity.
    explorer = Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"
    if explorer.exists():
        try:
            subprocess.Popen(
                [str(explorer), str(steam_exe)],
                cwd=cwd_str,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return True, "Steam launched via explorer"
        except Exception as exc:
            logger.warning("explorer.exe launch failed: %s", exc)

    # Last resort — ShellExecute (still inherits elevation, but at least
    # gives Steam a fighting chance and a clearer error if it refuses).
    try:
        import ctypes
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "open", str(steam_exe), None, cwd_str, 1
        )
        if int(ret) > 32:
            return True, "Steam launched via ShellExecute"
        return False, (
            f"ShellExecute failed (code {ret}). Close SteaMidra "
            "and start Steam from the Start Menu."
        )
    except Exception as exc:
        return False, f"All launch strategies failed: {exc}"


class SteamProcess:

    def __init__(self, steam_path: Path, applist_folder: Path = None):

        self.steam_path = steam_path
        self.injector_dir = applist_folder.parent if applist_folder else None
        self.exe_name = "steam.exe"
        self.wait_time = 3

    def kill(self):

        print(" ", end="", flush=True)
        # Use taskkill - works without elevation and is very reliable
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", self.exe_name],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # taskkill returns 0 if successful, 128 if process not found
            if result.returncode == 0:
                return  # Success
            elif result.returncode == 128:
                # Process not running, that's fine
                return
        except subprocess.TimeoutExpired:
            print("(timeout, trying psutil)...", end="", flush=True)
        except Exception as e:
            logger.debug(f"taskkill failed: {e}")
        # Fallback: Use psutil
        try:
            killed = False
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() == self.exe_name.lower():
                        proc.kill()
                        killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if killed:
                return
        except Exception as e:
            logger.debug(f"psutil failed: {e}")
        pass

    def resolve_injector_path(self):

        target = self.steam_path / self.exe_name
        if target.exists():
            return str(target.resolve())
        return None

    def prompt_launch_or_restart(self):

        watcher = Konami(on_success=partial(replace_boot_image, self.injector_dir))
        t = threading.Thread(target=watcher.listen, daemon=True)
        t.start()
        do_start = prompt_confirm("Would like me to restart/start Steam for you?")
        watcher.stop()
        if not do_start:
            return False
        if is_proc_running(self.exe_name):
            print("Killing Steam...", flush=True, end="")
            self.kill()
            wait_start = time.time()
            max_wait = 15  # 15 seconds max
            while is_proc_running(self.exe_name):
                if time.time() - wait_start > max_wait:
                    print("\nSteam is taking too long to close.")
                    if prompt_confirm("Force close Steam?"):
                        subprocess.run(
                            ["taskkill", "/F", "/IM", self.exe_name],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        time.sleep(2)
                        if is_proc_running(self.exe_name):
                            print("Could not close Steam. Please close it manually.")
                        break
                    else:
                        print("Skipping Steam restart.")
                        return False
                time.sleep(0.5)
            if not is_proc_running(self.exe_name):
                print(" Done!")
        injector = self.resolve_injector_path()
        if injector is None:
            print("Could not find any matching executables. Launch it yourself.")
            return False
        print("Launching Steam...")
        ok, msg = launch_steam_unelevated(Path(injector), self.steam_path)
        if ok:
            print("Steam launched successfully!")
            return True
        print(f"\nError launching Steam: {msg}")
        print("Please launch Steam manually from your Start Menu or Desktop.")
        return False
