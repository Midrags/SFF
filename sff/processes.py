from functools import partial
import logging
import subprocess
import threading
import time
from pathlib import Path

import psutil

from sff.fun import Konami, replace_boot_image
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


class SteamProcess:
    def __init__(self, steam_path: Path, applist_folder: Path):
        self.steam_path = steam_path
        self.injector_dir = applist_folder.parent
        self.exe_name = "steam.exe"
        self.wait_time = 3

    def kill(self):
        """Kill Steam process using taskkill (most reliable method)"""
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
        
        # If we get here, Steam might not be running (which is fine)
        # or we couldn't kill it (user will need to do it manually)
        pass

    def resolve_injector_path(self):
        candidates = ["DLLInjector.exe", "steam.exe"]
        matches = [
            x for x in map(lambda x: (self.injector_dir / x), candidates) if x.exists()
        ]
        if len(matches) == 1:
            return str(matches[0].resolve())
        if len(matches) == 0:
            return None
        print(f"The following were found: {', '.join(x.name for x in matches)}")
        if prompt_confirm("Is your GreenLuma installation in Normal Mode right now?"):
            return str(matches[0].resolve())
        renamed_path = matches[0].parent / (matches[0].name + ".backup")
        matches[0].rename(renamed_path)
        print(
            "You must be in stealth mode then. "
            f"You shouldn't leave {candidates[0]} in that folder! I've renamed it "
            f"to {renamed_path.name} for you."
        )
        return str(matches[1].resolve())

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
            
            # Wait for Steam to close (with timeout)
            wait_start = time.time()
            max_wait = 15  # 15 seconds max
            
            while is_proc_running(self.exe_name):
                if time.time() - wait_start > max_wait:
                    print("\nSteam is taking too long to close.")
                    if prompt_confirm("Force close Steam?"):
                        # Force kill with taskkill
                        subprocess.run(
                            ["taskkill", "/F", "/IM", self.exe_name],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        time.sleep(2)
                        if is_proc_running(self.exe_name):
                            print("Could not close Steam. Please close it manually.")
                            input("Press Enter after closing Steam...")
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
        
        print("Launching Steam with administrator privileges...")
        try:
            import ctypes
            import sys
            
            # Use ShellExecute with 'runas' verb to run as administrator
            # This will show the UAC prompt if needed
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,                    # hwnd
                "runas",                 # operation (run as admin)
                injector,                # file to execute
                None,                    # parameters
                str(self.steam_path),    # working directory
                1                        # SW_SHOWNORMAL (show window normally)
            )
            
            # ShellExecute returns a value > 32 on success
            if ret > 32:
                print("Steam launched successfully!")
                return True
            else:
                # Error codes: https://docs.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecutew
                error_messages = {
                    0: "Out of memory or resources",
                    2: "File not found",
                    3: "Path not found",
                    5: "Access denied",
                    8: "Out of memory",
                    26: "Sharing violation",
                    27: "File association incomplete or invalid",
                    28: "DDE timeout",
                    29: "DDE transaction failed",
                    30: "DDE busy",
                    31: "No file association",
                    32: "DLL not found"
                }
                error_msg = error_messages.get(ret, f"Unknown error (code {ret})")
                print(f"\nFailed to launch Steam: {error_msg}")
                print("Please launch Steam manually from your Start Menu or Desktop.")
                input("Press Enter after launching Steam...")
                return False
                
        except Exception as e:
            print(f"\nError launching Steam: {e}")
            print("Please launch Steam manually from your Start Menu or Desktop.")
            input("Press Enter after launching Steam...")
            return False
