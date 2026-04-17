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
URI protocol handler for midra:// links.

Registers midra:// in Windows registry and processes incoming URIs.

Supported actions:
- midra://download/{appId}           — download manifest only
- midra://install/{appId}            — install from existing download
- midra://download/install/{appId}   — one-click download + install + auto-fix
"""

import os
import sys
import re
import logging
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PROTOCOL_NAME = "midra"
PROTOCOL_DESCRIPTION = "SteaMidra Protocol"

# regex for valid URIs
URI_REGEX = re.compile(
    r"^midra://(download(?:/install)?|install)/(\d+)$",
    re.IGNORECASE,
)


@dataclass
class ParsedUri:
    """parsed midra:// URI"""
    action: str       # "download", "install", or "download_install"
    app_id: int


class UriHandler:
    """
    Handles midra:// protocol registration and URI parsing.
    
    Registration puts a key in HKCU\\Software\\Classes\\midra
    that points to the running SteaMidra executable.
    """

    @staticmethod
    def register(exe_path = None):
        """
        Register the midra:// protocol in Windows registry.
        
        Uses HKCU so no admin rights needed.
        """
        if sys.platform != "win32":
            logger.warning("URI protocol registration only supported on Windows")
            return False

        if not exe_path:
            exe_path = sys.executable

        try:
            import winreg

            key_path = f"Software\\Classes\\{PROTOCOL_NAME}"

            # create the protocol key
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{PROTOCOL_DESCRIPTION}")
                winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

            # the icon
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\DefaultIcon") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}",1')

            # the command that runs when a midra:// link is clicked
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\shell\\open\\command") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}" "%1"')

            logger.info("Registered midra:// protocol handler -> %s", exe_path)
            return True

        except Exception as e:
            logger.error("Failed to register protocol: %s", e)
            return False

    @staticmethod
    def unregister():
        """remove the midra:// protocol registration"""
        if sys.platform != "win32":
            return False

        try:
            import winreg

            def _delete_key_recursive(hkey, path):
                try:
                    with winreg.OpenKey(hkey, path) as key:
                        while True:
                            try:
                                subkey = winreg.EnumKey(key, 0)
                                _delete_key_recursive(hkey, f"{path}\\{subkey}")
                            except OSError:
                                break
                    winreg.DeleteKey(hkey, path)
                except FileNotFoundError:
                    pass

            _delete_key_recursive(
                winreg.HKEY_CURRENT_USER,
                f"Software\\Classes\\{PROTOCOL_NAME}"
            )
            logger.info("Unregistered midra:// protocol handler")
            return True

        except Exception as e:
            logger.error("Failed to unregister protocol: %s", e)
            return False

    @staticmethod
    def is_registered():
        """check if midra:// is registered"""
        if sys.platform != "win32":
            return False

        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                f"Software\\Classes\\{PROTOCOL_NAME}"
            ):
                return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def parse_uri(uri):
        """
        Parse a midra:// URI into action + app ID.
        
        Examples:
            midra://download/12345        → ParsedUri("download", 12345)
            midra://install/12345         → ParsedUri("install", 12345)
            midra://download/install/12345 → ParsedUri("download_install", 12345)
        
        Returns None if the URI is invalid.
        """
        uri = uri.strip()

        match = URI_REGEX.match(uri)
        if not match:
            logger.warning("Invalid midra:// URI: %s", uri)
            return None

        action_str = match.group(1).lower()
        app_id = int(match.group(2))

        # normalize action
        if action_str == "download/install":
            action = "download_install"
        elif action_str == "download":
            action = "download"
        elif action_str == "install":
            action = "install"
        else:
            return None

        return ParsedUri(action=action, app_id=app_id)

    @staticmethod
    def check_args_for_uri():
        """
        Check sys.argv for a midra:// URI (passed when clicking a link).
        Returns the parsed URI if found, None otherwise.
        """
        for arg in sys.argv[1:]:
            if arg.lower().startswith("midra://"):
                return UriHandler.parse_uri(arg)
        return None
