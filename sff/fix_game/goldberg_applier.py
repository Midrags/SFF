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
Goldberg DLL applier — replaces steam_api DLLs with Goldberg emulator.

Two modes:
- Regular: replace steam_api.dll / steam_api64.dll with Goldberg versions,
  generate steam_interfaces.txt from original DLL exports
- ColdClient: deploy steamclient.dll/64.dll + loader, or use ColdLoader DLL
  (from https://github.com/denuvosanctuary/coldloader)

Mirrors Solus GoldbergApplier.cs
"""

import os
import re
import sys
import stat
import struct
import shutil
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# interface version patterns to scan for in steam_api DLLs
# these are the strings that Goldberg needs in steam_interfaces.txt
INTERFACE_PATTERNS = [
    b"SteamClient",
    b"SteamGameServer",
    b"SteamGameServerStats",
    b"SteamUser",
    b"SteamFriends",
    b"SteamUtils",
    b"SteamMatchMaking",
    b"SteamMatchMakingServers",
    b"SteamUserStats",
    b"SteamGameServerStats",
    b"SteamApps",
    b"SteamNetworking",
    b"SteamRemoteStorage",
    b"SteamScreenshots",
    b"SteamHTTP",
    b"SteamController",
    b"SteamUGC",
    b"SteamAppList",
    b"SteamMusic",
    b"SteamMusicRemote",
    b"SteamHTMLSurface",
    b"SteamInventory",
    b"SteamVideo",
    b"SteamParentalSettings",
    b"SteamInput",
    b"SteamParties",
    b"SteamRemotePlay",
    b"SteamNetworkingMessages",
    b"SteamNetworkingSockets",
    b"SteamNetworkingUtils",
    b"SteamGameSearch",
    b"SteamTimeline",
]

# full regex pattern for interface version strings like "SteamUser021"
INTERFACE_REGEX = re.compile(
    rb'((?:' + b'|'.join(INTERFACE_PATTERNS) + rb')\d{3})',
)

# exe skip patterns for main exe detection
# games often ship launchers / helpers that are LARGER than the actual game exe;
# they must be excluded so find_main_exe() picks the real game binary.
EXE_SKIP = [
    "unins", "setup", "install", "redist", "crash", "report",
    "update", "patch", "vc_", "dotnet", "directx", "dxsetup",
    "steamclient_loader", "UnityCrash",
    # launchers / helpers / tools that can be larger than the game exe:
    "launcher", "helper", "tool", "config", "benchmark", "editor",
    "prerequisite", "prereq", "physx", "vcredist", "uplay", "easyanticheat",
    "battleye", "anticheat", "game_shipping",
]


class GoldbergApplier:
    """
    Applies Goldberg emulator DLLs to a game directory.

    Regular mode: replaces steam_api.dll / steam_api64.dll
    ColdClient Loader mode: deploys steamclient DLLs + loader + generates ini
    ColdLoader DLL mode: deploys coldloader.dll + proxy DLL (no exe needed)
    """

    def __init__(self, goldberg_cache_dir):
        self.cache_dir = goldberg_cache_dir

    # --- detection ---

    @staticmethod
    def detect_steam_api(game_dir):
        """
        Find all steam_api DLLs in the game directory.
        Returns (has_32bit, has_64bit, list_of_paths)
        """
        game_path = Path(game_dir)
        has_32 = False
        has_64 = False
        paths = []
        for dll in game_path.rglob("steam_api.dll"):
            has_32 = True
            paths.append(str(dll))
        for dll in game_path.rglob("steam_api64.dll"):
            has_64 = True
            paths.append(str(dll))
        return has_32, has_64, paths

    @staticmethod
    def is_exe_64bit(exe_path):
        """
        Check if an executable is 64-bit by reading the PE header.
        Reads MZ header → PE offset → machine type.
        """
        try:
            with open(exe_path, "rb") as f:
                # MZ header check
                if f.read(2) != b"MZ":
                    return False
                # PE offset at 0x3C
                f.seek(0x3C)
                pe_offset = struct.unpack("<I", f.read(4))[0]
                # PE signature
                f.seek(pe_offset)
                if f.read(4) != b"PE\x00\x00":
                    return False
                # Machine type (2 bytes after PE sig)
                machine = struct.unpack("<H", f.read(2))[0]
                # 0x8664 = AMD64, 0xAA64 = ARM64
                return machine in (0x8664, 0xAA64)
        except Exception:
            return False

    @staticmethod
    def detect_game_bitness(game_dir, main_exe = None):
        """
        Detect whether the game is 64-bit using multiple signals, in order:
        1. steam_api64.dll present in the game dir  → definitively 64-bit
           (the game ships this DLL only when targeting x64)
        2. steam_api.dll present but no steam_api64.dll  → definitively 32-bit
        3. PE header of the provided main_exe (or largest found exe)
        4. Default  → True (64-bit) — safer choice; most modern games are x64
        Never crashes: every path has a fallback.
        """
        game_path = Path(game_dir)
        # --- Signal 1 & 2: steam_api DLL presence (most reliable) ---
        has_api64 = (game_path / "steam_api64.dll").exists()
        if not has_api64:
            # also check one level of subdirectories (some games nest the exe)
            for p in game_path.iterdir():
                if p.is_dir() and (p / "steam_api64.dll").exists():
                    has_api64 = True
                    break
        has_api32 = (game_path / "steam_api.dll").exists()
        if not has_api32:
            for p in game_path.iterdir():
                if p.is_dir() and (p / "steam_api.dll").exists():
                    has_api32 = True
                    break
        if has_api64:
            return True   # steam_api64.dll present → x64
        if has_api32:     # only steam_api.dll, no 64-bit variant → x86
            return False
        # --- Signal 3: PE header ---
        exe = main_exe or GoldbergApplier.find_main_exe(game_dir)
        if exe:
            try:
                result = GoldbergApplier.is_exe_64bit(exe)
                return result
            except Exception:
                pass
        # --- Signal 4: default to 64-bit ---
        logger.warning(
            "detect_game_bitness: could not determine arch for %s — defaulting to 64-bit",
            game_dir,
        )
        return True

    @staticmethod
    def find_main_exe(game_dir):
        """
        Find the main game executable (largest .exe, excluding known non-game files).
        """
        game_path = Path(game_dir)
        best_path = None
        best_size = 0
        for exe in game_path.rglob("*.exe"):
            name_lower = exe.name.lower()
            if any(skip in name_lower for skip in EXE_SKIP):
                continue
            try:
                size = exe.stat().st_size
                if size > best_size:
                    best_size = size
                    best_path = str(exe)
            except OSError:
                continue
        return best_path

    # --- interface scanning ---

    @staticmethod
    def scan_interfaces(dll_path):
        """
        Scan a steam_api DLL for interface version strings.
        Returns a list like ["SteamUser021", "SteamFriends017", ...]
        """
        try:
            data = Path(dll_path).read_bytes()
            matches = set()
            for match in INTERFACE_REGEX.finditer(data):
                iface = match.group(1).decode("ascii", errors="ignore")
                matches.add(iface)
            return sorted(matches)
        except Exception as e:
            logger.warning("Failed to scan interfaces in %s: %s", dll_path, e)
            return []

    def generate_interfaces_file(self, dll_path, settings_dir):
        """
        Scan a steam_api DLL and write steam_interfaces.txt
        to the steam_settings directory.
        """
        interfaces = self.scan_interfaces(dll_path)
        if interfaces:
            out_path = Path(settings_dir) / "steam_interfaces.txt"
            out_path.write_text("\n".join(interfaces) + "\n", encoding="utf-8")
            logger.info("Wrote %d interfaces to %s", len(interfaces), out_path)

    # --- regular mode ---

    def apply(self, game_dir, log_func=None):
        """
        Apply Goldberg in regular mode — replace steam_api DLLs.
        Returns (success, message)
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        has_32, has_64, dll_paths = self.detect_steam_api(game_dir)
        if not has_32 and not has_64:
            return False, "No steam_api DLLs found in game directory"
        replaced = 0
        settings_dir = Path(game_dir) / "steam_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        for dll_path in dll_paths:
            dll_name = Path(dll_path).name.lower()
            # determine which cached Goldberg DLL to use
            if dll_name == "steam_api.dll":
                src = self.cache_dir / "steam_api.dll"
            elif dll_name == "steam_api64.dll":
                src = self.cache_dir / "steam_api64.dll"
            else:
                continue
            if not src.exists():
                log(f"Cached {src.name} not found — run Goldberg update first")
                continue
            target = Path(dll_path)
            # scan interfaces BEFORE replacing
            self.generate_interfaces_file(str(target), str(settings_dir))
            # backup original
            backup = target.with_suffix(target.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(target, backup)
                log(f"Backed up {target.name} → {backup.name}")
            # replace with Goldberg
            shutil.copy2(src, target)
            replaced += 1
            log(f"✓ Replaced {target.name} with Goldberg")
        if replaced > 0:
            return True, f"Applied Goldberg to {replaced} DLL(s)"
        return False, "No DLLs were replaced"

    # --- Linux native mode ---

    @staticmethod
    def detect_steam_api_linux(game_dir):
        """
        Find libsteam_api.so files in the game directory (native Linux games).
        Returns list of paths found.
        """
        game_path = Path(game_dir)
        paths = []
        for so in game_path.rglob("libsteam_api.so"):
            paths.append(str(so))
        return paths

    @staticmethod
    def find_main_binary_linux(game_dir):
        """
        Find the main Linux game binary — largest ELF executable (no extension,
        has execute permission, not a known helper).
        Falls back to largest file with execute bit set.
        """
        SKIP = [
            "unins", "setup", "install", "crash", "report",
            "update", "patch", "helper", "tool",
        ]
        game_path = Path(game_dir)
        best_path = None
        best_size = 0
        for f in game_path.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix in (".so", ".py", ".sh", ".txt", ".ini", ".json", ".cfg", ".pak"):
                continue
            name_lower = f.name.lower()
            if any(skip in name_lower for skip in SKIP):
                continue
            # check execute bit
            try:
                mode = f.stat().st_mode
                if not (mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
                    continue
                size = f.stat().st_size
                # verify ELF magic
                with open(f, "rb") as fh:
                    magic = fh.read(4)
                if magic != b"\x7fELF":
                    continue
                if size > best_size:
                    best_size = size
                    best_path = str(f)
            except (OSError, PermissionError):
                continue
        return best_path

    def apply_linux(self, game_dir, log_func=None):
        """
        Apply Goldberg in native Linux mode — replace libsteam_api.so.
        Returns (success, message)
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        so_paths = self.detect_steam_api_linux(game_dir)
        if not so_paths:
            return False, "No libsteam_api.so found in game directory"
        src = self.cache_dir / "libsteam_api.so"
        if not src.exists():
            return False, "Cached libsteam_api.so not found — run Goldberg update first"
        replaced = 0
        settings_dir = Path(game_dir) / "steam_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        for so_path in so_paths:
            target = Path(so_path)
            # scan interfaces from the original .so before replacing
            self.generate_interfaces_file(str(target), str(settings_dir))
            # backup original
            backup = target.with_suffix(target.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(target, backup)
                log(f"Backed up {target.name} \u2192 {backup.name}")
            # replace with Goldberg
            shutil.copy2(src, target)
            replaced += 1
            log(f"\u2713 Replaced {target.name} with Goldberg")
        if replaced > 0:
            return True, f"Applied Goldberg (.so) to {replaced} file(s)"
        return False, "No libsteam_api.so files were replaced"

    # --- ColdClient loader mode (Solus method) ---

    def apply_coldclient_loader(self, game_dir, app_id, log_func=None):
        """
        Apply Goldberg in ColdClient loader mode.
        Deploys steamclient DLLs + steamclient_loader exe + generates
        ColdClientLoader.ini with the correct exe and paths.
        Also auto-reverts any previous regular GBE DLL swap before applying.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        game_path = Path(game_dir)
        # --- auto-revert previous regular GBE install if present ---
        # Regular mode renames steam_api.dll → steam_api.dll.bak and puts Goldberg in its place.
        # ColdClient needs the original steam_api.dll to remain untouched, so restore it first.
        bak_files = list(game_path.rglob("steam_api*.dll.bak"))
        if bak_files:
            log("Detected previous regular GBE install — restoring originals before ColdClient...")
            for bak in bak_files:
                original = bak.with_suffix("")  # removes .bak → steam_api.dll / steam_api64.dll
                try:
                    shutil.copy2(bak, original)
                    bak.unlink()
                    log(f"✓ Restored {original.name} from backup")
                except Exception as e:
                    log(f"Warning: could not restore {original.name}: {e}")
        # --- generate steam_interfaces.txt from the original steam_api DLL ---
        for dll_name in ["steam_api64.dll", "steam_api.dll"]:
            dll_path = game_path / dll_name
            if dll_path.exists():
                settings_dir = game_path / "steam_settings"
                settings_dir.mkdir(parents=True, exist_ok=True)
                self.generate_interfaces_file(str(dll_path), str(settings_dir))
                log(f"✓ Scanned interfaces from {dll_name}")
                break
        # find main exe
        main_exe = self.find_main_exe(game_dir)
        if not main_exe:
            return False, "Could not find main game executable"
        is_64 = self.detect_game_bitness(game_dir, main_exe)
        log(f"Main exe: {Path(main_exe).name} ({'64-bit' if is_64 else '32-bit'})")
        # deploy BOTH steamclient DLLs — ColdClientLoader always writes both paths
        # to the registry and the game exe may hard-require either regardless of bitness
        for sc_name in ("steamclient.dll", "steamclient64.dll"):
            sc_src = self.cache_dir / sc_name
            if sc_src.exists():
                shutil.copy2(sc_src, game_path / sc_name)
                log(f"✓ Deployed {sc_name}")
            else:
                log(f"Warning: {sc_name} not found in cache")
        # deploy loader
        loader_name = "steamclient_loader_x64.exe" if is_64 else "steamclient_loader_x32.exe"
        src = self.cache_dir / loader_name
        if src.exists():
            shutil.copy2(src, game_path / loader_name)
            log(f"✓ Deployed {loader_name}")
        else:
            return False, f"{loader_name} not found in cache"
        # deploy extra DLLs into extra_dlls/ subfolder — loader injects everything there
        extra_dir = game_path / "extra_dlls"
        extra_dir.mkdir(exist_ok=True)
        # steamclient_extra DLL (gbe_fork companion — arch-correct)
        extra_name = "steamclient_extra_x64.dll" if is_64 else "steamclient_extra_x32.dll"
        extra_src = self.cache_dir / extra_name
        if extra_src.exists():
            shutil.copy2(extra_src, extra_dir / extra_name)
            log(f"\u2713 Deployed {extra_name} \u2192 extra_dlls/")
        else:
            log(f"Warning: {extra_name} not found in cache")
        # steamstub avoider DLL — bypasses SteamStub protection at runtime
        stub_name = "steamstub_x64.dll" if is_64 else "steamstub_x32.dll"
        stub_src = self._find_tool(stub_name)
        if stub_src:
            shutil.copy2(stub_src, extra_dir / stub_name)
            log(f"\u2713 Deployed {stub_name} \u2192 extra_dlls/ (SteamStub bypass)")
        # prefer .unpacked.exe if present (Steamless output — SteamStub removed)
        main_exe_path = Path(main_exe)
        unpacked_path = main_exe_path.parent / (main_exe_path.name + ".unpacked.exe")
        if unpacked_path.exists():
            exe_rel = os.path.relpath(str(unpacked_path), game_dir)
            log(f"\u2713 Using unpacked exe: {unpacked_path.name}")
        else:
            exe_rel = os.path.relpath(main_exe, game_dir)
        # generate ColdClientLoader.ini — both DLL entries must always be present;
        # the loader writes both paths to the Windows registry unconditionally,
        # and some game exes hard-require steamclient.dll regardless of their bitness
        ini_content = f"""[SteamClient]
# path to game exe, absolute or relative to the loader
Exe={exe_rel}
# empty means the folder of the exe
ExeRunDir=
# any additional args to pass to the game
ExeCommandLine=
# Steam App ID for this game
AppId={app_id}
# path to the steamclient dlls — both must be set
SteamClientDll=steamclient.dll
SteamClient64Dll=steamclient64.dll

[Injection]
ForceInjectSteamClient=0
ForceInjectGameOverlayRenderer=0
DllsToInjectFolder=extra_dlls
IgnoreInjectionError=1
IgnoreLoaderArchDifference=0

[Persistence]
Mode=0

[Debug]
ResumeByDebugger=0
"""

        (game_path / "ColdClientLoader.ini").write_text(ini_content, encoding="utf-8")
        log("\u2713 Generated ColdClientLoader.ini")
        # deploy GameOverlayRenderer — needed if overlay is enabled in configs
        gor_name = "GameOverlayRenderer64.dll" if is_64 else "GameOverlayRenderer.dll"
        gor_src = self._find_tool(gor_name)
        if gor_src:
            shutil.copy2(gor_src, game_path / gor_name)
            log(f"\u2713 Deployed {gor_name} (overlay support)")
        # create desktop shortcut for the loader
        game_name = main_exe_path.stem
        self._create_desktop_shortcut(game_name, game_path / loader_name, game_path, main_exe_path, log)
        return True, f"ColdClient loader deployed \u2014 run {loader_name} to start the game"

    # --- ColdLoader DLL mode (denuvosanctuary method) ---

    def apply_coldloader_dll(self, game_dir, app_id, log_func=None):
        """
        Apply ColdLoader DLL mode — uses coldloader.dll + a DLL proxy
        to load GBE ColdClient without needing an external exe.
        Requires coldloader.dll and coldloader-proxy (version.dll) to be
        available in the cache or third_party.
        See: https://github.com/denuvosanctuary/coldloader
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        game_path = Path(game_dir)
        # detect bitness first so we can pick the right arch-specific bundled DLL
        main_exe = self.find_main_exe(game_dir)
        is_64 = self.detect_game_bitness(game_dir, main_exe)
        if main_exe:
            log(f"Main exe: {Path(main_exe).name} ({'64-bit' if is_64 else '32-bit'})")
        else:
            log(f"No main exe found — bitness detected from steam_api DLLs: {'64-bit' if is_64 else '32-bit'}")
        arch = "x64" if is_64 else "x86"
        coldloader_dll = (self._find_tool(f"coldloader_{arch}.dll")
                          or self._find_tool("coldloader.dll"))
        proxy_dll      = (self._find_tool(f"version_{arch}.dll")
                          or self._find_tool("version.dll")
                          or self._find_tool("winmm.dll"))
        if not coldloader_dll:
            return False, "coldloader.dll not found in third_party/coldloader/"
        # deploy coldloader.dll
        shutil.copy2(coldloader_dll, game_path / "coldloader.dll")
        log("✓ Deployed coldloader.dll")
        # deploy proxy DLL — strip arch suffix so game sees version.dll / winmm.dll
        if proxy_dll:
            raw_name = Path(proxy_dll).name
            proxy_name = raw_name.replace("_x64", "").replace("_x86", "")
            shutil.copy2(proxy_dll, game_path / proxy_name)
            log(f"✓ Deployed {proxy_name} (DLL proxy)")
        # deploy steamclient DLL
        sc_name = "steamclient64.dll" if is_64 else "steamclient.dll"
        src = self.cache_dir / sc_name
        if src.exists():
            shutil.copy2(src, game_path / sc_name)
            log(f"✓ Deployed {sc_name}")
        # generate coldloader.ini
        ini_content = f"""[ColdLoader]
AppId={app_id}
SteamClient={'steamclient64.dll' if is_64 else 'steamclient.dll'}
"""
        (game_path / "coldloader.ini").write_text(ini_content, encoding="utf-8")
        log("✓ Generated coldloader.ini")
        # make sure steam_settings exists with steam_appid.txt
        settings_dir = game_path / "steam_settings"
        settings_dir.mkdir(exist_ok=True)
        (settings_dir / "steam_appid.txt").write_text(str(app_id), encoding="utf-8")
        return True, "ColdLoader DLL deployed — game loads Goldberg automatically via DLL proxy"

    @staticmethod
    def _create_desktop_shortcut(
        game_name: str,
        target_exe: Path,
        working_dir: Path,
        icon_source: Path,
        log,
    ):
        """
        Create a shortcut on the Desktop for the given target exe.
        Windows: .lnk via PowerShell WScript.Shell.
        Linux: .desktop file in ~/Desktop.
        """
        if sys.platform != "win32":
            try:
                desktop = Path.home() / "Desktop"
                desktop.mkdir(exist_ok=True)
                safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in game_name)
                desktop_file = desktop / f"{safe_name}.desktop"
                content = (
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    f"Name={game_name}\n"
                    f"Exec={target_exe}\n"
                    f"Path={working_dir}\n"
                    "Terminal=false\n"
                )
                desktop_file.write_text(content, encoding="utf-8")
                desktop_file.chmod(0o755)
                log(f"\u2713 Created desktop shortcut: {desktop_file.name}")
            except Exception as e:
                log(f"Warning: could not create desktop shortcut ({e})")
            return
        try:
            desktop = Path.home() / "Desktop"
            if not desktop.exists():
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
                )
                desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
                winreg.CloseKey(key)
            safe_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in game_name)
            lnk_path = desktop / f"{safe_name}.lnk"
            icon_loc = str(icon_source) if icon_source.exists() else str(target_exe)
            ps_script = (
                f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{lnk_path}");'
                f'$s.TargetPath="{target_exe}";'
                f'$s.WorkingDirectory="{working_dir}";'
                f'$s.IconLocation="{icon_loc},0";'
                f'$s.Save()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                check=True,
                capture_output=True,
                timeout=10,
            )
            log(f"\u2713 Created desktop shortcut: {lnk_path.name}")
        except Exception as e:
            log(f"Warning: could not create desktop shortcut ({e})")

    def _find_tool(self, filename):
        """search cache dir and third_party for a file"""
        tp = Path(__file__).parent.parent.parent / "third_party"
        candidates = [
            self.cache_dir / filename,
            self.cache_dir / "coldloader" / filename,
            tp / filename,
            tp / "gbe_fork" / filename,
            tp / "coldloader" / filename,
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    # --- restore ---

    def restore(self, game_dir, log_func=None):
        """
        Undo all Goldberg changes — restore .bak files,
        delete steam_settings/, steam_appid.txt, ColdClient files.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        game_path = Path(game_dir)
        restored = 0
        # restore .bak files (steam_api.dll.bak → steam_api.dll)
        for bak in game_path.rglob("*.bak"):
            if bak.name.endswith(".steamstub.bak"):
                continue  # handled by SteamStubUnpacker.restore
            original = bak.with_suffix("")
            try:
                shutil.copy2(bak, original)
                bak.unlink()
                restored += 1
                log(f"Restored {original.name}")
            except Exception as e:
                log(f"Failed to restore {original.name}: {e}")
        # delete steam_settings/
        settings_dir = game_path / "steam_settings"
        if settings_dir.exists():
            shutil.rmtree(settings_dir, ignore_errors=True)
            log("Deleted steam_settings/")
        # delete steam_appid.txt
        appid_file = game_path / "steam_appid.txt"
        if appid_file.exists():
            appid_file.unlink()
            log("Deleted steam_appid.txt")
        # delete ColdClient files
        for name in [
            "ColdClientLoader.ini", "coldloader.ini", "coldloader.dll",
            "steamclient.dll", "steamclient64.dll",
            "steamclient_loader_x32.exe", "steamclient_loader_x64.exe",
            "steamclient_extra_x32.dll", "steamclient_extra_x64.dll",
            "steam_interfaces.txt",
            "GameOverlayRenderer.dll", "GameOverlayRenderer64.dll",
        ]:
            p = game_path / name
            if p.exists():
                p.unlink()
                log(f"Deleted {name}")
        # delete extra_dlls/
        extra_dir = game_path / "extra_dlls"
        if extra_dir.exists():
            shutil.rmtree(extra_dir, ignore_errors=True)
            log("Deleted extra_dlls/")
        # delete version.dll/winmm.dll proxy (only if it's the coldloader proxy)
        for proxy in ["version.dll", "winmm.dll"]:
            p = game_path / proxy
            if p.exists():
                try:
                    # check size — real system DLLs are usually very different sizes
                    if p.stat().st_size < 500_000:
                        p.unlink()
                        log(f"Deleted {proxy} (coldloader proxy)")
                except Exception:
                    pass
        msg = f"Restored {restored} file(s)" if restored else "No backups to restore"
        log(msg)
        return True, msg
