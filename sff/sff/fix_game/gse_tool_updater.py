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
GSE Fork generate_emu_config auto-updater.

Downloads the latest generate_emu_config tool from alex47exe/gse_fork on GitHub
and stores it in the APPDATA gse_tool staging directory so it's available for
the Fix Game Advanced pipeline.

Used as a last-resort fallback when the bundled tool cannot be found — mirrors
the GoldbergUpdater pattern.
"""

import io
import logging
import os
import shutil
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/alex47exe/gse_fork/releases/latest"

_TOOL_EXE = "generate_emu_config.exe"
_VERSION_FILE = "gse_tool_version.txt"


def _staging_dir():
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return appdata / "SteaMidra" / "gse_tool"


class GseToolUpdater:
    """
    Auto-downloads the latest generate_emu_config.exe from alex47exe/gse_fork.

    Stored in %APPDATA%/SteaMidra/gse_tool/ — the same directory that
    FixGameService._run_gse_config() stages and runs the tool from.
    """

    def __init__(self):
        self.staging = _staging_dir()

    def get_staged_version(self):
        try:
            vf = self.staging / _VERSION_FILE
            if vf.exists():
                return vf.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return None

    def get_latest_release(self):
        """
        Query GitHub for the latest release.
        Returns (tag_name, zip_download_url) or None.
        """
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    RELEASES_URL,
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "SteaMidra/1.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            tag = data.get("tag_name", "")
            assets = data.get("assets", [])
            # look for a ZIP asset containing 'generate_emu_config' or 'gen_emu'
            for asset in assets:
                name = asset.get("name", "").lower()
                if "generate_emu_config" in name and name.endswith(".zip"):
                    return (tag, asset["browser_download_url"])
            # broader fallback: any zip that looks like a tool release
            for asset in assets:
                name = asset.get("name", "").lower()
                if ("gen_emu" in name or "emu_config" in name) and name.endswith(".zip"):
                    return (tag, asset["browser_download_url"])
            # last resort: first zip asset in the release
            for asset in assets:
                if asset.get("name", "").lower().endswith(".zip"):
                    return (tag, asset["browser_download_url"])
            logger.warning("No suitable ZIP asset found in gse_fork release %s", tag)
            return None
        except Exception as e:
            logger.error("Failed to check gse_fork releases: %s", e)
            return None

    def is_available(self):
        return (self.staging / _TOOL_EXE).exists()

    def needs_update(self):
        if not self.is_available():
            return True
        cached = self.get_staged_version()
        if not cached:
            return True
        latest = self.get_latest_release()
        if not latest:
            return False  # can't check; assume OK
        return cached != latest[0]

    def ensure_tool(self, force_update = False, log_func=None):
        """
        Make sure generate_emu_config.exe is available in the staging directory.
        Downloads from GitHub if missing or outdated.
        Returns True if the tool is available after this call.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            logger.info(msg)
        if self.is_available() and not force_update:
            cached_ver = self.get_staged_version()
            if cached_ver:
                log(f"GSE tool {cached_ver} already staged")
                return True
        log("Checking for latest generate_emu_config from alex47exe/gse_fork...")
        latest = self.get_latest_release()
        if not latest:
            log("Could not reach GitHub releases API")
            return self.is_available()  # use whatever we have
        tag, url = latest
        cached = self.get_staged_version()
        if cached == tag and self.is_available() and not force_update:
            log(f"GSE tool {tag} is up to date")
            return True
        log(f"Downloading GSE tool {tag} from {url}...")
        ok = self._download_and_extract(tag, url, log)
        if ok:
            return True
        log("Download failed — using previously staged tool if available")
        return self.is_available()

    def _download_and_extract(self, tag, url, log):
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                archive_data = resp.content
            log(f"Downloaded {len(archive_data):,} bytes")
        except Exception as e:
            log(f"Download error: {e}")
            logger.error("Failed to download gse_fork tool: %s", e)
            return False
        try:
            self.staging.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
                names = zf.namelist()
                log(f"Archive contains {len(names)} entries")
                # find generate_emu_config.exe inside the zip
                exe_entry = None
                for name in names:
                    if name.lower().endswith("generate_emu_config.exe"):
                        exe_entry = name
                        break
                if not exe_entry:
                    log("generate_emu_config.exe not found in archive")
                    return False
                # determine the prefix directory inside the zip
                prefix = "/".join(exe_entry.split("/")[:-1])
                extracted = 0
                for name in names:
                    if prefix and not name.startswith(prefix):
                        continue
                    rel = name[len(prefix):].lstrip("/") if prefix else name
                    if not rel:
                        continue
                    dest = self.staging / rel
                    if name.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(name))
                        extracted += 1
                log(f"Extracted {extracted} files to {self.staging}")
            (self.staging / _VERSION_FILE).write_text(tag, encoding="utf-8")
            log(f"GSE tool {tag} downloaded and staged successfully")
            return True
        except Exception as e:
            log(f"Extraction error: {e}")
            logger.error("Failed to extract gse_fork tool: %s", e)
            return False
