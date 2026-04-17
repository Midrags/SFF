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
Config VDF key extractor — reads depot decryption keys from Steam's config.vdf.

Extracts depot keys in "depot_id;key" format for use with DepotDownloader.
Validates key format (64-char hex) and deduplicates against existing files.

Mirrors Solus VdfKeyExtractor.cs (208 lines).
"""

import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# regex to find depot keys in config.vdf
# format:     "123456"
#             {
#                 "DecryptionKey"    "hex64chars"
#             }
DEPOT_KEY_REGEX = re.compile(
    r'"(\d+)"\s*\{[^}]*"DecryptionKey"\s+"([0-9a-fA-F]+)"',
    re.MULTILINE | re.DOTALL,
)

# alternate flat format: "depot_id" { "DecryptionKey" "key" }
DEPOT_KEY_FLAT_REGEX = re.compile(
    r'"(\d+)"\s*\{\s*"DecryptionKey"\s*"([0-9a-fA-F]{64})"',
    re.MULTILINE,
)


@dataclass
class DepotKey:
    """a depot decryption key"""
    depot_id: str
    key: str

    def __str__(self):
        return f"{self.depot_id};{self.key}"

    def __eq__(self, other):
        return self.depot_id == other.depot_id and self.key.lower() == other.key.lower()

    def __hash__(self):
        return hash((self.depot_id, self.key.lower()))


@dataclass
class ExtractionResult:
    """result of a key extraction"""
    keys: list = field(default_factory=list)
    new_keys: list = field(default_factory=list)  # keys not in existing file
    errors: list = field(default_factory=list)
    source_path = ""


class VdfKeyExtractor:
    """
    Extracts depot decryption keys from Steam's config.vdf file.
    
    Usage:
        extractor = VdfKeyExtractor()
        result = extractor.extract_keys()
        for key in result.keys:
            print(f"{key.depot_id};{key.key}")
    """

    @staticmethod
    def get_default_steam_config_path():
        """get the default config.vdf path from Steam's install dir"""
        candidates = [
            r"C:\Program Files (x86)\Steam\config\config.vdf",
            r"C:\Program Files\Steam\config\config.vdf",
        ]

        # also try registry
        try:
            import winreg
            for key_path in [
                r"SOFTWARE\Valve\Steam",
                r"SOFTWARE\WOW6432Node\Valve\Steam",
            ]:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        vdf_path = os.path.join(install_path, "config", "config.vdf")
                        if os.path.exists(vdf_path):
                            return vdf_path
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass

        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def validate_depot_key(key):
        """check if a key is valid (64 hex characters)"""
        if not key or len(key) != 64:
            return False
        try:
            int(key, 16)
            return True
        except ValueError:
            return False

    def extract_keys(
        self,
        vdf_path = None,
        existing_keys_path = None,
    ):
        """
        Extract depot keys from config.vdf.
        
        Args:
            vdf_path: path to config.vdf (auto-detected if None)
            existing_keys_path: optional path to existing keys file for dedup
        
        Returns ExtractionResult with all found keys.
        """
        result = ExtractionResult()

        # find config.vdf
        if not vdf_path:
            vdf_path = self.get_default_steam_config_path()
        if not vdf_path or not os.path.exists(vdf_path):
            result.errors.append("config.vdf not found")
            return result

        result.source_path = vdf_path

        # read the file
        try:
            content = Path(vdf_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result.errors.append(f"Failed to read {vdf_path}: {e}")
            return result

        # extract keys using both regex patterns
        found_keys = set()

        for match in DEPOT_KEY_REGEX.finditer(content):
            depot_id = match.group(1)
            key = match.group(2)
            if self.validate_depot_key(key):
                found_keys.add(DepotKey(depot_id, key))
            else:
                result.errors.append(f"Invalid key for depot {depot_id}: {key[:10]}...")

        for match in DEPOT_KEY_FLAT_REGEX.finditer(content):
            depot_id = match.group(1)
            key = match.group(2)
            if self.validate_depot_key(key):
                found_keys.add(DepotKey(depot_id, key))

        result.keys = sorted(found_keys, key=lambda k: int(k.depot_id))

        # deduplicate against existing file
        if existing_keys_path and os.path.exists(existing_keys_path):
            existing = self._load_existing_keys(existing_keys_path)
            result.new_keys = [k for k in result.keys if k not in existing]
        else:
            result.new_keys = list(result.keys)

        return result

    def _load_existing_keys(self, path):
        """load keys from an existing keys file (depot_id;key format)"""
        keys = set()
        try:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if ";" in line:
                    parts = line.split(";", 1)
                    if len(parts) == 2 and parts[0].isdigit():
                        keys.add(DepotKey(parts[0], parts[1]))
        except Exception as e:
            logger.warning("Failed to load existing keys: %s", e)
        return keys

    @staticmethod
    def format_keys_as_text(keys):
        """format keys as "depot_id;key" lines"""
        return "\n".join(str(k) for k in keys)

    def save_keys(self, keys, output_path):
        """save keys to a file"""
        Path(output_path).write_text(
            self.format_keys_as_text(keys), encoding="utf-8"
        )
        logger.info("Saved %d keys to %s", len(keys), output_path)
