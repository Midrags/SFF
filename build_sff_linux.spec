# -*- mode: python ; coding: utf-8 -*-
# SteaMidra Linux Build Configuration
#
# Builds the GUI version (Main_gui.py) in onedir mode.
# onedir is recommended for AppImage packaging — no /tmp extraction on launch.
#
# Usage (on Linux Mint / Ubuntu / Debian):
#   pip install pyinstaller
#   pyinstaller build_sff_linux.spec
#
# Output: dist/SteaMidra_GUI/   (directory — use as AppDir/usr/bin/ content)

import os
import sys
from pathlib import Path

block_cipher = None

spec_root = os.path.abspath(SPECPATH)
icon_path  = os.path.join(spec_root, 'SFF.png')

# ── Data files ────────────────────────────────────────────────────────────────
datas = [
    ('static', 'static'),
]

# third_party tools (gbe_fork, linux deps, online_fix DLLs, etc.)
third_party_dir = os.path.join(spec_root, 'third_party')
if os.path.exists(third_party_dir):
    datas.append((third_party_dir, 'third_party'))

# Icon
if os.path.exists(os.path.join(spec_root, 'SFF.png')):
    datas.append(('SFF.png', '.'))

# GUI resources
gui_resources = os.path.join(spec_root, 'sff', 'gui', 'resources')
if os.path.exists(gui_resources):
    datas.append((gui_resources, 'sff/gui/resources'))

# Locales
locales_dir = os.path.join(spec_root, 'sff', 'locales')
if os.path.exists(locales_dir):
    datas.append((locales_dir, 'sff/locales'))

# Lua / depot keys
lua_dir = os.path.join(spec_root, 'sff', 'lua')
if os.path.exists(lua_dir):
    datas.append((lua_dir, 'sff/lua'))

fallback_db = os.path.join(spec_root, 'sff', 'fallback_depotkeys.json')
if os.path.exists(fallback_db):
    datas.append((fallback_db, 'sff'))

c_dir = os.path.join(spec_root, 'c')
if os.path.exists(c_dir):
    datas.append((c_dir, 'c'))

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['Main_gui.py'],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Qt / GUI
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        # Prompts / CLI utils (used in sff modules)
        'prompt_toolkit',
        'colorama',
        # Networking
        'httpx',
        'requests',
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
        'seleniumbase',
        'undetected_chromedriver',
        # Steam / manifests
        'steam',
        'steam.client',
        'gevent',
        'vdf',
        'msgpack',
        # SteaMidra modules
        'sff.manifest.collections',
        'sff.manifest.workshop_tracker',
        'sff.fix_game',
        'sff.fix_game.service',
        'sff.fix_game.cache',
        'sff.fix_game.goldberg_updater',
        'sff.fix_game.config_generator',
        'sff.fix_game.steamstub_unpacker',
        'sff.fix_game.goldberg_applier',
        'sff.fix_game.online_fix_applier',
        'sff.fix_game.gse_tool_updater',
        'sff.linux',
        'sff.linux.dotnet',
        'sff.linux.depot_downloader',
        'sff.linux.permissions',
        'sff.linux.steamless',
        'sff.linux.acf_writer',
        'sff.linux.slscheevo',
        'sff.linux.slssteam',
        'sff.linux.linux_download',
        'sff.linux.steam_process',
        'sff.cloud_saves',
        'sff.image_cache',
        'sff.download_manager',
        'sff.store_browser',
        'sff.tray_icon',
        'sff.uri_handler',
        'sff.tools',
        'sff.tools.gbe_token_generator',
        'sff.tools.vdf_key_extractor',
        'sff.tools.capcom_save_fix',
        # Misc
        'psutil',
        'keyring',
        'keyring.backends',
        'keyrings',
        'keyrings.alt',
        'keyrings.alt.file',
        'nacl',
        'nacl.exceptions',
        'nacl.secret',
        'nacl.encoding',
        'pynacl',
        'bs4',
        'bs4.builder',
        'bs4.builder._html5lib',
        'bs4.builder._lxml',
        'bs4.builder._htmlparser',
        'py7zr',
        'rich',
        'rich.console',
        'rich.table',
        'yaml',
        'tqdm',
        'pathvalidate',
        'configupdater',
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
        # Windows-only — not available on Linux
        'win10toast',
        'winreg',
        'winsound',
        'msvcrt',
        'pywin32',
        'pywin32_ctypes',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── onedir EXE (no single-file extraction overhead) ───────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SteaMidra_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
