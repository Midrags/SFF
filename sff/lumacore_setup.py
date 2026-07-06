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
import hashlib
import json
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

_LC_DLLS = ("dwmapi.dll", "xinput1_4.dll", "LumaCore.dll", "LumaCorePayload.dll")

_GL_MARKER = ".steamidra_gl_cleaned"
_LEGACY_MARKER_DIR = "lumacore"
_LEGACY_MARKER_NAME = ".gl_cleaned"

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
    ("", "xinput1_4.dll"),
    ("", "LumaCore.dll"),
    ("", "LumaCorePayload.dll"),
    ("bin", "lcoverlay.dll"),
)

_PATTERN_REPO_RAW = "https://raw.githubusercontent.com/KoriaPolis/Steam-Auto-PT/pattern"
_PATTERN_REPO_CDN = "https://cdn.jsdelivr.net/gh/KoriaPolis/Steam-Auto-PT@pattern"
_PATTERN_REPO_GITFLIC = "https://gitflic.ru/api/project/midrags/steam-auto-pt/blob"


def _progress(msg: str, callback: Optional[Callable[[str], None]]) -> None:
    logger.info(msg)
    if callback:
        callback(msg)


def _gl_marker_path(steam_path: Path) -> Path:
    """Return the canonical path of the GL-cleanup marker.

    Lives at the Steam root, NOT inside <steam>/lumacore/ — that folder is
    LumaCore's runtime log directory. Sharing it with our marker risks the
    marker file being mistaken for log content (or vice versa) and has caused
    LumaCore to fail to start on first run.
    """
    return steam_path / _GL_MARKER


def _legacy_gl_marker_path(steam_path: Path) -> Path:
    return steam_path / _LEGACY_MARKER_DIR / _LEGACY_MARKER_NAME


