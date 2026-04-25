# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

spec_root = os.path.abspath(SPECPATH)
icon_path = os.path.join(spec_root, 'sff.ico')

def get_win10toast_data():
    try:
        import win10toast
        win10toast_dir = os.path.dirname(win10toast.__file__)
        data_dir = os.path.join(win10toast_dir, 'data')
        if os.path.exists(data_dir):
            return (data_dir, 'win10toast/data')
    except Exception as e:
        print(f"Warning: Could not find win10toast data: {e}")
    return None

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

if os.path.exists(os.path.join(spec_root, 'sff.png')):
    datas.append(('sff.png', '.'))
if os.path.exists(os.path.join(spec_root, 'sff.ico')):
    datas.append(('sff.ico', '.'))
gui_resources = os.path.join(spec_root, 'sff', 'gui', 'resources')
if os.path.exists(gui_resources):
    datas.append((gui_resources, 'sff/gui/resources'))

# Include locale files for multi-language support
locales_dir = os.path.join(spec_root, 'sff', 'locales')
if os.path.exists(locales_dir):
    datas.append((locales_dir, 'sff/locales'))

# Include fallback depot keys/tokens from sff/lua/
lua_dir = os.path.join(spec_root, 'sff', 'lua')
if os.path.exists(lua_dir):
    datas.append((lua_dir, 'sff/lua'))

# Include fallback depot keys database if present at sff/ level
fallback_db = os.path.join(spec_root, 'sff', 'fallback_depotkeys.json')
if os.path.exists(fallback_db):
    datas.append((fallback_db, 'sff'))

# Include all_games.txt for offline game name resolution in Cloud Saves
all_games_txt = os.path.join(spec_root, 'all_games.txt')
if os.path.exists(all_games_txt):
    datas.append((all_games_txt, '.'))

# Include c/ folder (MIDI player library, soundfont, and MIDI files)
c_dir = os.path.join(spec_root, 'c')
if os.path.exists(c_dir):
    datas.append((c_dir, 'c'))

win10toast_data = get_win10toast_data()
if win10toast_data:
    datas.append(win10toast_data)
    print(f"Including win10toast data from: {win10toast_data[0]}")

a = Analysis(
    ['Main_gui.py'],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
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
        'psutil',
        'colorama',
        'httpx',
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
        'keyrings',
        'keyrings.alt',
        'keyrings.alt.file',
        'nacl',
        'nacl.exceptions',
        'nacl.secret',
        'nacl.encoding',
        'pynacl',
        'cryptography',
        'win10toast',
        'sff.store_browser',
        'sff.image_cache',
        'sff.download_manager',

        'sff.cloud_saves',
        'sff.tray_icon',
        'sff.uri_handler',
        'sff.fix_game',
        'sff.fix_game.service',
        'sff.fix_game.cache',
        'sff.fix_game.goldberg_updater',
        'sff.fix_game.config_generator',
        'sff.fix_game.steamstub_unpacker',
        'sff.fix_game.goldberg_applier',
        'sff.fix_game.online_fix_applier',
        'sff.fix_game.gse_tool_updater',
        'sff.linux.steam_process',
        'sff.tools',
        'sff.tools.gbe_token_generator',
        'sff.tools.vdf_key_extractor',
        'sff.tools.capcom_save_fix',
        'py7zr',
        'seleniumbase',
        'undetected_chromedriver',
        'bs4',
        'bs4.builder',
        'bs4.builder._html5lib',
        'bs4.builder._lxml',
        'bs4.builder._htmlparser',
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
    name='SteaMidra_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)
