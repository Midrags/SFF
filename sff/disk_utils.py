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

"""Safe disk enumeration.

Wraps drive-letter scanning in per-drive OSError guards and skips volumes
that Windows exposes but cannot actually read: BitLocker-locked drives,
Linux ext4/btrfs/xfs partitions, RAW/corrupt filesystems, recovery/EFI
partitions, offline disks, empty optical drives and SD readers, network
drives that have disconnected, and permission-blocked paths.

Every caller that used to iterate A-Z directly should call
iter_accessible_drives or find_steam_libraries_on_disk instead,
which handle all the edge cases and log every skip with a reason.
"""

import logging
import os
import subprocess
from pathlib import Path
from string import ascii_uppercase

logger = logging.getLogger(__name__)

# Filesystems Windows can mount and read without third-party drivers.
_READABLE_FILESYSTEMS = frozenset({None, "NTFS", "FAT32", "FAT", "exFAT", "ReFS"})


def _try_psutil_fstype(mount: str) -> str | None:
    try:
        import psutil
        for p in psutil.disk_partitions(all=False):
            if p.mountpoint.rstrip("\\/").upper() == mount.rstrip("\\/").upper():
                return p.fstype or ""
    except Exception:
        pass
    return None


def _drive_readable(path: Path) -> bool:
    """Return True if the drive root can be accessed at all."""
    try:
        return os.access(str(path), os.R_OK)
    except OSError:
        return False


def _check_bitlocker_locked(drive_letter: str) -> bool:
    """Best-effort check: returns True if the volume appears BitLocker-locked."""
    try:
        out = subprocess.check_output(
            ["manage-bde", "-status", f"{drive_letter}:"],
            shell=True, stderr=subprocess.DEVNULL, timeout=8,
        ).decode("utf-8", errors="replace")
        if "Lock Status" in out and "Locked" in out:
            return True
    except Exception:
        pass
    return False


class DriveStatus:
    OK = "ok"
    MISSING = "missing"
    UNREADABLE = "unreadable"
    BITLOCKER_LOCKED = "bitlocker_locked"
    UNSUPPORTED_FS = "unsupported_fs"
    NO_MEDIA = "no_media"


def classify_drive(drive_letter: str) -> tuple[str, str]:
    """Return (status, message) for one drive letter.

    status is one of the DriveStatus constants.
    """
    drive_path = Path(f"{drive_letter}:/")
    try:
        exists = drive_path.exists()
    except OSError:
        return DriveStatus.UNREADABLE, "PermissionError / inaccessible drive"
    if not exists:
        return DriveStatus.MISSING, "Drive letter not present"
    if not _drive_readable(drive_path):
        if _check_bitlocker_locked(drive_letter):
            return DriveStatus.BITLOCKER_LOCKED, "BitLocker locked"
        return DriveStatus.UNREADABLE, "Access denied (permissions / locked volume)"
    fstype = _try_psutil_fstype(str(drive_path))
    if fstype is not None and fstype not in _READABLE_FILESYSTEMS:
        return DriveStatus.UNSUPPORTED_FS, f"Unsupported filesystem ({fstype or 'unknown'})"
    return DriveStatus.OK, fstype or "ok"


def iter_accessible_drives() -> list[Path]:
    """Return a list of drive root Paths that are readable and have a
    supported filesystem (NTFS, FAT32, exFAT, ReFS).

    Drives that are inaccessible, BitLocker-locked, Linux-formatted,
    or missing are logged and skipped.
    """
    if os.name != "nt":
        return []
    drives: list[Path] = []
    skipped: list[tuple[str, str]] = []
    for dl in ascii_uppercase:
        status, reason = classify_drive(dl)
        if status == DriveStatus.OK:
            drives.append(Path(f"{dl}:/"))
        elif status not in (DriveStatus.MISSING,):
            skipped.append((f"{dl}:", reason))
    if skipped:
        logger.debug("Skipped %d inaccessible drive(s): %s",
            len(skipped),
            ", ".join(f"{dl} ({r})" for dl, r in skipped),
        )
    return drives


_STEAMLIB_CANDIDATE_SUBDIRS = (
    "SteamLibrary", "Steam", "Games/Steam",
    "Program Files (x86)/Steam", "Program Files/Steam",
)


def find_steam_libraries_on_disk() -> list[Path]:
    """Walk every accessible drive looking for Steam library folders.

    Safe: never throws on bad drives. Logs every skip reason.
    Returns deduplicated list of Paths that have a steamapps subdir.
    """
    from sff.storage.vdf import get_steam_libs
    found: list[Path] = []
    seen = set()
    for drive in iter_accessible_drives():
        for subdir in _STEAMLIB_CANDIDATE_SUBDIRS:
            candidate = drive / subdir
            try:
                steamapps = candidate / "steamapps"
                if steamapps.exists() and candidate not in seen:
                    found.append(candidate)
                    seen.add(candidate)
            except OSError:
                continue
    return found
