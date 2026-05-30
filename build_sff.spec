# -*- mode: python ; coding: utf-8 -*-
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
#
# SteaMidra Build Configuration
#
# Expected warnings you can ignore:
# - "pkg_resources is deprecated" from win10toast / PyInstaller: from dependencies; build is fine.
# - "Hidden import tzdata not found": optional timezone data; safe to ignore unless you use timezone features.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None


def _validate_rich_packaging(hidden_imports, data_entries):
    """Abort the build before Analysis runs if rich packaging is incomplete.

    The frozen DLC check loads `rich._unicode_data` lazily; missing it has
    crashed users in the past. The validator catches the regression at spec
    load time so a bad spec never produces an artifact.
    """
    required_hidden = ("rich._unicode_data", "rich.box", "rich.text")
    missing_hidden = [name for name in required_hidden if name not in hidden_imports]
    if missing_hidden:
        raise SystemExit(
            "build_sff.spec validation failed: hiddenimports is missing "
            + ", ".join(missing_hidden)
        )

    has_rich_data = False
    for entry in data_entries:
        if isinstance(entry, tuple) and len(entry) == 2:
            src, dst = entry
            if "rich" in str(src) or "rich" in str(dst):
                has_rich_data = True
                break
    if not has_rich_data:
        raise SystemExit(
            "build_sff.spec validation failed: collect_data_files('rich', "
            "include_py_files=False) must contribute to datas"
        )


# Get the directory where this spec file is located (where Main.py, sff.ico, etc. live)
spec_root = os.path.abspath(SPECPATH)
icon_path = os.path.join(spec_root, 'SFF.ico')

# Find win10toast data directory
def get_win10toast_data():
    """Get win10toast data directory for inclusion"""
    try:
        import win10toast
        win10toast_dir = os.path.dirname(win10toast.__file__)
        data_dir = os.path.join(win10toast_dir, 'data')
        if os.path.exists(data_dir):
            return (data_dir, 'win10toast/data')
    except Exception as e:
        print(f"Warning: Could not find win10toast data: {e}")
    return None

# Collect data files
datas = [
    ('static', 'static'),
]

# Include third_party tools if present
third_party_dir = os.path.join(spec_root, 'third_party')
if os.path.exists(third_party_dir):
    datas.append((third_party_dir, 'third_party'))

# DLC unlocker bundled resources (CreamAPI, SmokeAPI, Koaloader, UplayR1/R2 DLLs)
dlc_resources_dir = os.path.join(spec_root, 'sff', 'dlc_unlockers', 'resources')
if os.path.exists(dlc_resources_dir):
    datas.append((dlc_resources_dir, 'sff/dlc_unlockers/resources'))

# Lua depot keys / tokens (required for manifest depot key operations)
lua_dir = os.path.join(spec_root, 'sff', 'lua')
if os.path.exists(lua_dir):
    datas.append((lua_dir, 'sff/lua'))

# MIDI player library, soundfont, and MIDI files
c_dir = os.path.join(spec_root, 'c')
if os.path.exists(c_dir):
    datas.append((c_dir, 'c'))

# Add icon assets if they exist
if os.path.exists(os.path.join(spec_root, 'SFF.png')):
    datas.append(('SFF.png', '.'))
if os.path.exists(os.path.join(spec_root, 'SFF.ico')):
    datas.append(('SFF.ico', '.'))

# Include all_games.txt for offline game name resolution in Cloud Saves
all_games_txt = os.path.join(spec_root, 'all_games.txt')
if os.path.exists(all_games_txt):
    datas.append((all_games_txt, '.'))

# Add win10toast data
win10toast_data = get_win10toast_data()
if win10toast_data:
    datas.append(win10toast_data)
    print(f"Including win10toast data from: {win10toast_data[0]}")

# Bundle the rich package's data files (including _unicode_data tables) so the
# DLC check path stays import-clean inside the frozen build.
datas.extend(collect_data_files("rich", include_py_files=False))

hiddenimports = [
    'InquirerPy',
    'prompt_toolkit',
    'selenium',
    'selenium.webdriver',
    'selenium.webdriver.chrome',
    'selenium.webdriver.chrome.service',
    'selenium.webdriver.chrome.options',
    'selenium.webdriver.common.by',
    'selenium.webdriver.common.keys',
    'selenium.webdriver.support',
    'selenium.webdriver.support.ui',
    'selenium.webdriver.support.expected_conditions',
    'selenium.common.exceptions',
    'steam',
    'steam.client',
    'gevent',
    'sff.manifest.collections',
    'sff.manifest.workshop_tracker',
    'sff.cloud_saves',
    'sff.google_drive',
    'sff._gc',
    'google.auth',
    'google.auth.transport.requests',
    'google.oauth2.credentials',
    'google_auth_oauthlib',
    'google_auth_oauthlib.flow',
    'googleapiclient',
    'googleapiclient.discovery',
    'googleapiclient.http',
    'sff.fix_game.online_fix_applier',
    'sff.linux.steam_process',
    'psutil',
    'colorama',
    'httpx',
    'keyring',
    'cryptography',
    'win10toast',
    'seleniumbase',
    'undetected_chromedriver',
    'bs4',
    'bs4.builder',
    'bs4.builder._html5lib',
    'bs4.builder._lxml',
    'bs4.builder._htmlparser',
    'rich._unicode_data',
    'rich.box',
    'rich.text',
    # pkg_resources.py2_warn / pkg_resources.markers removed: not present in newer setuptools
]

_validate_rich_packaging(hiddenimports, datas)

a = Analysis(
    ['Main.py'],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='SteaMidra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=True,  # IMPORTANT: Must be True for interactive prompts!
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SteaMidra',
)
