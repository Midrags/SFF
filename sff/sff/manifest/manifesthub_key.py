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

"""ManifestHub API key cache with auto-renewal (24 h validity)."""

import logging
import threading
import time
import webbrowser

from sff.prompts import prompt_text

logger = logging.getLogger(__name__)

_KEY_URL = "https://manifesthub1.filegear-sg.me"
_EXPIRY_SECONDS = 86_400  # 24 h
_renewal_lock = threading.Lock()


def _key_is_valid():
    from sff.storage.settings import get_setting
    from sff.structs import Settings

    key = get_setting(Settings.MANIFESTHUB_API_KEY)
    expiry_str = get_setting(Settings.MANIFESTHUB_KEY_EXPIRY)
    if not key or not expiry_str:
        return False
    try:
        return time.time() < float(expiry_str)
    except (ValueError, TypeError):
        return False


def _save_key(key):
    from sff.storage.settings import set_setting
    from sff.structs import Settings

    set_setting(Settings.MANIFESTHUB_API_KEY, key)
    set_setting(Settings.MANIFESTHUB_KEY_EXPIRY, str(time.time() + _EXPIRY_SECONDS))


def get_manifesthub_api_key():
    """Get a valid key; opens the generator page in the user's browser if renewal needed."""
    from sff.storage.settings import get_setting
    from sff.structs import Settings

    if _key_is_valid():
        return get_setting(Settings.MANIFESTHUB_API_KEY)

    with _renewal_lock:
        # Re-check inside lock — another parallel thread may have already renewed.
        if _key_is_valid():
            return get_setting(Settings.MANIFESTHUB_API_KEY)
        had_key = get_setting(Settings.MANIFESTHUB_API_KEY) is not None
        if had_key:
            print(f"ManifestHub API key expired. Opening renewal page: {_KEY_URL}")
        else:
            print(f"ManifestHub API key needed. Opening key generator: {_KEY_URL}")
        # Opens URL in the user's default/active browser — one tab, no flicker.
        webbrowser.open(_KEY_URL)
        pasted = prompt_text(
            "Paste your ManifestHub API key (leave blank to skip): "
        ).strip()
        if pasted:
            _save_key(pasted)
            return pasted
        return None
