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
Goldberg emulator auto-updater.

Downloads the latest gbe_fork release from GitHub, extracts DLLs,
and caches them for use by the Fix Game pipeline.

Source: https://github.com/Detanup01/gbe_fork
"""

import os
import io
import sys
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/Detanup01/gbe_fork/releases/latest"
RELEASE_ASSET_NAME = "emu-win-release.7z"
LINUX_RELEASE_ASSET_NAME = "emu-linux-release.tar.bz2"

# files we need from the Windows release archive
REQUIRED_FILES = {
    # regular mode — experimental builds (include overlay support, ~19 MB)
    "steam_api.dll":              "release/experimental/x32/steam_api.dll",
    "steam_api64.dll":            "release/experimental/x64/steam_api64.dll",
    # coldclient mode — full steamclient emulator (~19 MB)
    "steamclient.dll":            "release/steamclient_experimental/steamclient.dll",
    "steamclient64.dll":          "release/steamclient_experimental/steamclient64.dll",
    "steamclient_loader_x32.exe": "release/steamclient_experimental/steamclient_loader_x32.exe",
    "steamclient_loader_x64.exe": "release/steamclient_experimental/steamclient_loader_x64.exe",
    # extra DLLs for coldclient injection
    "steamclient_extra_x32.dll":  "release/steamclient_experimental/extra_dlls/steamclient_extra_x32.dll",
    "steamclient_extra_x64.dll":  "release/steamclient_experimental/extra_dlls/steamclient_extra_x64.dll",
    # overlay renderer — required when any overlay is enabled in steam_settings
    "GameOverlayRenderer.dll":    "release/steamclient_experimental/GameOverlayRenderer.dll",
    "GameOverlayRenderer64.dll":  "release/steamclient_experimental/GameOverlayRenderer64.dll",
}

# generate_interfaces tool (Windows)
TOOLS_FILES = {
    "generate_interfaces_x32.exe": "release/tools/generate_interfaces/generate_interfaces_x32.exe",
    "generate_interfaces_x64.exe": "release/tools/generate_interfaces/generate_interfaces_x64.exe",
}

# files we need from the Linux release archive (.tar.bz2)
# key = dest filename in cache; value = path inside the archive
LINUX_REQUIRED_FILES = {
    "libsteam_api.so":   "release/regular/x64/libsteam_api.so",
    "libsteam_api32.so": "release/regular/x32/libsteam_api.so",  # same filename, different dir
    "steamclient.so":    "release/regular/x64/steamclient.so",
    "steamclient32.so":  "release/regular/x32/steamclient.so",
}

# Linux generate_interfaces tools
LINUX_TOOLS_FILES = {
    "generate_interfaces_x64": "release/tools/generate_interfaces/generate_interfaces_x64",
    "generate_interfaces_x32": "release/tools/generate_interfaces/generate_interfaces_x32",
}


class GoldbergUpdater:
    """
    Auto-downloads and caches the latest Goldberg emulator (gbe_fork).

    Checks GitHub releases API, compares with cached version,
    downloads emu-win-release.7z (Windows) or emu-linux-release.tar.bz2 (Linux)
    if outdated, and extracts all needed files.
    """

    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_version(self):
        """get the currently cached version tag"""
        version_file = self.cache_dir / "version.txt"
        try:
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return None

    def get_latest_version(self, linux_native: bool = False):
        """
        Check GitHub for the latest release.
        Returns (tag_name, download_url) or None on failure.
        On Linux with linux_native=True, returns the emu-linux-release.tar.bz2 asset URL.
        """
        want_asset = LINUX_RELEASE_ASSET_NAME if linux_native else RELEASE_ASSET_NAME
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(RELEASES_URL, headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "SteaMidra/1.0",
                })
                resp.raise_for_status()
                data = resp.json()
                tag = data.get("tag_name", "")
                assets = data.get("assets", [])
                for asset in assets:
                    if asset.get("name", "") == want_asset:
                        return (tag, asset["browser_download_url"])
                # fallback: look for any 7z asset matching the platform
                for asset in assets:
                    name = asset.get("name", "")
                    if linux_native:
                        if name.endswith(".tar.bz2") and "linux" in name.lower():
                            return (tag, asset["browser_download_url"])
                    else:
                        if name.endswith(".7z") and "win" in name.lower():
                            return (tag, asset["browser_download_url"])
                logger.warning("No suitable asset found in gbe_fork release %s", tag)
                return None
        except Exception as e:
            logger.error("Failed to check gbe_fork releases: %s", e)
            return None

    def needs_update(self):
        """check if we need to download a newer version"""
        cached = self.get_cached_version()
        if not cached:
            return True
        latest = self.get_latest_version()
        if not latest:
            return False  # can't check, assume we're fine
        return cached != latest[0]

    def _copy_bundled_fallback(self, log, linux_native: bool = False):
        """
        Last-resort fallback: copy any Goldberg files that ship inside
        third_party/gbe_fork/ (Windows) or third_party/gbe_fork_linux/emu-linux-release/ (Linux)
        into the cache directory.
        Linux files use the archive_path (dict value) as relative path within the folder.
        """
        import shutil
        tp_root = Path(__file__).parent.parent.parent / "third_party"
        if linux_native:
            # bundled Linux files live under gbe_fork_linux/emu-linux-release/
            base_dir = tp_root / "gbe_fork_linux" / "emu-linux-release"
            files_to_copy = {**LINUX_REQUIRED_FILES, **LINUX_TOOLS_FILES}
            label = "third_party/gbe_fork_linux/"
            if not base_dir.is_dir():
                return False
            copied = 0
            for dest_name, archive_path in files_to_copy.items():
                src = base_dir / archive_path  # e.g. base_dir/release/regular/x64/libsteam_api.so
                if src.exists():
                    dst = self.cache_dir / dest_name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    if dest_name.endswith(".so") or "." not in dest_name:
                        dst.chmod(dst.stat().st_mode | 0o111)
                    copied += 1
                    logger.debug("Copied bundled %s to cache", dest_name)
                else:
                    logger.debug("Bundled file not found: %s", src)
        else:
            third_party = tp_root / "gbe_fork"
            files_to_copy = {**REQUIRED_FILES, **TOOLS_FILES}
            label = "third_party/gbe_fork/"
            if not third_party.is_dir():
                return False
            copied = 0
            for dest_name in files_to_copy:
                src = third_party / dest_name
                if src.exists():
                    dst = self.cache_dir / dest_name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1
                    logger.debug("Copied bundled %s to cache", dest_name)
        if copied:
            (self.cache_dir / "version.txt").write_text("bundled", encoding="utf-8")
            log(f"Using {copied} bundled Goldberg file(s) from {label}")
            return True
        return False

    def ensure_goldberg(self, force_update: bool = False, log_func=None, linux_native: bool = False):
        """
        Make sure we have the latest Goldberg files cached.
        Downloads emu-win-release.7z (Windows) or emu-linux-release.7z (Linux native).
        Returns True if files are available.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        # determine which files to check based on platform
        if linux_native:
            check_files = ["libsteam_api.so"]
        else:
            check_files = ["steam_api.dll", "steam_api64.dll"]
        has_files = all((self.cache_dir / name).exists() for name in check_files)
        if has_files and not force_update:
            cached_ver = self.get_cached_version()
            if cached_ver:
                log(f"Goldberg {cached_ver} already cached")
                return True
        # check latest version
        log("Checking for latest Goldberg emulator...")
        latest = self.get_latest_version(linux_native=linux_native)
        if not latest:
            log("Could not check GitHub releases")
            if has_files:
                return True
            log("Trying bundled fallback...")
            return self._copy_bundled_fallback(log, linux_native=linux_native)
        tag, download_url = latest
        cached_ver = self.get_cached_version()
        if cached_ver == tag and has_files and not force_update:
            log(f"Goldberg {tag} is up to date")
            return True
        log(f"Downloading Goldberg {tag}...")
        ok = self._download_and_extract(tag, download_url, log, linux_native=linux_native)
        if ok:
            return True
        # download/extraction failed — fall back to whatever we have
        if has_files:
            log("Download failed — using previously cached files")
            return True
        log("Download failed — trying bundled fallback...")
        return self._copy_bundled_fallback(log, linux_native=linux_native)

    def _download_and_extract(self, tag, url, log, linux_native: bool = False):
        """download the archive and extract needed files.
        Linux uses .tar.bz2 (Python tarfile stdlib); Windows uses .7z (py7zr or system 7z).
        """
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                archive_data = resp.content
            log(f"Downloaded {len(archive_data):,} bytes, extracting...")
        except Exception as e:
            logger.error("Failed to download Goldberg: %s", e)
            log(f"Download failed: {e}")
            return False
        files_to_extract = {**LINUX_REQUIRED_FILES, **LINUX_TOOLS_FILES} if linux_native else {**REQUIRED_FILES, **TOOLS_FILES}
        # Linux: .tar.bz2 — use stdlib tarfile (no extra dependencies needed)
        if linux_native:
            try:
                import tarfile
                import tempfile
                import shutil
                with tarfile.open(fileobj=io.BytesIO(archive_data), mode='r:bz2') as tf:
                    members = tf.getnames()
                    log(f"Archive contains {len(members)} entries")
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tf.extractall(path=tmpdir)
                        extracted_count = 0
                        tmppath = Path(tmpdir)
                        for dest_name, archive_path in files_to_extract.items():
                            # Use the full archive path to find the correct file
                            # (important: x64 and x32 both have 'libsteam_api.so')
                            full = tmppath / archive_path
                            found = full if full.exists() else self._find_file(tmppath, Path(archive_path).name)
                            if found:
                                dest = self.cache_dir / dest_name
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(found, dest)
                                if dest_name.endswith(".so") or "." not in dest_name:
                                    dest.chmod(dest.stat().st_mode | 0o111)
                                extracted_count += 1
                            else:
                                logger.debug("File not found in archive: %s (path: %s)", dest_name, archive_path)
                        log(f"Extracted {extracted_count} file(s)")
                (self.cache_dir / "version.txt").write_text(tag, encoding="utf-8")
                log(f"Goldberg {tag} cached successfully (Linux)")
                return True
            except Exception as e:
                log(f"tarfile extraction failed ({e}) — trying subprocess tar...")
            return self._extract_with_subprocess(archive_data, tag, log, linux_native=True)
        # Windows: .7z — try py7zr first, fall through to system 7z on any failure (e.g. BCJ2)
        try:
            import py7zr
            import tempfile
            import shutil
            with py7zr.SevenZipFile(io.BytesIO(archive_data), mode='r') as archive:
                all_files = archive.getnames()
                log(f"Archive contains {len(all_files)} files")
                with tempfile.TemporaryDirectory() as tmpdir:
                    archive.extractall(path=tmpdir)
                    extracted_count = 0
                    tmppath = Path(tmpdir)
                    for dest_name, archive_path in files_to_extract.items():
                        full = tmppath / archive_path
                        found = full if full.exists() else self._find_file(tmppath, Path(archive_path).name)
                        if found:
                            dest = self.cache_dir / dest_name
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(found, dest)
                            extracted_count += 1
                        else:
                            logger.debug("File not found in archive: %s (path: %s)", dest_name, archive_path)
                    log(f"Extracted {extracted_count} files")
            (self.cache_dir / "version.txt").write_text(tag, encoding="utf-8")
            log(f"Goldberg {tag} cached successfully")
            return True
        except ImportError:
            log("py7zr not installed — trying system 7z...")
        except Exception as e:
            log(f"py7zr extraction failed ({e}) — trying system 7z...")
        return self._extract_with_subprocess(archive_data, tag, log, linux_native=False)

    def _find_file(self, search_dir, filename):
        """recursively find a file by name in a directory"""
        for path in search_dir.rglob(filename):
            if path.is_file():
                return path
        return None

    # (executable_path, tool_type) candidates checked in order
    # tool_type is "7z" or "winrar" — each needs different CLI syntax
    # Linux: "7z" and "7zz" are found via PATH (p7zip-full / 7-zip package)
    _EXTRACTOR_CANDIDATES = [
        ("7z",                                          "7z"),
        ("7zz",                                         "7z"),
        (r"C:\Program Files\7-Zip\7z.exe",              "7z"),
        (r"C:\Program Files (x86)\7-Zip\7z.exe",       "7z"),
        (r"C:\Program Files\WinRAR\WinRAR.exe",         "winrar"),
        (r"C:\Program Files (x86)\WinRAR\WinRAR.exe",   "winrar"),
        ("WinRAR",                                      "winrar"),
    ]

    def _find_extractor(self):
        """return (exe_path, tool_type) for the first usable archive extractor, or ("", "")"""
        import subprocess
        import shutil as _shutil
        for candidate, tool_type in self._EXTRACTOR_CANDIDATES:
            if tool_type == "winrar":
                # never run WinRAR to probe it — WinRAR.exe -? opens a GUI dialog
                # and blocks until dismissed, always timing out
                if os.path.isabs(candidate):
                    if Path(candidate).is_file():
                        return candidate, tool_type
                else:
                    resolved = _shutil.which(candidate)
                    if resolved:
                        return resolved, tool_type
                continue
            # 7-Zip: safe to run --help (prints to stdout and exits cleanly)
            try:
                result = subprocess.run(
                    [candidate, "--help"],
                    capture_output=True, timeout=5,
                )
                if result.returncode in (0, 1):
                    return candidate, tool_type
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                continue
        return "", ""

    _7ZR_URL = "https://github.com/ip7z/7zip/releases/latest/download/7zr.exe"

    def _download_7zr(self, log):
        """download standalone 7zr.exe (Windows only) or hint for Linux package manager."""
        if sys.platform != "win32":
            log("No archive extractor found on Linux. Install 7-Zip: sudo apt install p7zip-full")
            return ""
        import httpx
        dest = self.cache_dir / "7zr.exe"
        if dest.exists():
            return str(dest)
        try:
            log("No local archive extractor found — downloading 7zr.exe (~1 MB) as fallback...")
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                resp = client.get(self._7ZR_URL)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            log(f"Downloaded 7zr.exe ({len(resp.content):,} bytes)")
            return str(dest)
        except Exception as e:
            log(f"Failed to download 7zr.exe: {e}")
            return ""

    def _extract_with_subprocess(self, archive_data, tag, log, linux_native: bool = False):
        """fallback subprocess extraction.
        Linux .tar.bz2: uses system 'tar'. Windows .7z: uses 7-Zip or WinRAR.
        """
        import subprocess
        import shutil
        asset_name = LINUX_RELEASE_ASSET_NAME if linux_native else RELEASE_ASSET_NAME
        files_to_extract = {**LINUX_REQUIRED_FILES, **LINUX_TOOLS_FILES} if linux_native else {**REQUIRED_FILES, **TOOLS_FILES}
        archive_path = self.cache_dir / asset_name
        extract_dir  = self.cache_dir / "_extract_tmp"
        try:
            archive_path.write_bytes(archive_data)
            extract_dir.mkdir(exist_ok=True)
            # Linux: use system tar for .tar.bz2
            if linux_native:
                tar_exe = shutil.which("tar")
                if not tar_exe:
                    log("'tar' not found — install tar (usually pre-installed on Linux)")
                    return False
                cmd = [tar_exe, "xjf", str(archive_path), "-C", str(extract_dir)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    log(f"tar extraction failed: {result.stderr}")
                    return False
            else:
                # Windows: use 7-Zip or WinRAR
                exe, tool_type = self._find_extractor()
                if not exe:
                    exe = self._download_7zr(log)
                    tool_type = "7z"
                if not exe:
                    log("No archive extractor available — install 7-Zip or WinRAR")
                    return False
                tool_name = Path(exe).name
                log(f"Using {tool_name} ({tool_type}) for extraction")
                if tool_type == "7z":
                    cmd = [exe, "x", str(archive_path), f"-o{extract_dir}", "-y"]
                else:  # winrar
                    cmd = [exe, "x", "-y", str(archive_path), str(extract_dir) + "\\"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    log(f"{tool_name} extraction failed: {result.stderr}")
                    return False
            extracted_count = 0
            for dest_name, archive_path in files_to_extract.items():
                full = extract_dir / archive_path
                found = full if full.exists() else self._find_file(extract_dir, Path(archive_path).name)
                if found:
                    dest = self.cache_dir / dest_name
                    shutil.copy2(found, dest)
                    if dest_name.endswith(".so") or not '.' in dest_name:
                        dest.chmod(dest.stat().st_mode | 0o111)
                    extracted_count += 1
            (self.cache_dir / "version.txt").write_text(tag, encoding="utf-8")
            log(f"Extracted {extracted_count} files")
            return True
        except Exception as e:
            log(f"Subprocess extraction failed: {e}")
            return False
        finally:
            for p in (archive_path, self.cache_dir / "7zr.exe"):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                shutil.rmtree(extract_dir, ignore_errors=True)
            except Exception:
                pass
