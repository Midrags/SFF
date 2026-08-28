# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

spec_root = os.path.abspath(SPECPATH)
icon_path = os.path.join(spec_root, 'SFF.ico')

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
]

# Include only Windows-side third_party tools. Do not drag Linux .so folders
# into the Windows package, that made the installer fat and confusing.
third_party_dir = os.path.join(spec_root, 'third_party')
if os.path.exists(third_party_dir):
    for name in (
        'DDMod',
        'SteamAutoCrack',
        'coldloader',
        'fzf',
        'gbe_fork',
        'gbe_fork_tools',
        'hv',
        'rclone',
        'steamless',
    ):
        src = os.path.join(third_party_dir, name)
        if os.path.exists(src):
            datas.append((src, f'third_party/{name}'))

# DLC unlocker bundled resources (CreamAPI, SmokeAPI, Koaloader, UplayR1/R2 DLLs)
dlc_resources_dir = os.path.join(spec_root, 'sff', 'dlc_unlockers', 'resources')
if os.path.exists(dlc_resources_dir):
    datas.append((dlc_resources_dir, 'sff/dlc_unlockers/resources'))

if os.path.exists(os.path.join(spec_root, 'SFF.png')):
    datas.append(('SFF.png', '.'))
if os.path.exists(os.path.join(spec_root, 'SFF.ico')):
    datas.append(('SFF.ico', '.'))
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

# Include fallback depot keys database
fallback_db = os.path.join(spec_root, 'sff', 'lua', 'fallback_depotkeys.json')
if os.path.exists(fallback_db):
    datas.append((fallback_db, 'sff/lua'))

# Ludusavi save-path manifest used by Cloud Saves. Without it the custom
# save-path scan silently finds nothing and only Steam userdata is backed up.
sff_data_dir = os.path.join(spec_root, 'sff', 'data')
if os.path.isdir(sff_data_dir):
    datas.append((sff_data_dir, 'sff/data'))

# Include all_games.txt for offline game name resolution in Cloud Saves
all_games_txt = os.path.join(spec_root, 'all_games.txt')
if os.path.exists(all_games_txt):
    datas.append((all_games_txt, '.'))

# Bundle the offline store catalog (SteamTools GameList + steamappidlist
# name maps). Without this a fresh install has an empty Store until the
# GitHub mirrors are fetched — "Stray" and friends would not show up.
store_metadata_dir = os.path.join(spec_root, 'store_metadata')
if os.path.isdir(store_metadata_dir):
    datas.append((store_metadata_dir, 'store_metadata'))

# Include sff/webui/ folder (HTML/CSS/JS web UI assets)
webui_dir = os.path.join(spec_root, 'sff', 'webui')
if os.path.exists(webui_dir):
    datas.append((webui_dir, 'sff/webui'))

# Include c/ folder (MIDI player library, soundfont, and MIDI files)
c_dir = os.path.join(spec_root, 'c')
if os.path.exists(c_dir):
    datas.append((c_dir, 'c'))

win10toast_data = get_win10toast_data()
if win10toast_data:
    datas.append(win10toast_data)
    print(f"Including win10toast data from: {win10toast_data[0]}")

from PyInstaller.utils.hooks import collect_data_files
datas.extend(collect_data_files("rich", include_py_files=False))

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
        'PyQt6.QtWebChannel',
        'PyQt6.QtNetwork',
        'sff.single_instance',
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
        'sff.network.store_browser',
        'sff.image_cache',
        'sff.downloads.download_manager',

        'sff.cloud.cloud_saves',
        'sff.cloud.google_drive',
        'sff.core._gc',
        'google.auth',
        'google.auth.transport.requests',
        'google.oauth2.credentials',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'googleapiclient',
        'googleapiclient.discovery',
        'googleapiclient.http',
        'sff.ui.tray_icon',
        'sff.uri_handler',
        'sff.game.fix_game',
        'sff.game.fix_game.service',
        'sff.game.fix_game.cache',
        'sff.game.fix_game.goldberg_updater',
        'sff.game.fix_game.config_generator',
        'sff.game.fix_game.steamstub_unpacker',
        'sff.game.fix_game.goldberg_applier',
        'sff.game.fix_game.online_fix_applier',
        'sff.game.fix_game.gse_tool_updater',
        'sff.linux.steam_process',
        'sff.tools',
        'sff.tools.gbe_token_generator',
        'sff.tools.vdf_key_extractor',
        'py7zr',
        'rarfile',
        'sff.lumacore.lumacore_setup',
        'seleniumbase',
        'undetected_chromedriver',
        'zendriver',
        'zendriver.core',
        'zendriver.cdp',
        'zendriver.cdp.network',
        'bs4',
        'bs4.builder',
        'bs4.builder._html5lib',
        'bs4.builder._lxml',
        'bs4.builder._htmlparser',
        'rich._unicode_data',
        'rich.box',
        'rich.text',
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
    exclude_binaries=True,
    name='SteaMidra_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
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
    name='SteaMidra_GUI',
)
