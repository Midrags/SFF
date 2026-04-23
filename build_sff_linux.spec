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
import glob as _glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

spec_root = os.path.abspath(SPECPATH)
icon_path  = os.path.join(spec_root, 'SFF.png')

# ── PyQt6 / WebEngine — must use collect_all, NOT just hiddenimports ──────────
# hiddenimports only works for pure-Python modules.
# PyQt6 is a compiled C extension with Qt shared libraries that require
# collect_all() to be properly bundled into the output directory.
_qt6  = collect_all('PyQt6')
_wec  = collect_all('PyQt6.QtWebEngineCore')
_wew  = collect_all('PyQt6.QtWebEngineWidgets')

_qt_datas    = _qt6[0] + _wec[0] + _wew[0]
_qt_binaries = _qt6[1] + _wec[1] + _wew[1]
_qt_hidden   = _qt6[2] + _wec[2] + _wew[2]

# ── Data files ────────────────────────────────────────────────────────────────
datas = [
    ('static', 'static'),
] + _qt_datas

# third_party tools (gbe_fork, linux deps, etc.)
third_party_dir = os.path.join(spec_root, 'third_party')
if os.path.exists(third_party_dir):
    datas.append((third_party_dir, 'third_party'))

# DLC unlocker bundled resources (CreamAPI, SmokeAPI, Koaloader, UplayR1/R2 DLLs)
dlc_resources_dir = os.path.join(spec_root, 'sff', 'dlc_unlockers', 'resources')
if os.path.exists(dlc_resources_dir):
    datas.append((dlc_resources_dir, 'sff/dlc_unlockers/resources'))

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

# ── Bundle system libs required by Qt6WebEngine ──────────────────────────────
# pyqt6-webengine-qt6 (PyPI) links against these system libs at compile time
# but does NOT ship them. Bundle them here so the AppImage is self-contained
# and end users need zero additional installs (just like the Windows EXE).
#
# Build machine requirement (one-time, developer only):
#   sudo apt install libatomic1 libnss3 libnspr4 libxkbfile1 \
#       libxkbcommon-x11-0 libxcb-cursor0 libxcb-xkb1 libxcb-image0 \
#       libxcb-keysyms1 libxcb-util1 libxcb-render-util0 libxcb-icccm4 \
#       libxcb-shape0 libasound2

_SYSLIB_BASE = '/usr/lib/x86_64-linux-gnu'

def _find_syslib(pattern):
    """Return up to 1 (path, dest_dir) tuple for a system library glob."""
    # Try exact versioned name first, then glob
    hits = (
        _glob.glob(f'{_SYSLIB_BASE}/{pattern}') +
        _glob.glob(f'{_SYSLIB_BASE}/{pattern}.*')
    )
    return [(_p, '.') for _p in hits[:1]]

_syslib_binaries = []
_missing = []

for _lib, _pkg in [
    # GCC atomics — needed by libQt6WebEngineCore, libQt6Pdf, libavcodec
    ('libatomic.so.1',              'libatomic1'),
    # NSS/NSPR — needed by Chromium (QtWebEngine) for SSL/TLS
    ('libnss3.so',                  'libnss3'),
    ('libnssutil3.so',              'libnss3'),
    ('libsmime3.so',                'libnss3'),
    ('libnspr4.so',                 'libnspr4'),
    ('libplc4.so',                  'libnspr4'),
    ('libplds4.so',                 'libnspr4'),
    # X11 keyboard handling
    ('libxkbfile.so.1',             'libxkbfile1'),
    ('libxkbcommon-x11.so.0',       'libxkbcommon-x11-0'),
    # XCB extensions (required by the xcb QPA platform plugin)
    ('libxcb-cursor.so.0',          'libxcb-cursor0'),
    ('libxcb-xkb.so.1',             'libxcb-xkb1'),
    ('libxcb-image.so.0',           'libxcb-image0'),
    ('libxcb-keysyms.so.1',         'libxcb-keysyms1'),
    ('libxcb-util.so.1',            'libxcb-util1'),
    ('libxcb-render-util.so.0',     'libxcb-render-util0'),
    ('libxcb-icccm.so.4',           'libxcb-icccm4'),
    ('libxcb-shape.so.0',           'libxcb-shape0'),
    # ALSA audio (optional but avoids startup crashes on some Qt builds)
    ('libasound.so.2',              'libasound2'),
]:
    _found = _find_syslib(_lib)
    if _found:
        _syslib_binaries += _found
    else:
        _missing.append((_lib, _pkg))

if _missing:
    print('\nWARNING: The following system libs were NOT found on this build machine.')
    print('         The AppImage will be missing them and may crash on target systems.')
    print('         Fix with:')
    print('           sudo apt install ' + ' '.join(p for _, p in _missing))
    for _lib, _ in _missing:
        print(f'  - {_lib}')

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['Main_gui.py'],
    pathex=[spec_root],
    binaries=_qt_binaries + _syslib_binaries,
    datas=datas,
    hiddenimports=_qt_hidden + [
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
