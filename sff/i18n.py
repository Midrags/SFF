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
import json
import locale
import os
from pathlib import Path
from sff.utils import root_folder

# Find the locales folder relative to this file
LOCALES_DIR = root_folder() / "sff/locales"

def _load_language_file(language):
    file_path = LOCALES_DIR / f"{language}.json"
    if not file_path.exists():
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading translation for {language}: {e}")
        return {}


class Translator:
    def __init__(self, language = None):
        if not LOCALES_DIR.exists():
            try:
                LOCALES_DIR.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # Read-only fs (AppImage squashfs) — locales are bundled or fall back to keys
        if language in ["Auto", None, ""]:
            try:
                language_sys = locale.getdefaultlocale()[0]
                language_code = language_sys.split("_")[0] if language_sys else "en"
                language = language_code
            except Exception:
                language = "en"
        if not language:
            language = "en"
        # Check if full locale exists (e.g. pt_BR.json)
        if not (LOCALES_DIR / f"{language}.json").exists():
            # Try simple language code (e.g. pt.json)
            if "_" in language:
                language = language.split("_")[0]
            # If still not found, default to en
            if not (LOCALES_DIR / f"{language}.json").exists():
                language = "en"
        self.language = language
        self.language_map = _load_language_file(language)
        # Load English as fallback for missing keys
        if language != "en":
            self.fallback_map = _load_language_file("en")
        else:
            self.fallback_map = {}

    @property
    def locale(self):
        return self.language

    def __call__(self, key):
        if not key:
            return ""
        # Try primary language
        if key in self.language_map:
            return self.language_map[key]
        # Try fallback
        if key in self.fallback_map:
            return self.fallback_map[key]
        # Return key itself
        return key

    def __repr__(self):
        return "Translator Language: " + self.language

# Global instance initialized below, but can be updated on App start
_T = Translator("en")

def get_translator():
    return _T

def set_language(lang):
    global _T
    _T = Translator(lang)

def T(key):
    """Short-hand for translation calls"""
    return _T(key)
