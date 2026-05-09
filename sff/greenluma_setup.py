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
Auto GreenLuma Setup — extracts a GL archive (ZIP/RAR/7z) and patches DLLInjector.ini.

Method A: GreenLuma folder placed next to SteaMidra.exe.
Method B: GreenLuma files placed inside Steam's installation folder.
"""

import logging
import shutil
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_UNRAR_CANDIDATES = [
    r"C:\Program Files\WinRAR\UnRAR.exe",
    r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    r"C:\Program Files\WinRAR\WinRAR.exe",
    r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
    "unrar",
    "unrar.exe",
]

_GL_DLL_PATTERNS = [
    "GreenLuma_2024_x64.dll",
    "GreenLuma_2025_x64.dll",
    "GreenLuma_2024_x86.dll",
    "GreenLuma_2025_x86.dll",
]

_DLL_INI_SECTION = "DllInjector"


def _find_unrar() -> str:
    """Return path to UnRAR/WinRAR executable, or empty string."""
    for candidate in _UNRAR_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return str(p)
        found = shutil.which(candidate)
        if found:
            return found
    return ""


def _extract_zip(archive_path: str, dest_dir: str) -> None:
    with zipfile.ZipFile(archive_path, "r") as z:
        z.extractall(dest_dir)


def _extract_rar(archive_path: str, dest_dir: str) -> None:
    try:
        import rarfile
        unrar = _find_unrar()
        if unrar:
            rarfile.UNRAR_TOOL = unrar
        with rarfile.RarFile(archive_path) as r:
            r.extractall(dest_dir)
        return
    except ImportError:
        pass
    # Fallback: use WinRAR/7-Zip subprocess
    unrar = _find_unrar()
    if unrar:
        import subprocess
        import sys
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        subprocess.run(
            [unrar, "x", "-y", archive_path, dest_dir + "\\"],
            capture_output=True, timeout=120, **flags,
        )
        return
    raise RuntimeError(
        "Cannot extract RAR: rarfile module not installed and WinRAR/UnRAR not found. "
        "Install WinRAR or run: pip install rarfile"
    )


def _extract_7z(archive_path: str, dest_dir: str) -> None:
    try:
        import py7zr
        with py7zr.SevenZipFile(archive_path, mode="r") as z:
            z.extractall(path=dest_dir)
        return
    except ImportError:
        pass
    # Fallback: system 7z.exe
    seven_z = shutil.which("7z") or shutil.which("7z.exe")
    if seven_z:
        import subprocess
        import sys
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        subprocess.run(
            [seven_z, "x", archive_path, f"-o{dest_dir}", "-y"],
            capture_output=True, timeout=120, **flags,
        )
        return
    raise RuntimeError("Cannot extract 7z: py7zr not installed and 7z.exe not found.")


def extract_archive(archive_path: str, dest_dir: str) -> None:
    """Extract archive to dest_dir. Supports ZIP, RAR, 7z."""
    ext = Path(archive_path).suffix.lower()
    if ext == ".zip":
        _extract_zip(archive_path, dest_dir)
    elif ext == ".rar":
        _extract_rar(archive_path, dest_dir)
    elif ext == ".7z":
        _extract_7z(archive_path, dest_dir)
    else:
        # Try ZIP first, then RAR, then 7z
        for fn in (_extract_zip, _extract_rar, _extract_7z):
            try:
                fn(archive_path, dest_dir)
                return
            except Exception:
                continue
        raise RuntimeError(f"Unsupported or unextractable archive: {archive_path}")


def find_dll_in_dir(dir_path: str) -> str:
    """Find the GreenLuma DLL in a directory tree. Returns full path or empty string."""
    root = Path(dir_path)
    for pattern in _GL_DLL_PATTERNS:
        matches = list(root.rglob(pattern))
        if matches:
            return str(matches[0])
    # Fallback: look for any *GreenLuma*.dll
    matches = list(root.rglob("*GreenLuma*.dll"))
    if matches:
        return str(matches[0])
    return ""


def find_ini_in_dir(dir_path: str) -> str:
    """Find DLLInjector.ini in a directory tree. Returns full path or empty string."""
    root = Path(dir_path)
    matches = list(root.rglob("DLLInjector.ini"))
    if matches:
        return str(matches[0])
    return ""


def patch_dll_injector_ini(ini_path: str, steam_exe: str, dll_path: str) -> None:
    """Patch DLLInjector.ini with the correct Exe and Dll paths, line by line."""
    p = Path(ini_path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""

    if not text:
        # Write a minimal config
        text = (
            f"[{_DLL_INI_SECTION}]\r\n"
            f'Exe = "{steam_exe}"\r\n'
            f'Dll = "{dll_path}"\r\n'
            "CreateFiles = 1\r\n"
            "FileToCreate_1 = NoQuestion.bin\r\n"
            "AllowMultipleInstancesOfDLLInjector = 0\r\n"
            "WaitForProcessTermination = 0\r\n"
        )
        p.write_text(text, encoding="utf-8")
        return

    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=")[0].strip() if "=" in stripped else stripped
        if key == "Exe":
            indent = line[: len(line) - len(line.lstrip())]
            result.append(f'{indent}Exe = "{steam_exe}"\r\n')
        elif key == "Dll":
            indent = line[: len(line) - len(line.lstrip())]
            result.append(f'{indent}Dll = "{dll_path}"\r\n')
        elif key == "CreateFiles":
            indent = line[: len(line) - len(line.lstrip())]
            result.append(f"{indent}CreateFiles = 1\r\n")
        elif key == "FileToCreate_1":
            indent = line[: len(line) - len(line.lstrip())]
            result.append(f"{indent}FileToCreate_1 = NoQuestion.bin\r\n")
        else:
            result.append(line)
    p.write_text("".join(result), encoding="utf-8")


def auto_gl_setup(method: str, archive_path: str, steam_exe_path: str) -> dict:
    """
    Extract and configure GreenLuma.

    method='A': install next to SteaMidra.exe in a GreenLuma/ subfolder.
    method='B': install directly into Steam's installation directory.

    Returns {'ok': bool, 'message': str, 'applist_path': str}.
    """
    from sff.utils import root_folder

    archive_path = str(Path(archive_path).resolve())
    if not Path(archive_path).exists():
        return {"ok": False, "message": f"Archive not found: {archive_path}", "applist_path": ""}

    steam_exe = Path(steam_exe_path)
    if not steam_exe.exists():
        logger.warning("steam.exe not found at %s — patching anyway", steam_exe_path)

    # Determine destination directory
    if method == "B":
        dest_dir = steam_exe.parent if steam_exe.exists() else Path(r"C:\Program Files (x86)\Steam")
    else:
        # Method A: GreenLuma subfolder next to SteaMidra.exe
        app_dir = root_folder()
        dest_dir = Path(app_dir) / "GreenLuma"

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Extract archive into a temp folder, then copy into dest_dir
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="steamidra_gl_"))
    try:
        logger.info("Extracting %s → %s", archive_path, tmp)
        extract_archive(archive_path, str(tmp))

        # Find DLL and INI
        dll_path = find_dll_in_dir(str(tmp))
        ini_path = find_ini_in_dir(str(tmp))

        if not dll_path:
            return {"ok": False, "message": "GreenLuma DLL not found in archive.", "applist_path": ""}
        if not ini_path:
            logger.warning("DLLInjector.ini not found in archive — will create one")

        # Copy all extracted files into dest_dir
        for item in Path(tmp).rglob("*"):
            if item.is_file():
                rel = item.relative_to(tmp)
                target = dest_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

        # Resolve final paths
        final_dll = str(dest_dir / Path(dll_path).relative_to(tmp))
        final_ini_path = str(dest_dir / Path(ini_path).relative_to(tmp)) if ini_path else str(dest_dir / "DLLInjector.ini")

        # Patch the INI
        patch_dll_injector_ini(final_ini_path, str(steam_exe), final_dll)

        # AppList folder
        applist_dir = dest_dir / "AppList"
        applist_dir.mkdir(parents=True, exist_ok=True)

        logger.info("GreenLuma setup complete in %s", dest_dir)
        return {
            "ok": True,
            "message": f"GreenLuma installed to {dest_dir}. Edit AppList and run DLLInjector.exe.",
            "applist_path": str(applist_dir),
        }
    except Exception as exc:
        logger.error("GreenLuma setup failed: %s", exc)
        return {"ok": False, "message": f"Setup failed: {exc}", "applist_path": ""}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
