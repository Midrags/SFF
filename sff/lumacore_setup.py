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

"""Download the latest LumaCore release from GitHub and install DLLs into the Steam folder."""

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

import httpx
import rarfile  # type: ignore

logger = logging.getLogger(__name__)

_EXTRACTOR_CANDIDATES: list[tuple[str, str]] = [
    ("7z",                                         "7z"),
    ("7zz",                                        "7z"),
    (r"C:\Program Files\7-Zip\7z.exe",             "7z"),
    (r"C:\Program Files (x86)\7-Zip\7z.exe",      "7z"),
    (r"C:\Program Files\WinRAR\WinRAR.exe",        "winrar"),
    (r"C:\Program Files (x86)\WinRAR\WinRAR.exe",  "winrar"),
    ("WinRAR",                                     "winrar"),
    ("unrar",                                      "unrar"),
]


def _find_extractor() -> tuple[str, str]:
    """Return (exe_path, tool_type) for the first usable archive extractor, or ('', '')."""
    for candidate, tool_type in _EXTRACTOR_CANDIDATES:
        if tool_type in ("winrar", "unrar"):
            if os.path.isabs(candidate):
                if Path(candidate).is_file():
                    return candidate, tool_type
            else:
                resolved = shutil.which(candidate)
                if resolved:
                    return resolved, tool_type
            continue
        try:
            result = subprocess.run(
                [candidate, "--help"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode in (0, 1):
                return candidate, tool_type
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return "", ""


def _extract_dlls_via_subprocess(
    archive: Path,
    steam_path: Path,
    callback: Optional[Callable[[str], None]],
) -> bool:
    """Extract LumaCore DLLs using an external archiver (WinRAR / 7-Zip / unrar)."""
    exe, tool_type = _find_extractor()
    if not exe:
        _progress("No external extractor found. Install 7-Zip or WinRAR.", callback)
        return False
    _progress(f"Using {Path(exe).name} for extraction...", callback)
    with tempfile.TemporaryDirectory(prefix="sff_lc_ext_") as tmp:
        tmp_path = Path(tmp)
        if tool_type == "winrar":
            cmd = [exe, "x", "-y", str(archive), tmp + os.sep]
        elif tool_type == "unrar":
            cmd = [exe, "x", "-y", str(archive), tmp + os.sep]
        else:
            cmd = [exe, "x", str(archive), f"-o{tmp}", "-y"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                err = result.stderr.decode(errors="replace")[:200]
                _progress(f"Extractor returned error: {err}", callback)
                return False
        except subprocess.TimeoutExpired:
            _progress("Extraction timed out.", callback)
            return False
        except Exception as exc:
            _progress(f"Extraction subprocess failed: {exc}", callback)
            return False
        for dll in _LC_DLLS:
            dll_lower = dll.lower()
            found: Optional[Path] = None
            for p in tmp_path.rglob("*"):
                if p.is_file() and p.name.lower() == dll_lower:
                    found = p
                    break
            if found is None:
                _progress(f"DLL not found in extracted archive: {dll}", callback)
                return False
            (steam_path / dll).write_bytes(found.read_bytes())
            _progress(f"Installed {dll}", callback)
    return True

_LUMACORE_GITHUB_REPO = "KoriaPolis/LumaCore"
_LUMACORE_RELEASE_API = f"https://api.github.com/repos/{_LUMACORE_GITHUB_REPO}/releases/latest"

_LC_DLLS = ("dwmapi.dll", "LumaCore.dll")

_GL_MARKER = ".gl_cleaned"

_GL_ROOT_FILES = (
    "GreenLuma_2024_x64.dll",
    "GreenLuma_2024_x86.dll",
    "GreenLuma_2025_x64.dll",
    "GreenLuma_2025_x86.dll",
    "GreenLuma.dll",
    "GreenLumaSettings_2025.exe",
    "DLLInjector.exe",
    "DLLInjector.ini",
    "SteamKillInject.exe",
)

_GL_BIN_FILES = (
    "x86launcher.exe",
)

_GL_ROOT_DIRS = (
    "AppList",
    "GreenLuma2025_Files",
)

_LC_RESET_FILES = (
    ("", "dwmapi.dll"),
    ("", "LumaCore.dll"),
    ("bin", "lcoverlay.dll"),
    ("bin", "diversion.dll"),
)


def _progress(msg: str, callback: Optional[Callable[[str], None]]) -> None:
    logger.info(msg)
    if callback:
        callback(msg)


def _gl_marker_path(steam_path: Path) -> Path:
    return steam_path / "lumacore" / _GL_MARKER


def _run_gl_cleanup(steam_path: Path, callback: Optional[Callable[[str], None]]) -> None:
    """Remove all GreenLuma files and folders from *steam_path*. Called at most once."""
    _progress("Removing GreenLuma files...", callback)

    for name in _GL_ROOT_FILES:
        target = steam_path / name
        if target.exists():
            try:
                target.unlink()
                _progress(f"Removed {name}", callback)
            except OSError as exc:
                _progress(f"Could not remove {name}: {exc}", callback)

    bin_dir = steam_path / "bin"
    for name in _GL_BIN_FILES:
        target = bin_dir / name
        if target.exists():
            try:
                target.unlink()
                _progress(f"Removed bin/{name}", callback)
            except OSError as exc:
                _progress(f"Could not remove bin/{name}: {exc}", callback)

    for name in _GL_ROOT_DIRS:
        target = steam_path / name
        if target.is_dir():
            try:
                shutil.rmtree(target)
                _progress(f"Removed folder {name}/", callback)
            except OSError as exc:
                _progress(f"Could not remove folder {name}/: {exc}", callback)


def _reset_lumacore_files(steam_path: Path, callback: Optional[Callable[[str], None]]) -> None:
    """Remove previously installed LumaCore DLLs so a clean install can follow."""
    for subdir, name in _LC_RESET_FILES:
        target = (steam_path / subdir / name) if subdir else (steam_path / name)
        if target.exists():
            try:
                target.unlink()
                path_label = f"{subdir}/{name}" if subdir else name
                _progress(f"Removed old {path_label}", callback)
            except OSError as exc:
                path_label = f"{subdir}/{name}" if subdir else name
                _progress(f"Could not remove {path_label}: {exc}", callback)


def _fetch_release_asset() -> Optional[tuple[str, str]]:
    """Return (download_url, filename) for the best asset in the latest GitHub release.

    Priority: release.zip → release.rar → first .zip asset found.
    """
    try:
        resp = httpx.get(
            _LUMACORE_RELEASE_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        assets = resp.json().get("assets", [])

        for priority_name in ("release.zip", "release.rar"):
            for asset in assets:
                if asset.get("name", "").lower() == priority_name:
                    return asset["browser_download_url"], asset["name"]

        for asset in assets:
            if asset.get("name", "").lower().endswith(".zip"):
                return asset["browser_download_url"], asset["name"]

    except Exception as exc:
        logger.warning("GitHub release fetch failed: %s", exc)
    return None


def _dll_name_match(names: list[str], dll: str) -> Optional[str]:
    """Find *dll* in a list of archive member names (case-insensitive, any subfolder)."""
    dll_lower = dll.lower()
    return next(
        (n for n in names if n.lower() == dll_lower or n.lower().endswith(f"/{dll_lower}")),
        None,
    )


def _extract_zip(archive: Path, steam_path: Path,
                 callback: Optional[Callable[[str], None]]) -> bool:
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            names = zf.namelist()
            for dll in _LC_DLLS:
                member = _dll_name_match(names, dll)
                if member is None:
                    logger.error("DLL not found in ZIP: %s", dll)
                    return False
                (steam_path / dll).write_bytes(zf.read(member))
                _progress(f"Installed {dll}", callback)
        return True
    except Exception as exc:
        logger.error("ZIP extraction failed: %s — trying external tool", exc)
        _progress(f"ZIP extraction failed ({exc}), trying external tool...", callback)
        return _extract_dlls_via_subprocess(archive, steam_path, callback)


def _extract_rar(archive: Path, steam_path: Path,
                 callback: Optional[Callable[[str], None]]) -> bool:
    try:
        with rarfile.RarFile(str(archive), "r") as rf:
            names = rf.namelist()
            for dll in _LC_DLLS:
                member = _dll_name_match(names, dll)
                if member is None:
                    logger.error("DLL not found in RAR: %s", dll)
                    return False
                (steam_path / dll).write_bytes(rf.read(member))
                _progress(f"Installed {dll}", callback)
        return True
    except Exception as exc:
        logger.error("RAR extraction failed: %s — trying external tool", exc)
        _progress(f"RAR extraction failed ({exc}), trying external tool...", callback)
        return _extract_dlls_via_subprocess(archive, steam_path, callback)


def install_lumacore(
    steam_path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """Full LumaCore setup: GL cleanup (once), remove old LC files, download latest
    release from GitHub, extract and install DLLs to *steam_path*.

    Returns (success, message).
    """
    if not steam_path.is_dir():
        msg = f"Steam path not found: {steam_path}"
        logger.error(msg)
        return False, msg

    marker = _gl_marker_path(steam_path)
    if not marker.exists():
        _run_gl_cleanup(steam_path, progress_callback)
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError:
            pass
    else:
        _progress("GreenLuma already cleaned up, skipping.", progress_callback)

    _reset_lumacore_files(steam_path, progress_callback)

    asset = _fetch_release_asset()
    if asset is None:
        msg = "Could not reach GitHub releases. Check your internet connection."
        logger.error(msg)
        return False, msg

    url, filename = asset
    _progress(f"Downloading {filename}...", progress_callback)

    with tempfile.TemporaryDirectory(prefix="sff_lc_") as tmp:
        archive_path = Path(tmp) / filename
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=None) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with archive_path.open("wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=524288):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            _progress(f"Downloading... {pct}%", progress_callback)
        except Exception as exc:
            msg = f"Download failed: {exc}"
            logger.error(msg)
            return False, msg

        _progress("Extracting DLLs...", progress_callback)
        if filename.lower().endswith(".rar"):
            ok = _extract_rar(archive_path, steam_path, progress_callback)
        else:
            ok = _extract_zip(archive_path, steam_path, progress_callback)

    if not ok:
        return False, "Failed to extract DLLs from the release archive."

    for dll in _LC_DLLS:
        if not (steam_path / dll).is_file():
            msg = f"DLL missing after install: {dll}"
            logger.error(msg)
            return False, msg

    msg = "LumaCore installed."
    _progress(msg, progress_callback)
    return True, msg
