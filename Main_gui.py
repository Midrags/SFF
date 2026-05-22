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

from PyQt6.QtGui import QIcon


class _NullWriter:
    def write(self, *a): pass
    def flush(self): pass


if sys.stderr is None:
    sys.stderr = _NullWriter()
if sys.stdout is None:
    sys.stdout = _NullWriter()


os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy')

import PyQt6.QtWebEngineWidgets  # noqa: F401 - must import before QCoreApplication
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from sff.steam_path import validate_steam_path
from sff.storage.settings import get_setting, set_setting
from sff.structs import OSType, Settings
from sff.utils import root_folder, sff_data_dir

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
fh = logging.FileHandler(str(sff_data_dir() / "debug.log"))
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

    from sff.single_instance import SingleInstanceGuard
    _guard = SingleInstanceGuard()
    if _guard.try_activate_existing():
        sys.exit(0)

    _app_icon = QIcon()
    _icon_candidates = list(("SFF.ico", "SFF.png"))
    if sys.platform == "linux":
        _appdir = os.environ.get("APPDIR", "")
        if _appdir:
            _icon_candidates.insert(0, os.path.join(_appdir, "SteaMidra.png"))
    for _ic in _icon_candidates:
        _candidate = QIcon(str(_ic))
        if not _candidate.isNull():
            _app_icon = _candidate
            break
    if not _app_icon.isNull():
        app.setWindowIcon(_app_icon)
    if sys.platform == "linux":
        app.setDesktopFileName("steamidra")
        _appimage = os.environ.get("APPIMAGE", "")
        if _appimage:
            try:
                import shutil as _shutil
                _home = Path.home()
                _icon_dest_dir = _home / ".local/share/icons/hicolor/256x256/apps"
                _icon_dest = _icon_dest_dir / "SteaMidra.png"
                _desktop_dir = _home / ".local/share/applications"
                _desktop_file = _desktop_dir / "steamidra.desktop"
                _appdir_env = os.environ.get("APPDIR", "")
                _icon_src = Path(_appdir_env) / "SteaMidra.png" if _appdir_env else None
                if _icon_src and _icon_src.exists() and not _icon_dest.exists():
                    _icon_dest_dir.mkdir(parents=True, exist_ok=True)
                    _shutil.copy2(str(_icon_src), str(_icon_dest))
                _new_exec = f"Exec={_appimage}"
                _needs_write = (
                    not _desktop_file.exists()
                    or _new_exec not in _desktop_file.read_text(encoding="utf-8", errors="ignore")
                )
                if _needs_write:
                    _desktop_dir.mkdir(parents=True, exist_ok=True)
                    _desktop_file.write_text(
                        "[Desktop Entry]\n"
                        "Version=1.0\n"
                        "Name=SteaMidra\n"
                        "Comment=Steam game setup and manifest tool\n"
                        f"{_new_exec}\n"
                        "Icon=SteaMidra\n"
                        "Terminal=false\n"
                        "Type=Application\n"
                        "Categories=Utility;\n"
                        "StartupNotify=false\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass

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

    app.setQuitOnLastWindowClosed(False)

    window = SFFMainWindow(ui, steam_path)
    if not _app_icon.isNull():
        window.setWindowIcon(_app_icon)
    window.show()

    from sff.tray_icon import TrayIcon
    tray = TrayIcon(parent=window)
    tray.setup(_app_icon if not _app_icon.isNull() else app.windowIcon())
    window.set_tray(tray)
    # Keep a reference on app to prevent garbage collection
    app._tray = tray
    tray.show_requested.connect(window.showNormal)
    tray.show_requested.connect(window.activateWindow)
    tray.exit_requested.connect(app.quit)
    tray.exit_requested.connect(window.force_quit)

    def _on_show_from_second_instance():
        window.showNormal()
        window.activateWindow()
        window.raise_()

    _guard.start_server(_on_show_from_second_instance)
    app.aboutToQuit.connect(_guard.cleanup)

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
