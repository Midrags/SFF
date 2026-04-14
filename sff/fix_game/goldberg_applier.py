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
import struct
import shutil
import logging
from pathlib import Path
from typing import Optional

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
EXE_SKIP = [
    "unins", "setup", "install", "redist", "crash", "report",
    "update", "patch", "vc_", "dotnet", "directx", "dxsetup",
    "steamclient_loader", "UnityCrash",
]


class GoldbergApplier:
    """
    Applies Goldberg emulator DLLs to a game directory.
    
    Regular mode: replaces steam_api.dll / steam_api64.dll
    ColdClient Loader mode: deploys steamclient DLLs + loader + generates ini
    ColdLoader DLL mode: deploys coldloader.dll + proxy DLL (no exe needed)
    """

    def __init__(self, goldberg_cache_dir: Path):
        self.cache_dir = goldberg_cache_dir

    # --- detection ---

    @staticmethod
    def detect_steam_api(game_dir: str) -> tuple[bool, bool, list]:
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
    def is_exe_64bit(exe_path: str) -> bool:
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
    def find_main_exe(game_dir: str) -> Optional[str]:
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
    def scan_interfaces(dll_path: str) -> list[str]:
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

    def generate_interfaces_file(self, dll_path: str, settings_dir: str):
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

    def apply(self, game_dir: str, log_func=None) -> tuple[bool, str]:
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

    # --- ColdClient loader mode (Solus method) ---

    def apply_coldclient_loader(self, game_dir: str, app_id: int, log_func=None) -> tuple[bool, str]:
        """
        Apply Goldberg in ColdClient loader mode.
        
        Deploys steamclient DLLs + steamclient_loader exe + generates
        ColdClientLoader.ini with the correct exe and paths.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        game_path = Path(game_dir)

        # find main exe
        main_exe = self.find_main_exe(game_dir)
        if not main_exe:
            return False, "Could not find main game executable"

        is_64 = self.is_exe_64bit(main_exe)
        log(f"Main exe: {Path(main_exe).name} ({'64-bit' if is_64 else '32-bit'})")

        # deploy steamclient DLLs
        for dll_name in ["steamclient.dll", "steamclient64.dll"]:
            src = self.cache_dir / dll_name
            if src.exists():
                shutil.copy2(src, game_path / dll_name)
                log(f"✓ Deployed {dll_name}")

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

        # generate ColdClientLoader.ini (DllsToInjectFolder is the correct gbe_fork format)
        ini_content = f"""[SteamClient]
Exe={exe_rel}
ExeRunDir=
ExeCommandLine=
AppId={app_id}
SteamClientDll=steamclient.dll
SteamClient64Dll=steamclient64.dll
DllsToInjectFolder=extra_dlls
"""

        (game_path / "ColdClientLoader.ini").write_text(ini_content, encoding="utf-8")
        log("✓ Generated ColdClientLoader.ini")

        return True, f"ColdClient loader deployed — run {loader_name} to start the game"

    # --- ColdLoader DLL mode (denuvosanctuary method) ---

    def apply_coldloader_dll(self, game_dir: str, app_id: int, log_func=None) -> tuple[bool, str]:
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
        is_64 = True
        main_exe = self.find_main_exe(game_dir)
        if main_exe:
            is_64 = self.is_exe_64bit(main_exe)
            log(f"Main exe: {Path(main_exe).name} ({'64-bit' if is_64 else '32-bit'})")

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

    def _find_tool(self, filename: str) -> Optional[str]:
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

    def restore(self, game_dir: str, log_func=None) -> tuple[bool, str]:
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
