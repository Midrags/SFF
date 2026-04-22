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
CreamAPI v5.3.0.0 multiplayer fix applier.

Installs bundled CreamAPI DLLs to spoof a game's AppID as 480 (Spacewar)
so online multiplayer works in offline/cracked games.

Modes:
  classic  — replaces steam_api.dll / steam_api64.dll in-place (default)
  proxy    — installs CreamAPI as winmm.dll (original DLL untouched)
  linux    — replaces libsteam_api.so for native Linux games

Bundled DLLs must be placed at:
  third_party/online_fix/windows/steam_api.dll        (x86)
  third_party/online_fix/windows/steam_api64.dll      (x64)
  third_party/online_fix/linux/x64/libsteam_api.so
  third_party/online_fix/linux/x86/libsteam_api.so
"""

import logging
import shutil
import struct
import time
from pathlib import Path

from sff.fix_game.goldberg_applier import GoldbergApplier
from sff.utils import root_folder

logger = logging.getLogger(__name__)

_ANTICHEAT_PATTERNS = {
    "EasyAntiCheat": [
        "EasyAntiCheat",
        "EasyAntiCheat_EOS.exe",
        "EasyAntiCheat_launcher.exe",
        "EACLauncher.exe",
    ],
    "BattlEye": [
        "BattlEye",
        "BEClient.dll",
        "BEClient_x64.dll",
        "BEService.exe",
    ],
}


def _copy2_retry(src: Path, dst: Path, retries: int = 8, delay: float = 0.5) -> None:
    """
    shutil.copy2 with retry logic for transient PermissionError (e.g. AV scanner).
    Retries up to `retries` times with `delay` seconds between attempts.
    """
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


class OnlineFixApplier:
    """
    Applies CreamAPI v5.3.0.0 (bundled) to a game directory
    for online multiplayer via AppID 480 (Spacewar).
    """

    BUNDLE_DIR_NAME = "online_fix"
    CONFIG_FILENAME = "cream_api.ini"
    APPID_FILE = "steam_appid.txt"
    APPID_VALUE = "480"
    BACKUP_SUFFIX_32 = "_o.dll"
    BACKUP_SUFFIX_64 = "_o.dll"
    BACKUP_NAME_32 = "steam_api_o.dll"
    BACKUP_NAME_64 = "steam_api64_o.dll"
    BACKUP_NAME_SO = "libsteam_api_o.so"
    PROXY_DLL_NAME = "winmm.dll"
    PROXY_BACKUP_NAME = "winmm_o.dll"
    PROXY_MAX_SIZE = 300 * 1024  # 300 KB — larger than this means it's not CreamAPI proxy

    # --- internal helpers ---

    def _get_bundle_dir(self) -> Path:
        return root_folder() / "third_party" / self.BUNDLE_DIR_NAME

    def _get_windows_dll(self, is_64: bool) -> Path:
        name = "steam_api64.dll" if is_64 else "steam_api.dll"
        return self._get_bundle_dir() / "windows" / name

    def _get_linux_so(self, is_64: bool) -> Path:
        arch = "x64" if is_64 else "x86"
        return self._get_bundle_dir() / "linux" / arch / "libsteam_api.so"

    @staticmethod
    def _is_elf_64bit(path: Path) -> bool:
        """
        Read ELF header to determine if a file is 64-bit.
        EI_CLASS byte at offset 4: 1 = ELFCLASS32, 2 = ELFCLASS64.
        Defaults to True (64-bit) on any error.
        """
        try:
            with open(path, "rb") as f:
                magic = f.read(4)
                if magic != b"\x7fELF":
                    return True
                ei_class_bytes = f.read(1)
                if not ei_class_bytes:
                    return True
                ei_class = struct.unpack("B", ei_class_bytes)[0]
                return ei_class == 2  # ELFCLASS64
        except Exception:
            return True

    def _generate_ini(self, mode: str, is_64: bool, platform: str) -> str:
        """
        Generate cream_api.ini content for the given mode/platform combination.

        Args:
            mode:     "classic" or "proxy"
            is_64:    True if 64-bit game
            platform: "windows" or "linux"
        """
        if platform == "linux":
            orgapi = "libsteam_api_o.so"
            orgapi64 = "libsteam_api_o.so"
            comment = "linux"
        elif mode == "proxy":
            orgapi = "steam_api.dll"
            orgapi64 = "steam_api64.dll"
            comment = "proxy"
        else:
            orgapi = self.BACKUP_NAME_32
            orgapi64 = self.BACKUP_NAME_64
            comment = "classic"

        extra_protection_line = "" if platform == "linux" else "extraprotection = false\n"

        return (
            f"; Online multiplayer fix (SpaceWar / AppID 480)"
            f" — generated by SteaMidra ({comment})\n"
            f"[steam]\n"
            f"appid = 480\n"
            f"unlockall = false\n"
            f"orgapi = {orgapi}\n"
            f"orgapi64 = {orgapi64}\n"
            f"{extra_protection_line}"
            f"forceoffline = false\n"
            f"\n"
            f"[steam_misc]\n"
            f"disableuserinterface = false\n"
            f"\n"
            f"[dlc]\n"
            f"; No DLC unlock — SpaceWar multiplayer only\n"
        )

    def _write_appid_txt(self, game_path: Path, log) -> None:
        """Write steam_appid.txt = 480 to the exe directory (with game-root fallback)."""
        main_exe = GoldbergApplier.find_main_exe(game_path)
        if main_exe:
            target_dir = Path(main_exe).parent
        else:
            target_dir = game_path
        appid_path = target_dir / self.APPID_FILE
        try:
            appid_path.write_text(self.APPID_VALUE, encoding="utf-8")
            log(f"  Wrote {self.APPID_FILE} (480) -> {target_dir.name}/")
        except Exception as e:
            log(f"  Warning: could not write {self.APPID_FILE}: {e}")

    def _write_appid_txt_linux(self, game_path: Path, log) -> None:
        """Write steam_appid.txt for Linux games (uses main binary dir if found)."""
        main_bin = GoldbergApplier.find_main_binary_linux(game_path)
        if main_bin:
            target_dir = Path(main_bin).parent
        else:
            target_dir = game_path
        appid_path = target_dir / self.APPID_FILE
        try:
            appid_path.write_text(self.APPID_VALUE, encoding="utf-8")
            log(f"  Wrote {self.APPID_FILE} (480) -> {target_dir.name}/")
        except Exception as e:
            log(f"  Warning: could not write {self.APPID_FILE}: {e}")

    # --- apply modes ---

    def _apply_classic(self, game_path: Path, log) -> "tuple[bool, str]":
        """Classic mode: replace steam_api.dll / steam_api64.dll with CreamAPI."""
        bundle_dir = self._get_bundle_dir()
        _, _, dll_paths = GoldbergApplier.detect_steam_api(game_path)
        if not dll_paths:
            return False, "No steam_api DLL found in game directory"

        replaced = 0
        for dll_str in dll_paths:
            dll_path = Path(dll_str)
            dll_name = dll_path.name.lower()
            is_64 = dll_name == "steam_api64.dll"
            dll_dir = dll_path.parent

            src = self._get_windows_dll(is_64)
            if not src.exists():
                log(f"  WARNING: Bundled CreamAPI DLL not found at {src}")
                log(f"  Copy third_party/online_fix/windows/{src.name} first")
                continue

            backup_name = self.BACKUP_NAME_64 if is_64 else self.BACKUP_NAME_32
            backup_path = dll_dir / backup_name

            if not backup_path.exists():
                _copy2_retry(dll_path, backup_path)
                log(f"  Backed up {dll_path.name} -> {backup_name}")
            else:
                log(f"  Backup already exists: {backup_name} (skipped)")

            _copy2_retry(src, dll_path)
            log(f"  Installed CreamAPI -> {dll_path.name}")

            ini_content = self._generate_ini("classic", is_64, "windows")
            ini_path = dll_dir / self.CONFIG_FILENAME
            ini_path.write_text(ini_content, encoding="utf-8")
            log(f"  Wrote {self.CONFIG_FILENAME} -> {dll_dir.name}/")

            replaced += 1

        if replaced == 0:
            return False, "No DLLs were replaced — check bundled CreamAPI files exist"

        self._write_appid_txt(game_path, log)
        return True, f"CreamAPI installed (classic) to {replaced} DLL location(s)"

    def _apply_proxy(self, game_path: Path, log) -> "tuple[bool, str]":
        """Proxy mode: install CreamAPI as winmm.dll, original DLLs untouched."""
        main_exe = GoldbergApplier.find_main_exe(game_path)
        if not main_exe:
            return False, "Could not find main game executable for proxy mode"

        exe_dir = Path(main_exe).parent
        is_64 = GoldbergApplier.detect_game_bitness(game_path, main_exe)

        src = self._get_windows_dll(is_64)
        if not src.exists():
            return False, (
                f"Bundled CreamAPI DLL not found at {src}. "
                f"Copy third_party/online_fix/windows/{src.name} first."
            )

        proxy_path = exe_dir / self.PROXY_DLL_NAME
        backup_path = exe_dir / self.PROXY_BACKUP_NAME

        if proxy_path.exists() and not backup_path.exists():
            _copy2_retry(proxy_path, backup_path)
            log(f"  Backed up {self.PROXY_DLL_NAME} -> {self.PROXY_BACKUP_NAME}")

        _copy2_retry(src, proxy_path)
        log(f"  Installed CreamAPI -> {self.PROXY_DLL_NAME}")

        ini_content = self._generate_ini("proxy", is_64, "windows")
        ini_path = exe_dir / self.CONFIG_FILENAME
        ini_path.write_text(ini_content, encoding="utf-8")
        log(f"  Wrote {self.CONFIG_FILENAME}")

        appid_path = exe_dir / self.APPID_FILE
        appid_path.write_text(self.APPID_VALUE, encoding="utf-8")
        log(f"  Wrote {self.APPID_FILE} (480)")

        return True, "CreamAPI installed in proxy mode (as winmm.dll)"

    def _apply_linux(self, game_path: Path, log) -> "tuple[bool, str]":
        """Linux mode: replace libsteam_api.so with CreamAPI .so."""
        so_paths = GoldbergApplier.detect_steam_api_linux(game_path)
        if not so_paths:
            return False, "No libsteam_api.so found in game directory"

        replaced = 0
        for so_str in so_paths:
            so_path = Path(so_str)
            so_dir = so_path.parent
            is_64 = self._is_elf_64bit(so_path)

            src = self._get_linux_so(is_64)
            if not src.exists():
                arch_label = "x64" if is_64 else "x86"
                log(f"  WARNING: Bundled Linux .so not found at {src}")
                log(f"  Copy third_party/online_fix/linux/{arch_label}/libsteam_api.so first")
                continue

            backup_path = so_dir / self.BACKUP_NAME_SO
            if not backup_path.exists():
                _copy2_retry(so_path, backup_path)
                log(f"  Backed up {so_path.name} -> {self.BACKUP_NAME_SO}")
            else:
                log(f"  Backup already exists: {self.BACKUP_NAME_SO} (skipped)")

            _copy2_retry(src, so_path)
            log(f"  Installed CreamAPI .so -> {so_path.name}")

            ini_content = self._generate_ini("classic", is_64, "linux")
            ini_path = so_dir / self.CONFIG_FILENAME
            ini_path.write_text(ini_content, encoding="utf-8")
            log(f"  Wrote {self.CONFIG_FILENAME} -> {so_dir.name}/")

            replaced += 1

        if replaced == 0:
            return False, "No .so files were replaced — check bundled CreamAPI files exist"

        self._write_appid_txt_linux(game_path, log)
        return True, f"CreamAPI installed (linux) to {replaced} .so location(s)"

    # --- public API ---

    def apply(
        self,
        game_dir,
        platform_hint: str = "windows",
        mode: str = "classic",
        log_func=None,
    ) -> "tuple[bool, str]":
        """
        Apply CreamAPI to game_dir.

        Args:
            game_dir:      Path or str to the game's root folder.
            platform_hint: "windows" or "linux".
            mode:          "classic" or "proxy" (Windows only).
            log_func:      Optional callable for progress output.

        Returns:
            (success: bool, message: str)
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        game_path = Path(game_dir)
        if not game_path.is_dir():
            return False, f"Game directory does not exist: {game_path}"

        bundle_check = self._get_bundle_dir()
        if not bundle_check.exists():
            return False, (
                f"CreamAPI bundle directory not found: {bundle_check}\n"
                f"Copy the DLLs from CreamAPI_Release_v5.3.0.0/nonlog_build/ "
                f"into third_party/online_fix/"
            )

        log(f"Applying CreamAPI multiplayer fix to: {game_path.name}")
        log(f"  Platform: {platform_hint}  |  Mode: {mode}")

        if platform_hint == "linux":
            return self._apply_linux(game_path, log)
        elif mode == "proxy":
            return self._apply_proxy(game_path, log)
        else:
            return self._apply_classic(game_path, log)

    def restore(self, game_dir, log_func=None) -> "tuple[bool, str]":
        """
        Restore original DLLs and remove all CreamAPI files from game_dir.

        Returns:
            (success: bool, message: str)
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        game_path = Path(game_dir)
        restored = 0
        errors = 0

        # 1. Classic / Linux installs: find cream_api.ini files
        for ini_path in list(game_path.rglob(self.CONFIG_FILENAME)):
            ini_dir = ini_path.parent

            # Restore Windows DLLs
            for dll_name, backup_name in [
                ("steam_api64.dll", self.BACKUP_NAME_64),
                ("steam_api.dll", self.BACKUP_NAME_32),
            ]:
                backup = ini_dir / backup_name
                if backup.exists():
                    original = ini_dir / dll_name
                    try:
                        _copy2_retry(backup, original)
                        backup.unlink()
                        log(f"  Restored {dll_name} from {backup_name}")
                        restored += 1
                    except Exception as e:
                        log(f"  ERROR restoring {dll_name}: {e}")
                        errors += 1

            # Restore Linux .so
            so_backup = ini_dir / self.BACKUP_NAME_SO
            if so_backup.exists():
                so_orig = ini_dir / "libsteam_api.so"
                try:
                    _copy2_retry(so_backup, so_orig)
                    so_backup.unlink()
                    log(f"  Restored libsteam_api.so from {self.BACKUP_NAME_SO}")
                    restored += 1
                except Exception as e:
                    log(f"  ERROR restoring libsteam_api.so: {e}")
                    errors += 1

            # Delete cream_api.ini
            try:
                ini_path.unlink()
                log(f"  Deleted {self.CONFIG_FILENAME}")
            except Exception as e:
                log(f"  ERROR deleting {self.CONFIG_FILENAME}: {e}")
                errors += 1

        # 2. Proxy installs: detect CreamAPI winmm.dll by size
        for winmm in list(game_path.rglob(self.PROXY_DLL_NAME)):
            try:
                size = winmm.stat().st_size
                if size >= self.PROXY_MAX_SIZE:
                    continue  # too large — likely a real winmm.dll
                winmm_dir = winmm.parent
                winmm.unlink()
                log(f"  Removed proxy {self.PROXY_DLL_NAME}")
                backup = winmm_dir / self.PROXY_BACKUP_NAME
                if backup.exists():
                    _copy2_retry(backup, winmm_dir / self.PROXY_DLL_NAME)
                    backup.unlink()
                    log(f"  Restored {self.PROXY_DLL_NAME} from {self.PROXY_BACKUP_NAME}")
                restored += 1
            except Exception as e:
                log(f"  ERROR during proxy restore: {e}")
                errors += 1

        # 3. Delete steam_appid.txt only if it contains "480" (our file)
        for appid_txt in list(game_path.rglob(self.APPID_FILE)):
            try:
                content = appid_txt.read_text(encoding="utf-8", errors="ignore").strip()
                if content == self.APPID_VALUE:
                    appid_txt.unlink()
                    log(f"  Deleted {self.APPID_FILE}")
            except Exception as e:
                log(f"  ERROR deleting {self.APPID_FILE}: {e}")

        if restored == 0 and errors == 0:
            return False, "Nothing to restore — no CreamAPI files found in game directory"
        if errors > 0:
            return False, f"Restored {restored} item(s) with {errors} error(s) — check log above"
        return True, f"Restored {restored} item(s) — CreamAPI removed successfully"

    def is_applied(self, game_dir) -> bool:
        """Return True if cream_api.ini exists anywhere in game_dir."""
        return any(Path(game_dir).rglob(self.CONFIG_FILENAME))

    @staticmethod
    def detect_anticheat(game_dir) -> "list[str]":
        """
        Scan game_dir for known anti-cheat systems.

        Returns:
            List of detected anti-cheat names (e.g. ["EasyAntiCheat", "BattlEye"]).
        """
        game_path = Path(game_dir)
        detected = []
        for ac_name, patterns in _ANTICHEAT_PATTERNS.items():
            for pattern in patterns:
                if list(game_path.rglob(pattern)):
                    detected.append(ac_name)
                    break
        return detected
