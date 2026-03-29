# owner: Midrag
import logging
import os
import sys
from pathlib import Path
from typing import Optional

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


def get_steam_path_gui() -> Optional[Path]:
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


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SteaMidra")
    app.setApplicationDisplayName("SteaMidra")

    os_type = (
        OSType.WINDOWS
        if sys.platform == "win32"
        else (OSType.LINUX if sys.platform == "linux" else OSType.OTHER)
    )

    steam_path = get_steam_path_gui()
    while steam_path is None:
        QMessageBox.warning(
            None,
            "Steam path required",
            "Steam installation path could not be found. Please select the folder that contains steam.exe.",
        )
        path = QFileDialog.getExistingDirectory(None, "Select Steam folder (contains steam.exe)")
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

    window = SFFMainWindow(ui, steam_path)
    window.show()
    sys.exit(app.exec())


def _show_error_and_exit(msg: str, log_path: str = "crash.log") -> None:
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
