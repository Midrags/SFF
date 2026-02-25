"""
Steam patch via two DLLs (xinput1_4.dll, hid.dll).

Places them in the Steam directory so the client reads config\\stplug-in
and related folders that SMD prepares, without replacing Steam.exe.
Windows only. DLLs must be placed in the steam_patch folder.
"""

import logging
import shutil
import sys
from pathlib import Path
from typing import Optional

from sff.utils import root_folder

logger = logging.getLogger(__name__)

DLL_NAMES = ("xinput1_4.dll", "hid.dll")


def get_steam_patch_dir() -> Path:
    """Folder where the two DLLs must be placed (e.g. project root/steam_patch)."""
    return root_folder() / "steam_patch"


def find_dll_dir() -> Optional[Path]:
    """
    Directory that contains both xinput1_4.dll and hid.dll.
    Only looks in the steam_patch folder. Returns None if not found.
    """
    candidate = get_steam_patch_dir()
    if not candidate.exists():
        return None
    if all((candidate / name).exists() for name in DLL_NAMES):
        return candidate
    return None


def get_patch_status(steam_path: Path) -> str:
    """
    Returns "patched", "not_patched", or "partial" depending on how many
    of the two DLLs are present in the Steam directory.
    """
    steam_path = Path(steam_path)
    present = sum(1 for name in DLL_NAMES if (steam_path / name).exists())
    if present == 2:
        return "patched"
    if present == 0:
        return "not_patched"
    return "partial"


def patch_steam(steam_path: Path) -> tuple[bool, str]:
    """
    Copy xinput1_4.dll and hid.dll into the Steam directory.
    Returns (success, message).
    """
    if sys.platform != "win32":
        return False, "Steam patch is only supported on Windows."

    steam_path = Path(steam_path)
    dll_dir = find_dll_dir()
    if not dll_dir:
        return False, (
            f"DLLs not found. Place xinput1_4.dll and hid.dll in: {get_steam_patch_dir()}"
        )

    if not steam_path.exists() or not (steam_path / "steam.exe").exists():
        return False, f"Steam path does not exist or has no steam.exe: {steam_path}"

    try:
        for name in DLL_NAMES:
            src = dll_dir / name
            dst = steam_path / name
            shutil.copy2(src, dst)
            logger.info("Copied %s -> %s", src, dst)
        return True, "Steam patched. Restart Steam for changes to take effect."
    except OSError as e:
        logger.exception("Patch failed")
        return False, f"Failed to copy DLLs: {e}. Try running as administrator if Steam is in Program Files."


def unpatch_steam(steam_path: Path) -> tuple[bool, str]:
    """
    Remove xinput1_4.dll and hid.dll from the Steam directory.
    Returns (success, message).
    """
    if sys.platform != "win32":
        return False, "Steam patch is only supported on Windows."

    steam_path = Path(steam_path)
    removed = 0
    errors = []
    for name in DLL_NAMES:
        p = steam_path / name
        if p.exists():
            try:
                p.unlink()
                removed += 1
                logger.info("Removed %s", p)
            except OSError as e:
                errors.append(f"{name}: {e}")
    if errors:
        return False, "Failed to remove: " + "; ".join(errors)
    if removed == 0:
        return True, "Steam was not patched (no DLLs found)."
    return True, f"Unpatched Steam (removed {removed} DLL(s)). Restart Steam for changes to take effect."
