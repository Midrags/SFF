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
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/Detanup01/gbe_fork/releases/latest"
RELEASE_ASSET_NAME = "emu-win-release.7z"

# files we need from the release archive
REQUIRED_FILES = {
    # regular mode
    "steam_api.dll": "release/steam_api.dll",
    "steam_api64.dll": "release/steam_api64.dll",
    # coldclient mode
    "steamclient.dll": "release/steamclient.dll",
    "steamclient64.dll": "release/steamclient64.dll",
    "steamclient_loader_x32.exe": "release/steamclient_loader_x32.exe",
    "steamclient_loader_x64.exe": "release/steamclient_loader_x64.exe",
    # extra DLLs for coldclient injection
    "steamclient_extra_x32.dll": "release/extra_dlls/steamclient_extra_x32.dll",
    "steamclient_extra_x64.dll": "release/extra_dlls/steamclient_extra_x64.dll",
}

# generate_interfaces tool
TOOLS_FILES = {
    "generate_interfaces_x32.exe": "release/tools/generate_interfaces_x32.exe",
    "generate_interfaces_x64.exe": "release/tools/generate_interfaces_x64.exe",
}


class GoldbergUpdater:
    """
    Auto-downloads and caches the latest Goldberg emulator (gbe_fork).
    
    Checks GitHub releases API, compares with cached version,
    downloads emu-win-release.7z if outdated, and extracts all needed files.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_version(self) -> Optional[str]:
        """get the currently cached version tag"""
        version_file = self.cache_dir / "version.txt"
        try:
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return None

    def get_latest_version(self) -> Optional[tuple[str, str]]:
        """
        Check GitHub for the latest release.
        Returns (tag_name, download_url) or None on failure.
        """
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
                    if asset.get("name", "") == RELEASE_ASSET_NAME:
                        return (tag, asset["browser_download_url"])

                # fallback: look for any 7z asset
                for asset in assets:
                    name = asset.get("name", "")
                    if name.endswith(".7z") and "win" in name.lower():
                        return (tag, asset["browser_download_url"])

                logger.warning("No suitable asset found in gbe_fork release %s", tag)
                return None

        except Exception as e:
            logger.error("Failed to check gbe_fork releases: %s", e)
            return None

    def needs_update(self) -> bool:
        """check if we need to download a newer version"""
        cached = self.get_cached_version()
        if not cached:
            return True

        latest = self.get_latest_version()
        if not latest:
            return False  # can't check, assume we're fine

        return cached != latest[0]

    def ensure_goldberg(self, force_update: bool = False, log_func=None) -> bool:
        """
        Make sure we have the latest Goldberg DLLs cached.
        Downloads and extracts if needed.
        
        Returns True if DLLs are available.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)

        # check if we already have DLLs and are up to date
        has_dlls = all(
            (self.cache_dir / name).exists()
            for name in ["steam_api.dll", "steam_api64.dll"]
        )

        if has_dlls and not force_update:
            cached_ver = self.get_cached_version()
            if cached_ver:
                log(f"Goldberg {cached_ver} already cached")
                return True

        # check latest version
        log("Checking for latest Goldberg emulator...")
        latest = self.get_latest_version()
        if not latest:
            log("Could not check GitHub releases")
            return has_dlls  # if we have old DLLs, use them

        tag, download_url = latest
        cached_ver = self.get_cached_version()

        if cached_ver == tag and has_dlls and not force_update:
            log(f"Goldberg {tag} is up to date")
            return True

        log(f"Downloading Goldberg {tag}...")
        return self._download_and_extract(tag, download_url, log)

    def _download_and_extract(self, tag: str, url: str, log) -> bool:
        """download the 7z archive and extract needed files"""
        try:
            # download the archive
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                archive_data = resp.content

            log(f"Downloaded {len(archive_data)} bytes, extracting...")

            # extract with py7zr
            try:
                import py7zr
            except ImportError:
                log("py7zr not installed, trying fallback extraction...")
                return self._extract_with_subprocess(archive_data, tag, log)

            with py7zr.SevenZipFile(io.BytesIO(archive_data), mode='r') as archive:
                all_files = archive.getnames()
                log(f"Archive contains {len(all_files)} files")

                # extract everything to a temp location first
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    archive.extractall(path=tmpdir)

                    extracted_count = 0
                    tmppath = Path(tmpdir)

                    # find and copy required files
                    for dest_name, src_pattern in {**REQUIRED_FILES, **TOOLS_FILES}.items():
                        # search for the file in extracted content
                        found = self._find_file(tmppath, dest_name)
                        if found:
                            dest = self.cache_dir / dest_name
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            import shutil
                            shutil.copy2(found, dest)
                            extracted_count += 1
                        else:
                            logger.debug("File not found in archive: %s", dest_name)

                    log(f"Extracted {extracted_count} files")

            # save version
            (self.cache_dir / "version.txt").write_text(tag, encoding="utf-8")
            log(f"Goldberg {tag} cached successfully")
            return True

        except Exception as e:
            logger.error("Failed to download/extract Goldberg: %s", e)
            log(f"Error: {e}")
            return False

    def _find_file(self, search_dir: Path, filename: str) -> Optional[Path]:
        """recursively find a file by name in a directory"""
        for path in search_dir.rglob(filename):
            if path.is_file():
                return path
        return None

    def _extract_with_subprocess(self, archive_data: bytes, tag: str, log) -> bool:
        """fallback: write to temp file and extract with 7z.exe"""
        import tempfile
        import subprocess
        import shutil

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                archive_path = Path(tmpdir) / RELEASE_ASSET_NAME
                archive_path.write_bytes(archive_data)

                extract_dir = Path(tmpdir) / "extracted"
                extract_dir.mkdir()

                # try 7z.exe
                result = subprocess.run(
                    ["7z", "x", str(archive_path), f"-o{extract_dir}", "-y"],
                    capture_output=True, text=True, timeout=120
                )

                if result.returncode != 0:
                    log(f"7z extraction failed: {result.stderr}")
                    return False

                extracted_count = 0
                for dest_name in {**REQUIRED_FILES, **TOOLS_FILES}:
                    found = self._find_file(extract_dir, dest_name)
                    if found:
                        dest = self.cache_dir / dest_name
                        shutil.copy2(found, dest)
                        extracted_count += 1

                (self.cache_dir / "version.txt").write_text(tag, encoding="utf-8")
                log(f"Extracted {extracted_count} files via 7z.exe")
                return True

        except FileNotFoundError:
            log("7z.exe not found - install py7zr (pip install py7zr) or put 7z.exe in PATH")
            return False
        except Exception as e:
            log(f"Subprocess extraction failed: {e}")
            return False
