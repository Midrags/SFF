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
    # Include static files
    ('static', 'static'),
    # Include third party tools
    ('third_party', 'third_party'),
    # Include C folder (music/MIDI files and DLLs)
    ('c', 'c'),
]

# Add icon assets if they exist
if os.path.exists(os.path.join(spec_root, 'sff.png')):
    datas.append(('sff.png', '.'))
if os.path.exists(os.path.join(spec_root, 'sff.ico')):
    datas.append(('sff.ico', '.'))

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
        'psutil',
        'colorama',
        'httpx',
        'keyring',
        'cryptography',
        'win10toast',
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # IMPORTANT: Must be True for interactive prompts!
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)
