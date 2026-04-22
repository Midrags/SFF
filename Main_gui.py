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

import logging
import os
import sys
from pathlib import Path

import PyQt6.QtWebEngineWidgets  # noqa: F401 - must import before QCoreApplication
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from sff.steam_path import validate_steam_path
from sff.storage.settings import get_setting, set_setting
from sff.structs import OSType, Settings
from sff.utils import root_folder

try:
    _root = root_folder(outside_internal=True)
    os.chdir(_root)
except Exception as e:
    import traceback
    msg = traceback.format_exc()
    try:
        with open("crash.log", "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(None, "SteaMidra startup error", msg[:2000])
    sys.exit(1)

logger = logging.getLogger("sff")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler("debug.log")
fh.setFormatter(
    logging.Formatter(
        "%(asctime)s::%(name)s::%(levelname)s::%(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
    )
)
logger.addHandler(fh)


def get_steam_path_gui():
    path_str = get_setting(Settings.STEAM_PATH)
    if path_str:
        p = Path(path_str)
        if validate_steam_path(p):
            return p.resolve()
    if sys.platform == "win32":
        try:
            from sff.registry_access import find_steam_path_from_registry
            p = find_steam_path_from_registry()
            if validate_steam_path(p):
                return p
        except Exception:
            pass
    elif sys.platform == "linux":
        steam_dir = Path.home() / ".steam/root"
        if steam_dir.exists() and validate_steam_path(steam_dir):
            return steam_dir.resolve()
    return None


def main():
    lang = get_setting(Settings.LANGUAGE)
    if lang:
        from sff.i18n import set_language
        set_language(str(lang))

    app = QApplication(sys.argv)
    app.setApplicationName("SteaMidra")
    app.setApplicationDisplayName("SteaMidra")

    os_type = (
        OSType.WINDOWS
        if sys.platform == "win32"
        else (OSType.LINUX if sys.platform == "linux" else OSType.OTHER)
    )

    _steam_exe = "steam.exe" if sys.platform == "win32" else "steam"
    steam_path = get_steam_path_gui()
    while steam_path is None:
        QMessageBox.warning(
            None,
            "Steam path required — SteaMidra",
            f"Steam installation path could not be found. Please select the folder that contains {_steam_exe}.",
        )
        path = QFileDialog.getExistingDirectory(None, f"Select Steam folder (contains {_steam_exe})")
        if not path:
            sys.exit(0)
        path_obj = Path(path)
        if not validate_steam_path(path_obj):
            QMessageBox.warning(
                None,
                "Invalid path",
                "The selected folder does not appear to be a Steam installation (no steamapps folder).",
            )
            continue
        steam_path = path_obj.resolve()
        set_setting(Settings.STEAM_PATH, str(steam_path))

    from sff.gui.gui_prompts import install as install_gui_prompts
    install_gui_prompts()

    from steam.client import SteamClient
    from sff.steam_client import SteamInfoProvider
    from sff.ui import UI
    from sff.gui import SFFMainWindow

    client = SteamClient()
    provider = SteamInfoProvider(client)
    ui = UI(provider, steam_path, os_type)
    app.aboutToQuit.connect(ui.kill_midi_player)

    window = SFFMainWindow(ui, steam_path)
    window.show()

    from sff.tray_icon import TrayIcon
    tray = TrayIcon()
    tray.show_requested.connect(window.showNormal)
    tray.show_requested.connect(window.activateWindow)
    tray.exit_requested.connect(app.quit)
    tray.show()

    from sff.uri_handler import UriHandler
    if not UriHandler.is_registered():
        UriHandler.register()

    sys.exit(app.exec())


def _show_error_and_exit(msg, log_path = "crash.log"):
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    QMessageBox.critical(
        None,
        "SteaMidra failed to start",
        "An error occurred. See crash.log for details.\n\n" + msg[:1500],
    )
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        msg = traceback.format_exc()
        logger.exception("Uncaught exception in GUI")
        try:
            with open("crash.log", "w", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass
        _show_error_and_exit(msg)
