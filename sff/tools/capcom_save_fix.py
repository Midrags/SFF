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
Capcom game save fix — patches SteamTools DLLs to fix broken saves.

SteamTools messes with Steam Cloud requests, which causes Capcom games
(and some others) to fail to create save files. This tool patches the
SteamTools core DLL and its encrypted payload to disable the broken
cloud behavior while keeping SteamTools working for everything else.

Based on STFixer v0.7.1 by Selectively11
(https://github.com/Selectively11/STFixer)

The patching:
1. Core DLL (xinput1_4.dll / dwmapi.dll):
   - Patch #1: "call download_func" → "mov eax, 1" (skip re-download)
   - Patch #2: "jz hash_check" → "jmp hash_check" (skip hash compare)
2. Payload cache (encrypted blob in appcache/httpcache/):
   - AES-256-CBC decrypt → zlib decompress
   - Patch cloud rewrite jz → jmp (disable cloud app ID swap)
   - Patch proxy appid load → xor ecx,ecx (zero out proxy ID)
   - Patch Spacewar write → NOP (don't write fake app ID)
   - Patch activation flag → set to 1 (force activation)
   - Patch retry skip → always skip (don't retry broken behavior)
   - Recompress → re-encrypt → write
"""

import os
import struct
import shutil
import hashlib
import logging
import zlib
from pathlib import Path
from typing import Optional
from enum import Enum
from io import BytesIO

try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    try:
        from Cryptodome.Cipher import AES
        HAS_CRYPTO = True
    except ImportError:
        HAS_CRYPTO = False

logger = logging.getLogger(__name__)

# SteamTools hijack DLL candidates (one of these will be the core DLL)
HIJACK_CANDIDATES = ["xinput1_4.dll", "dwmapi.dll"]

# AES key used by SteamTools to encrypt its payload cache
AES_KEY = bytes([
    0x31, 0x4C, 0x20, 0x86, 0x15, 0x05, 0x74, 0xE1,
    0x5C, 0xF1, 0x1D, 0x1B, 0xC1, 0x71, 0x25, 0x1A,
    0x47, 0x08, 0x6C, 0x00, 0x26, 0x93, 0x55, 0xCD,
    0x51, 0xC9, 0x3A, 0x42, 0x3C, 0x14, 0x02, 0x94,
])

# known correct hashes for SteamTools DLLs
XINPUT_HASH = "ddb1f0909c7092f06890674f90b5d4f1198724b05b4bf1e656b4063897340243"
DWMAPI_HASH = "1ce49ed63af004ad37a4d2921a5659a17001c4c0026d6245fcc0d543e9c265d0"


class PatchState(Enum):
    NOT_INSTALLED = "not_installed"
    UNPATCHED = "unpatched"
    PATCHED = "patched"
    PARTIALLY_PATCHED = "partially_patched"
    UNKNOWN_VERSION = "unknown_version"
    PAYLOAD_CORRUPT = "payload_corrupt"
    ERROR = "error"


class PatchResult:
    def __init__(self):
        self.succeeded = False
        self.dll_patched = False
        self.cache_patched = False
        self.error = ""

    def fail(self, error: str) -> "PatchResult":
        self.succeeded = False
        self.error = error
        return self


class CapcomSaveFix:
    """
    Patches SteamTools to fix the Capcom game save issue.
    
    SteamTools hijacks Steam Cloud APIs and rewrites the App ID to
    the Screenshots app ID (760), which causes Capcom games to fail
    to create or load save files. This tool patches that behavior out.
    
    Usage:
        fixer = CapcomSaveFix()
        state = fixer.get_patch_state("/path/to/Steam")
        if state == PatchState.UNPATCHED:
            result = fixer.apply("/path/to/Steam")
    """

    def __init__(self):
        self._cached_payload = None
        self._cached_payload_size = 0

    @staticmethod
    def detect_steam_path() -> Optional[str]:
        """auto-detect Steam installation path"""
        candidates = []

        # try registry
        try:
            import winreg
            for key_path in [
                r"SOFTWARE\Valve\Steam",
                r"SOFTWARE\WOW6432Node\Valve\Steam",
            ]:
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    try:
                        with winreg.OpenKey(hive, key_path) as key:
                            val, _ = winreg.QueryValueEx(key, "InstallPath")
                            if val and os.path.isdir(val):
                                candidates.append(val)
                    except (FileNotFoundError, OSError):
                        continue
        except ImportError:
            pass

        # common paths
        for path in [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
        ]:
            if os.path.isdir(path):
                candidates.append(path)

        # prefer paths that have SteamTools installed
        for path in candidates:
            for dll in HIJACK_CANDIDATES:
                if os.path.exists(os.path.join(path, dll)):
                    return path

        return candidates[0] if candidates else None

    def _find_core_dll(self, steam_path: str) -> Optional[str]:
        """find the SteamTools core DLL by checking for the AES key in binary content"""
        for name in HIJACK_CANDIDATES:
            dll_path = os.path.join(steam_path, name)
            if not os.path.exists(dll_path):
                continue
            try:
                data = self._read_shared(dll_path)
                if self._scan_for_bytes(data, AES_KEY) >= 0:
                    return name
            except (IOError, PermissionError):
                continue
        return None

    def _find_cache_path(self, steam_path: str) -> Optional[str]:
        """find the SteamTools payload cache file"""
        cache_dir = os.path.join(steam_path, "appcache", "httpcache", "3b")
        if not os.path.isdir(cache_dir):
            return None

        # the cache file is a 16-char hex filename with no extension
        for fname in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, fname)
            if os.path.isfile(fpath) and len(fname) == 16:
                try:
                    int(fname, 16)
                    return fpath
                except ValueError:
                    continue
        return None

    def get_patch_state(self, steam_path: str) -> PatchState:
        """
        Check the current patch state of SteamTools.
        """
        if not HAS_CRYPTO:
            return PatchState.ERROR

        core_dll = self._find_core_dll(steam_path)
        if core_dll is None:
            return PatchState.NOT_INSTALLED

        cache_path = self._find_cache_path(steam_path)
        if cache_path is None:
            return PatchState.NOT_INSTALLED

        # decrypt and check payload
        try:
            payload = self._get_decrypted_payload(cache_path)
            if payload is None:
                return PatchState.PAYLOAD_CORRUPT
        except Exception:
            return PatchState.PAYLOAD_CORRUPT

        # check if patches are applied by scanning the payload
        # look for our patched bytes vs original bytes at known locations
        # this is a simplified check — the full version uses offset resolution
        try:
            dll_path = os.path.join(steam_path, core_dll)
            dll_data = self._read_shared(dll_path)

            # core patch #1: check if E8 (call) was replaced with B8 (mov eax,1)
            core_p1 = self._find_core_patch1(dll_data)
            if core_p1 < 0:
                return PatchState.UNKNOWN_VERSION

            # check if it's patched (B8 01 00 00 00) or original (E8 xx xx xx xx)
            core_patched = dll_data[core_p1] == 0xB8

            # check payload cloud patch
            payload_p1 = self._find_payload_patch1(payload)
            payload_patched = payload_p1 >= 0 and payload[payload_p1] == 0x90

            if core_patched and payload_patched:
                return PatchState.PATCHED
            elif not core_patched and not payload_patched:
                return PatchState.UNPATCHED
            else:
                return PatchState.PARTIALLY_PATCHED

        except Exception as e:
            logger.warning("Patch state check failed: %s", e)
            return PatchState.ERROR

    def apply(self, steam_path: str, log_func=None) -> PatchResult:
        """
        Apply the Capcom save fix patches.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        result = PatchResult()

        if not HAS_CRYPTO:
            return result.fail("pycryptodome not installed (pip install pycryptodome)")

        try:
            # find core DLL
            core_name = self._find_core_dll(steam_path)
            if not core_name:
                return result.fail("SteamTools core DLL not found — is SteamTools installed?")

            dll_path = os.path.join(steam_path, core_name)
            dll_data = bytearray(self._read_shared(dll_path))

            log(f"Patching {core_name}...")

            # find and apply core patches
            p1_offset = self._find_core_patch1(dll_data)
            if p1_offset < 0:
                return result.fail(f"Could not find patch location in {core_name}")

            p2_offset = self._find_core_patch2(dll_data, p1_offset)
            if p2_offset < 0:
                return result.fail(f"Could not find hash check in {core_name}")

            # apply core patch #1: call → mov eax, 1
            core_p1_applied = False
            if dll_data[p1_offset] == 0xE8:  # call
                dll_data[p1_offset:p1_offset+5] = b"\xB8\x01\x00\x00\x00"  # mov eax, 1
                core_p1_applied = True
                log("  Core patch #1: disabled re-download call")
            elif dll_data[p1_offset] == 0xB8:
                log("  Core patch #1: already applied")

            # apply core patch #2: jz → jmp
            core_p2_applied = False
            if dll_data[p2_offset] == 0x74:  # jz
                dll_data[p2_offset] = 0xEB  # jmp
                core_p2_applied = True
                log("  Core patch #2: skip hash check")
            elif dll_data[p2_offset] == 0xEB:
                log("  Core patch #2: already applied")

            # backup and write DLL
            self._backup(dll_path)
            if core_p1_applied or core_p2_applied:
                Path(dll_path).write_bytes(bytes(dll_data))
                log(f"  ✓ {core_name} patched")
            result.dll_patched = True

            # patch payload cache
            cache_path = self._find_cache_path(steam_path)
            if cache_path:
                log("Patching payload cache...")
                payload_result = self._patch_payload(cache_path, log)
                if payload_result:
                    result.cache_patched = True
                else:
                    log("  Warning: payload patching failed — may need fresh payload")
            else:
                log("Payload cache not found — run offline setup first or wait for SteamTools")

            result.succeeded = True
            log("Done! Restart Steam to apply changes.")

        except PermissionError:
            return result.fail("Access denied — close Steam first or run as administrator")
        except Exception as e:
            return result.fail(f"Unexpected error: {e}")

        return result

    def restore(self, steam_path: str, log_func=None) -> PatchResult:
        """
        Restore original SteamTools files from backups.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        result = PatchResult()
        restored = 0

        for name in HIJACK_CANDIDATES:
            dll_path = os.path.join(steam_path, name)
            bak_path = dll_path + ".bak"
            if os.path.exists(bak_path):
                try:
                    shutil.copy2(bak_path, dll_path)
                    os.unlink(bak_path)
                    restored += 1
                    log(f"Restored {name}")
                except Exception as e:
                    log(f"Failed to restore {name}: {e}")

        cache_path = self._find_cache_path(steam_path)
        if cache_path:
            bak_path = cache_path + ".bak"
            if os.path.exists(bak_path):
                try:
                    shutil.copy2(bak_path, cache_path)
                    os.unlink(bak_path)
                    restored += 1
                    log("Restored payload cache")
                except Exception as e:
                    log(f"Failed to restore cache: {e}")

        if restored > 0:
            result.succeeded = True
            log(f"Restored {restored} file(s). Restart Steam.")
        else:
            result.succeeded = True
            log("Nothing to restore (no backups found)")

        return result

    # --- internal helpers ---

    @staticmethod
    def _read_shared(path: str) -> bytes:
        """read a file with shared access (so Steam can still have it open)"""
        with open(path, "rb") as f:
            return f.read()

    @staticmethod
    def _backup(path: str):
        """create .bak backup if one doesn't exist"""
        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)

    @staticmethod
    def _scan_for_bytes(data: bytes, needle: bytes, start: int = 0) -> int:
        """find needle in data, returns offset or -1"""
        return data.find(needle, start)

    def _get_decrypted_payload(self, cache_path: str) -> Optional[bytes]:
        """decrypt and decompress the SteamTools payload cache"""
        raw = self._read_shared(cache_path)
        if len(raw) < 32:
            return None

        iv = raw[:16]
        ciphertext = raw[16:]

        # AES-256-CBC decrypt
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)

        # remove PKCS7 padding
        pad_len = decrypted[-1]
        if pad_len > 16:
            pad_len = 0
        if pad_len > 0:
            decrypted = decrypted[:-pad_len]

        # skip 4-byte header, then zlib decompress
        try:
            payload = zlib.decompress(decrypted[4:])
            return payload
        except zlib.error:
            # try without skipping header
            try:
                payload = zlib.decompress(decrypted)
                return payload
            except zlib.error:
                return None

    def _reencrypt_and_write(self, cache_path: str, payload: bytes, iv: bytes):
        """compress, encrypt, and write the payload back"""
        # compress
        compressed = zlib.compress(payload)

        # add 4-byte header (original size, little-endian)
        header = struct.pack("<I", len(payload))
        plaintext = header + compressed

        # pad to 16-byte boundary (PKCS7)
        pad_len = 16 - (len(plaintext) % 16)
        plaintext += bytes([pad_len] * pad_len)

        # encrypt
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(plaintext)

        # write: IV + ciphertext
        Path(cache_path).write_bytes(iv + ciphertext)

    def _patch_payload(self, cache_path: str, log) -> bool:
        """decrypt, patch, and re-encrypt the payload cache"""
        raw = self._read_shared(cache_path)
        if len(raw) < 32:
            log("  Payload too small")
            return False

        iv = raw[:16]
        ciphertext = raw[16:]

        # decrypt
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)

        # remove padding
        pad_len = decrypted[-1]
        if pad_len > 16:
            pad_len = 0
        decrypted = decrypted[:-pad_len] if pad_len > 0 else decrypted

        # decompress
        try:
            payload = bytearray(zlib.decompress(decrypted[4:]))
        except zlib.error:
            try:
                payload = bytearray(zlib.decompress(decrypted))
            except zlib.error:
                log("  Failed to decompress payload")
                return False

        log(f"  Payload: {len(payload)} bytes")
        patches_applied = 0

        # payload patch #1: cloud rewrite jz → jmp
        p1 = self._find_payload_patch1(payload)
        if p1 >= 0 and payload[p1] == 0x0F and payload[p1+1] == 0x84:
            payload[p1] = 0x90  # NOP
            payload[p1+1] = 0xE9  # JMP
            patches_applied += 1
            log("  Payload patch #1: disabled cloud rewrite")

        # payload patch #2: proxy appid → xor ecx,ecx
        p2 = self._find_payload_patch2(payload)
        if p2 >= 0 and payload[p2] == 0x8B and payload[p2+1] == 0x0D:
            payload[p2:p2+6] = b"\x31\xC9\x90\x90\x90\x90"
            patches_applied += 1
            log("  Payload patch #2: zeroed proxy appid")

        # payload patch #3: Spacewar write → NOP
        p3 = self._find_payload_patch3(payload)
        if p3 >= 0 and payload[p3] == 0x89:
            payload[p3:p3+6] = b"\x90" * 6
            patches_applied += 1
            log("  Payload patch #3: disabled Spacewar write")

        # payload patch #4: activation flag → force 1
        p4 = self._find_payload_patch4(payload)
        if p4 >= 0 and payload[p4+6] == 0x00:
            payload[p4+6] = 0x01
            patches_applied += 1
            log("  Payload patch #4: forced activation flag")

        # payload patch #5: retry skip
        p5 = self._find_payload_patch5(payload)
        if p5 >= 0 and payload[p5] == 0x75:
            payload[p5] = 0xEB  # jmp (always skip)
            patches_applied += 1
            log("  Payload patch #5: skip retry loop")

        if patches_applied == 0:
            log("  Payload: already patched or unknown version")
            return True

        # backup, then re-encrypt and write
        self._backup(cache_path)
        self._reencrypt_and_write(cache_path, bytes(payload), iv)
        log(f"  ✓ Applied {patches_applied} payload patches")
        return True

    # --- signature scanning (ported from STFixer Signatures.cs) ---

    @staticmethod
    def _find_core_patch1(data: bytes) -> int:
        """find core patch #1: E8 call with negative target, followed by 85 C0 0F 84"""
        pattern = bytes([0xE8])
        check_after = bytes([0x85, 0xC0, 0x0F, 0x84])
        pos = 0
        while pos < len(data) - 9:
            idx = data.find(pattern, pos)
            if idx < 0:
                break
            if idx + 9 < len(data):
                if data[idx+5:idx+9] == check_after:
                    # check that call target is negative (download func is earlier)
                    rel = struct.unpack_from("<i", data, idx + 1)[0]
                    if rel < 0:
                        return idx
            pos = idx + 1
        return -1

    @staticmethod
    def _find_core_patch2(data: bytes, start: int = 0) -> int:
        """find core patch #2: 85 C0 74 xx 33 FF (hash compare fall-through)"""
        end = len(data)
        for i in range(start, end - 6):
            if (data[i] == 0x85 and data[i+1] == 0xC0 and
                    (data[i+2] == 0x74 or data[i+2] == 0xEB) and
                    data[i+4] == 0x33 and data[i+5] == 0xFF):
                return i + 2
        return -1

    @staticmethod
    def _find_payload_patch1(data: bytes) -> int:
        """cloud rewrite jz: 85 C0 0F 85 ?? ?? 00 00 45 85 FF [0F 84|90 E9]"""
        for i in range(len(data) - 17):
            if (data[i] == 0x85 and data[i+1] == 0xC0 and
                    data[i+2] == 0x0F and data[i+3] == 0x85 and
                    data[i+6] == 0x00 and data[i+7] == 0x00 and
                    data[i+8] == 0x45 and data[i+9] == 0x85 and data[i+10] == 0xFF):
                if (data[i+11] == 0x0F and data[i+12] == 0x84) or \
                   (data[i+11] == 0x90 and data[i+12] == 0xE9):
                    return i + 11
        return -1

    @staticmethod
    def _find_payload_patch2(data: bytes, start: int = 0) -> int:
        """proxy appid load: [8B 0D|31 C9] ?? ?? ?? ?? 48 8D 14 3E"""
        tail = bytes([0x48, 0x8D, 0x14, 0x3E])
        for i in range(start, len(data) - 10):
            if data[i+6:i+10] == tail:
                if (data[i] == 0x8B and data[i+1] == 0x0D) or \
                   (data[i] == 0x31 and data[i+1] == 0xC9):
                    return i
        return -1

    @staticmethod
    def _find_payload_patch3(data: bytes) -> int:
        """Spacewar 480 constant anchor: C7 40 09 E0 01 00 00, then next 89 3D or 6x NOP"""
        spacewar = bytes([0xC7, 0x40, 0x09, 0xE0, 0x01, 0x00, 0x00])
        anchor = data.find(spacewar)
        if anchor < 0:
            return -1

        search_start = anchor + len(spacewar)
        search_end = min(search_start + 30, len(data) - 6)
        for i in range(search_start, search_end):
            if data[i] == 0x89 and data[i+1] == 0x3D:
                return i
            if all(data[i+j] == 0x90 for j in range(6)):
                return i
        return -1

    @staticmethod
    def _find_payload_patch4(data: bytes) -> int:
        """activation flag: paired C6 05 xx xx FE FF 01/00 with E9 bridge"""
        for i in range(len(data) - 24):
            if data[i] != 0xC6 or data[i+1] != 0x05:
                continue
            if data[i+4] != 0xFE or data[i+5] != 0xFF:
                continue
            if data[i+6] != 0x01:
                continue

            b = i + 7
            if b + 17 > len(data):
                continue
            if data[b] != 0xE9:
                continue
            if data[b+5] != 0xE9:
                continue

            fail_off = b + 10
            if data[fail_off] != 0xC6 or data[fail_off+1] != 0x05:
                continue
            if data[fail_off+4] != 0xFE or data[fail_off+5] != 0xFF:
                continue

            return fail_off
        return -1

    @staticmethod
    def _find_payload_patch5(data: bytes) -> int:
        """retry skip: E8 call then 48 85 F6 75/EB with backwards jmp in skip range"""
        for i in range(len(data) - 12):
            if data[i] != 0xE8:
                continue
            if data[i+5] != 0x48 or data[i+6] != 0x85 or data[i+7] != 0xF6:
                continue
            if data[i+8] != 0x75 and data[i+8] != 0xEB:
                continue

            skip_dist = data[i+9]
            after_skip = i + 10 + skip_dist
            if after_skip > len(data):
                continue

            # look for backwards jmp in skip range
            has_loop = False
            for j in range(i + 10, min(after_skip, len(data) - 5)):
                if data[j] == 0xE9:
                    rel = struct.unpack_from("<i", data, j + 1)[0]
                    if rel < 0:
                        has_loop = True
                        break
            if not has_loop:
                continue

            return i + 8
        return -1
