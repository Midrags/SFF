# -*- mode: python ; coding: utf-8 -*-
# SteaMidra Build Configuration
#
# Expected warnings you can ignore:
# - "pkg_resources is deprecated" from win10toast / PyInstaller: from dependencies; build is fine.
# - "Hidden import tzdata not found": optional timezone data; safe to ignore unless you use timezone features.

import os
import sys
from pathlib import Path

block_cipher = None

# Get the directory where this spec file is located (where Main.py, sff.ico, etc. live)
spec_root = os.path.abspath(SPECPATH)
icon_path = os.path.join(spec_root, 'sff.ico')

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

# Bundle Chrome for Testing so SteamDB scraping works without a download
_chrome_dir = os.path.join(os.environ.get('USERPROFILE', ''), '.sff', 'chrome-for-testing', 'chrome-win64')
if os.path.exists(_chrome_dir):
    datas.append((_chrome_dir, 'chrome-bundled'))
    print(f"Bundling Chrome for Testing from: {_chrome_dir}")
else:
    print("WARNING: Chrome for Testing not found at ~/.sff/chrome-for-testing/chrome-win64 — SteamDB scraping will auto-download at runtime")

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
if os.path.exists(os.path.join(spec_root, 'sff.png')):
    datas.append(('sff.png', '.'))
if os.path.exists(os.path.join(spec_root, 'sff.ico')):
    datas.append(('sff.ico', '.'))

# Include all_games.txt for offline game name resolution in Cloud Saves
all_games_txt = os.path.join(spec_root, 'all_games.txt')
if os.path.exists(all_games_txt):
    datas.append((all_games_txt, '.'))

# Add win10toast data
win10toast_data = get_win10toast_data()
if win10toast_data:
    datas.append(win10toast_data)
    print(f"Including win10toast data from: {win10toast_data[0]}")

a = Analysis(
    ['Main.py'],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
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
        # pkg_resources.py2_warn / pkg_resources.markers removed: not present in newer setuptools
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SteaMidra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # IMPORTANT: Must be True for interactive prompts!
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)