def _migrate_legacy_marker(steam_path: Path, callback: Optional[Callable[[str], None]]) -> bool:
    """Move a pre-existing marker out of <steam>/lumacore/ to the new location.

    Returns True if a legacy marker existed and was migrated. The empty lumacore/
    folder is removed only when no other files (logs, config) are present, so
    we never destroy LumaCore's runtime data.
    """
    legacy = _legacy_gl_marker_path(steam_path)
    if not legacy.is_file():
        return False

    new_marker = _gl_marker_path(steam_path)
    try:
        new_marker.touch(exist_ok=True)
        legacy.unlink()
        _progress("Migrated legacy GL-cleanup marker out of lumacore/.", callback)
    except OSError as exc:
        _progress(f"Could not migrate legacy marker: {exc}", callback)
        return False

    legacy_dir = legacy.parent
    try:
        if legacy_dir.is_dir() and not any(legacy_dir.iterdir()):
            legacy_dir.rmdir()
            _progress("Removed empty legacy lumacore/ folder.", callback)
    except OSError:
        pass
    return True


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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stitch_gitflic_body(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        return ""
    lines = data.get("blobLines")
    if not isinstance(lines, list):
        return ""
    body: list[str] = []
    for item in lines:
        if isinstance(item, dict):
            line = item.get("body", "")
            body.append(line if isinstance(line, str) else "")
    return "\n".join(body)


def _looks_like_pattern_toml(body: str, subdir: str) -> bool:
    if len(body) < 16 or len(body) > 1024 * 1024:
        return False
    if subdir == "steamclientipc":
        return "interface_id" in body and "funcHash" in body
    return "rva" in body and "sig" in body


def _download_pattern_body(subdir: str, sha: str) -> Optional[str]:
    rel = f"{subdir}/{sha}.toml" if subdir else f"{sha}.toml"
    urls = (
        f"{_PATTERN_REPO_RAW}/{rel}",
        f"{_PATTERN_REPO_CDN}/{rel}",
    )
    primary_not_found = False
    headers = {"Cache-Control": "no-cache", "Accept": "text/plain,*/*"}
    for url in urls:
        if primary_not_found:
            break
        try:
            resp = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
            if resp.status_code == 200 and _looks_like_pattern_toml(resp.text, subdir):
                return resp.text
            if resp.status_code == 404:
                primary_not_found = True
        except httpx.HTTPError:
            continue

    if primary_not_found:
        return None

    try:
        resp = httpx.get(
            _PATTERN_REPO_GITFLIC,
            params={"branch": "pattern", "file": rel},
            headers={"Accept": "application/json"},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            body = _stitch_gitflic_body(resp)
            if _looks_like_pattern_toml(body, subdir):
                return body
    except httpx.HTTPError:
        return None
    return None


def _write_pattern_cache(target: Path, body: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(body, encoding="utf-8", newline="\n")
    tmp.replace(target)


def _prewarm_lumacore_patterns(
    steam_path: Path,
    callback: Optional[Callable[[str], None]],
) -> None:
    """Best-effort cache fill for offline Steam launches after install."""
    jobs = (
        ("steamclient", steam_path / "steamclient64.dll", ""),
        ("steamui", steam_path / "steamui.dll", ""),
        ("steamclient IPC", steam_path / "steamclient64.dll", "steamclientipc"),
    )
    cache_root = steam_path / "lumacore" / "pattern"
    for label, binary_path, subdir in jobs:
        if not binary_path.is_file():
            _progress(f"Pattern cache skipped for {label}: Steam DLL not found.", callback)
            continue
        try:
            sha = _sha256_file(binary_path)
        except OSError as exc:
            _progress(f"Pattern cache skipped for {label}: {exc}", callback)
            continue

        target_dir = cache_root / subdir if subdir else cache_root
        target = target_dir / f"{sha}.toml"
        if target.is_file() and target.stat().st_size > 0:
            _progress(f"Pattern cache ready for {label}.", callback)
            continue

        body = _download_pattern_body(subdir, sha)
        if body is None:
            _progress(f"Pattern cache prewarm missed for {label}.", callback)
            continue
        try:
            _write_pattern_cache(target, body)
            _progress(f"Pattern cache prewarmed for {label}.", callback)
        except OSError as exc:
            _progress(f"Pattern cache write failed for {label}: {exc}", callback)


def _fetch_release_asset(variant: str = "release") -> Optional[tuple[str, str]]:
    """Return (download_url, filename) for the best asset in the latest GitHub release.

    *variant* picks which build to grab. "release" (default) prefers
    `release.zip` / `release.rar`, "debug" prefers `debug.zip` / `debug.rar`.
    Falls back to the first .zip whose name starts with the requested
    variant, then to the first .zip asset overall.
    """
    variant_lower = (variant or "release").strip().lower()
    if variant_lower not in ("release", "debug"):
        variant_lower = "release"
    try:
        resp = httpx.get(
            _LUMACORE_RELEASE_API,
            headers={"Accept": "application/vnd.github+json", "Cache-Control": "no-cache"},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        release_data = resp.json()
        assets = release_data.get("assets", [])
        tag_name = release_data.get("tag_name", "?")

        primary_names = (f"{variant_lower}.zip", f"{variant_lower}.rar")
        for priority_name in primary_names:
            for asset in assets:
                if asset.get("name", "").lower() == priority_name:
                    logger.debug("LumaCore release asset: %s (tag=%s)", asset["name"], tag_name)
                    return asset["browser_download_url"], asset["name"]

        # Loose match: any zip whose filename starts with the variant
        # token. Catches things like "release-v8.zip".
        for asset in assets:
            name_lower = asset.get("name", "").lower()
            if name_lower.endswith(".zip") and name_lower.startswith(variant_lower):
                logger.debug("LumaCore release asset (loose match): %s (tag=%s)", asset["name"], tag_name)
                return asset["browser_download_url"], asset["name"]

        # Final fallback: any zip that is not a source-code tarball.
        # GitHub auto-generates "Source code (zip)" for every release
        # tag and picking that would give us headers + .cpp but no DLLs.
        for asset in assets:
            name = asset.get("name", "")
            if name.lower().endswith(".zip") and "source code" not in name.lower():
                logger.debug("LumaCore release asset (fallback): %s (tag=%s)", name, tag_name)
                return asset["browser_download_url"], name

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
                    logger.error("DLL not found in ZIP: %s (names=%s)", dll, names)
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
    variant: str = "release",
) -> tuple[bool, str]:
    """Full LumaCore setup: kill Steam, GL cleanup (once), remove old LC files, download latest
    release from GitHub, extract and install DLLs to *steam_path*.

    *variant* picks the asset flavour. "release" (default) pulls the
    user-facing build; "debug" pulls the verbose-logging build that
    writes to <steam>\\lumacore\\*.log. Pass through from the WebUI
    Auto LC Setup picker.

    Returns (success, message).
    """
    if not steam_path.is_dir():
        msg = f"Steam path not found: {steam_path}"
        logger.error(msg)
        return False, msg

    # ── Kill Steam before touching DLLs ─────────────────────────
    import sys as _sys
    import time as _time
    if _sys.platform == "win32":
        try:
            from sff.processes import SteamProcess, is_proc_running
            steam_proc = SteamProcess(steam_path)
            if is_proc_running(steam_proc.exe_name):
                _progress("Closing Steam...", progress_callback)
                steam_proc.kill()
                waited = 0
                while is_proc_running(steam_proc.exe_name) and waited < 15:
                    _time.sleep(0.5)
                    waited += 0.5
                if is_proc_running(steam_proc.exe_name):
                    _progress("Warning: Steam did not close in time — DLLs may be locked.", progress_callback)
                else:
                    _progress("Steam closed.", progress_callback)
        except Exception as exc:
            _progress(f"Could not close Steam: {exc}", progress_callback)

    # Migrate legacy marker out of <steam>/lumacore/ before we look at it.
    # Older builds wrote .gl_cleaned into LumaCore's log folder, which on first
    # install of LumaCore could cause a startup glitch. Pull it out and clean
    # up the folder if we left it empty.
    _migrate_legacy_marker(steam_path, progress_callback)

    marker = _gl_marker_path(steam_path)
    if not marker.exists():
        _run_gl_cleanup(steam_path, progress_callback)
        try:
            marker.touch()
        except OSError:
            pass
    else:
        _progress("GreenLuma already cleaned up, skipping.", progress_callback)

    _reset_lumacore_files(steam_path, progress_callback)

    asset = _fetch_release_asset(variant=variant)
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

    _progress("Checking LumaCore pattern cache...", progress_callback)
    try:
        _prewarm_lumacore_patterns(steam_path, progress_callback)
    except Exception as exc:
        logger.warning("LumaCore pattern cache prewarm failed: %s", exc)
        _progress(f"Pattern cache prewarm failed: {exc}", progress_callback)

    msg = "LumaCore installed."
    _progress(msg, progress_callback)
    # Record the version we just installed so check_for_lumacore_update can
    # compare against the latest GitHub release on subsequent launches. Best
    # effort — the install itself is already done at this point.
    try:
        installed_tag = _fetch_latest_release_tag(timeout=5.0)
        if installed_tag:
            remember_installed_lumacore_version(installed_tag)
    except Exception:
        pass
    return True, msg


# ─────────────────────────────────────────────────────────────────────────
# LumaCore version checker
# ─────────────────────────────────────────────────────────────────────────
#
# Releases on github.com/KoriaPolis/LumaCore are tagged like "V4", "V5", etc.
# The release name is "LumaCore V4". We compare the latest tag from GitHub
# against the value cached in settings under LUMACORE_INSTALLED_VERSION and
# treat a mismatch as "update available".
#
# Cadence: at most one HTTP probe per 6 hours, regardless of how many times
# this runs in a session. Cached result lives in Settings.LUMACORE_LAST_CHECK
# / Settings.LUMACORE_LATEST_VERSION so the user sees the answer immediately
# on the next launch without another network round-trip.

_LC_VERSION_CHECK_INTERVAL = 6 * 60 * 60  # 6 hours


def _normalise_lc_version(raw: str) -> str:
    """Trim/normalise a tag or release name so 'V4', 'v4', 'LumaCore V4', etc.
    all collapse to the same key. Returns the bare version token (e.g. 'V4').
    Empty input → empty output.
    """
    if not raw:
        return ""
    token = raw.strip()
    # Drop a leading "LumaCore " label if the tag was actually the release name.
    lower = token.lower()
    if lower.startswith("lumacore"):
        token = token[len("lumacore"):].strip()
    # Normalise the V to uppercase so "v4" and "V4" compare equal.
    if token.startswith(("v", "V")):
        token = "V" + token[1:]
    return token


def _fetch_latest_release_tag(timeout: float = 10.0) -> Optional[str]:
    """Hit /releases/latest and pull the tag_name. None on any failure.
    Caller is responsible for logging — this just returns the value.
    """
    try:
        resp = httpx.get(
            _LUMACORE_RELEASE_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        payload = resp.json()
        # tag_name is the canonical version anchor; release name is a friendlier
        # display fallback.
        return _normalise_lc_version(
            payload.get("tag_name") or payload.get("name") or ""
        ) or None
    except Exception as exc:
        logger.debug("LumaCore release tag fetch failed: %s", exc)
        return None


def get_installed_lumacore_version(steam_path: Path) -> str:
    """Return the version label SteaMidra last installed. Empty when LumaCore
    isn't installed (or was installed by a build that never wrote the tag).
    """
    from sff.storage.settings import get_setting
    from sff.structs import Settings

    # Only treat the cached version as authoritative when the actual DLLs are
    # still on disk. Removing the DLLs by hand should reset the perceived
    # install so the next "Auto LC Setup" actually re-runs.
    for dll in _LC_DLLS:
        if not (steam_path / dll).is_file():
            return ""
    saved = get_setting(Settings.LUMACORE_INSTALLED_VERSION) or ""
    return _normalise_lc_version(str(saved))


def remember_installed_lumacore_version(version: str) -> None:
    """Persist the version label SteaMidra just installed."""
    from sff.storage.settings import set_setting
    from sff.structs import Settings

    set_setting(Settings.LUMACORE_INSTALLED_VERSION, _normalise_lc_version(version))


def check_for_lumacore_update(steam_path: Path, force: bool = False) -> dict:
    """Compare the installed LumaCore version against the latest GitHub
    release. Returns a dict with:
        installed:        version currently on disk (or "" if absent)
        latest:           latest version on GitHub (or "" on network failure)
        update_available: True when the two differ AND both are populated
        checked_at:       unix timestamp of the network probe (or cache hit)
        source:           "remote" if we hit GitHub this call, "cache" otherwise

    Honours a 6-hour cooldown between remote calls unless force=True. Reads
    and writes Settings.LUMACORE_LATEST_VERSION / LUMACORE_LAST_CHECK so the
    answer survives across sessions.
    """
    import time
    from sff.storage.settings import get_setting, set_setting
    from sff.structs import Settings

    installed = get_installed_lumacore_version(steam_path)

    cached_latest = _normalise_lc_version(
        str(get_setting(Settings.LUMACORE_LATEST_VERSION) or "")
    )
    try:
        last_check = float(get_setting(Settings.LUMACORE_LAST_CHECK) or 0)
    except (TypeError, ValueError):
        last_check = 0.0

    now = time.time()
    use_cache = (
        not force
        and cached_latest
        and (now - last_check) < _LC_VERSION_CHECK_INTERVAL
    )

    if use_cache:
        latest = cached_latest
        source = "cache"
        checked_at = last_check
    else:
        fetched = _fetch_latest_release_tag()
        if fetched:
            latest = fetched
            set_setting(Settings.LUMACORE_LATEST_VERSION, latest)
            set_setting(Settings.LUMACORE_LAST_CHECK, str(now))
            checked_at = now
            source = "remote"
        else:
            # Network miss — fall back to whatever we already have.
            latest = cached_latest
            checked_at = last_check
            source = "cache"

    update_available = bool(installed and latest and installed != latest)
    return {
        "installed": installed,
        "latest": latest,
        "update_available": update_available,
        "checked_at": checked_at,
        "source": source,
    }


# ─────────────────────────────────────────────────────────────────────────
# Deactivate / remove LumaCore
# ─────────────────────────────────────────────────────────────────────────
#
# Removes every file SteaMidra installs as part of LumaCore. Steam MUST be
# fully closed before this runs because the DLLs are loaded into steam.exe
# while it's running and the unlink will fail with "file in use" otherwise.
# The web/CLI surface kills Steam first, then calls this; the function
# itself only deletes files and reports what it did.

_LC_REMOVE_PROCESSES = ("steam.exe", "steamservice.exe", "steamwebhelper.exe")


def _force_close_steam(progress_callback: Optional[Callable[[str], None]] = None) -> None:
    """Kill every Steam-side process that would hold a handle on LumaCore.dll
    or dwmapi.dll. Best-effort — caller still surfaces success/failure based
    on whether the unlink afterwards works.
    """
    import sys

    if sys.platform != "win32":
        return
    try:
        from sff.processes import is_proc_running
    except Exception:
        is_proc_running = None  # type: ignore

    for name in _LC_REMOVE_PROCESSES:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            _progress(f"Stopped {name}", progress_callback)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("taskkill on %s failed: %s", name, exc)

    # Give the loader a moment to fully release file handles.
    import time
    for _ in range(20):
        time.sleep(0.25)
        if is_proc_running is None:
            break
        any_alive = False
        for name in _LC_REMOVE_PROCESSES:
            try:
                if is_proc_running(name):
                    any_alive = True
                    break
            except Exception:
                pass
        if not any_alive:
            break


def deactivate_lumacore(
    steam_path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """Close Steam, delete LumaCore.dll / dwmapi.dll / lcoverlay.dll, clear
    the installed-version setting. Idempotent — running twice on a clean
    install reports "nothing to remove" instead of failing.

    Returns (ok, message). ok is True when no DLL remains on disk after the
    sweep (whether anything was deleted or not).
    """
    from sff.storage.settings import set_setting
    from sff.structs import Settings

    _progress("Closing Steam...", progress_callback)
    _force_close_steam(progress_callback)

    removed = 0
    failures: list[str] = []
    for subdir, name in _LC_RESET_FILES:
        target = (steam_path / subdir / name) if subdir else (steam_path / name)
        if not target.exists():
            continue
        path_label = f"{subdir}/{name}" if subdir else name
        try:
            target.unlink()
            removed += 1
            _progress(f"Removed {path_label}", progress_callback)
        except OSError as exc:
            failures.append(f"{path_label} ({exc})")
            logger.warning("Failed to remove %s: %s", target, exc)

    # Clear the cached install version so check_for_lumacore_update reports
    # accurately on the next launch.
    try:
        set_setting(Settings.LUMACORE_INSTALLED_VERSION, "")
    except Exception:
        pass

    if failures:
        msg = (
            f"Removed {removed} file(s); could not remove: "
            + ", ".join(failures)
            + ". Close Steam fully and try again, or delete the files manually."
        )
        _progress(msg, progress_callback)
        return False, msg

    if removed == 0:
        msg = "LumaCore was not installed in this Steam folder; nothing to remove."
        _progress(msg, progress_callback)
        return True, msg

    msg = f"LumaCore deactivated. Removed {removed} file(s)."
    _progress(msg, progress_callback)
    return True, msg
