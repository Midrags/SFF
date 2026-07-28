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

# guard the PyQt6 import so a hollow build (CI accident) shows a useful
# message instead of just dumping ModuleNotFoundError to a console window
# that's already gone. happened once with the v6.3.1 workflow build —
# never again.
try:
    from PyQt6.QtGui import QIcon
except ImportError as _qt_err:
    _msg = (
        "SteaMidra failed to start because PyQt6 is missing from the install.\n\n"
        "This usually means the EXE you downloaded is incomplete (a CI build "
        "shipped without the GUI runtime). Re-download the latest release from:\n\n"
        "https://github.com/Midrags/SFF/releases/latest\n\n"
        "If the problem persists after a fresh install, ping the maintainer.\n\n"
        f"Original error: {_qt_err}"
    )
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, _msg, "SteaMidra — incomplete install", 0x10)
        except Exception:
            pass
    else:
        try:
            sys.stderr.write(_msg + "\n")
        except Exception:
            pass
    sys.exit(1)


class _NullWriter:
    def write(self, *a): pass
    def flush(self): pass


if sys.stderr is None:
    sys.stderr = _NullWriter()
if sys.stdout is None:
    sys.stdout = _NullWriter()


os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')
# Linux + Windows share one QtWebEngine flag stack now. 6.2.3 used
# this exact line for both platforms and Mint, Pop, Ubuntu, Fedora,
# Windows 10/11 all rendered correctly back then. Every version since
# tried to get clever per-session and broke at least one user. Going
# back to one line, no detection. The Windows white-flash work is
# gated on win32 in main_window.py via WA_OpaquePaintEvent, not via
# stripping zero-copy here.
#
# NVIDIA + Mesa GBM lookup fails on some Linux distros (issue #28) and
# the modern UI ends up blank. If the user hasn't already set their own
# QTWEBENGINE_CHROMIUM_FLAGS, slap a CPU-render fallback on top of the
# default on Linux ONLY. setdefault means power users with their own
# flag stack still win. Windows path is untouched. The disable-gpu /
# disable-features / disable-software-rasterizer stack here is what
# Skyflizz and others used to recover their UI by switching to Classic;
# baking it in skips the manual switch.
if sys.platform.startswith("linux"):
    if not os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"):
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            "--disable-gpu --disable-gpu-compositing "
            "--disable-features=UseOzonePlatform "
            "--disable-software-rasterizer"
        )
        # log line shows up in support logs once the file logger is ready;
        # using print() before logger init falls into the same null-stderr
        # void noop, so we'd never see this. Stash it for the logger init
        # block below.
        _LINUX_CHROMIUM_FALLBACK_APPLIED = True
    else:
        _LINUX_CHROMIUM_FALLBACK_APPLIED = False
else:
    _LINUX_CHROMIUM_FALLBACK_APPLIED = False
os.environ.setdefault(
    'QTWEBENGINE_CHROMIUM_FLAGS',
    '--no-sandbox --ignore-gpu-blocklist',
)

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
try:
    fh = logging.FileHandler(str(sff_data_dir() / "debug.log"), encoding="utf-8", errors="replace")
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s::%(name)s::%(levelname)s::%(message)s",
            datefmt="%m/%d/%Y %I:%M:%S %p",
        )
    )
    logger.addHandler(fh)
except Exception:
    logging.basicConfig(level=logging.DEBUG)

# Global crash hook — any unhandled exception anywhere in the app
# gets written to crash.log so the user can report it.
def _global_excepthook(exc_type, exc_value, exc_tb):
    import traceback
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("Unhandled exception:\n%s", msg)
    try:
        log_path = sff_data_dir() / "crash.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)
sys.excepthook = _global_excepthook

if _LINUX_CHROMIUM_FALLBACK_APPLIED:
    logger.info("Linux: applying Chromium GPU fallback flags")


# Yiso's case: Hubcap and DepotDownloaderMod both fall over silently when
# .NET 9 isn't on the box. The installer offers to grab it but if the user
# unchecked that box (or geo-blocking killed the download mid-setup) the
# app comes up looking fine and only breaks when they try to install a
# game. Probe at launch, fire ensure_dotnet_9 in the background if it's
# missing, and let the rest of the app boot in parallel. The launcher
# never blocks on this; ensure_dotnet_9 already retries with a sane
# timeout and logs progress to the file logger above.
def _kick_dotnet_check():
    try:
        from sff.dotnet_utils import get_dotnet_path, ensure_dotnet_9
        if get_dotnet_path():
            return
        # Not present. Run the installer on a worker thread so the GUI
        # event loop can come up while the download runs. The print_fn
        # routes everything into the standard logger so support logs
        # capture the install attempt.
        def _bg():
            class _LogPrinter:
                def __call__(self, msg):
                    try:
                        logger.info("[dotnet9-bootstrap] %s", str(msg))
                    except Exception:
                        pass
            try:
                ensure_dotnet_9(print_fn=_LogPrinter())
            except Exception:
                logger.exception("dotnet9 background bootstrap raised")
        import threading
        threading.Thread(target=_bg, name="dotnet9-bootstrap", daemon=True).start()
    except Exception:
        # Bootstrap is best-effort. A failure here must not stop the GUI.
        logger.exception("dotnet9 launch-time check raised before kicking")

_kick_dotnet_check()


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
        # The CLI's sff.steam_path.LinuxFinder already covers the common
        # native (.steam/steam, .local/share/Steam), Flatpak, and Snap
        # layouts. The GUI used to only probe ~/.steam/root, which exists
        # on Ubuntu/Debian but not on CachyOS, Arch, or Flatpak installs.
        # Reuse the CLI finder so the GUI matches CLI behaviour everywhere.
        from sff.steam_path import LinuxFinder
        try:
            p = LinuxFinder().find()
            if p is not None:
                return p
        except Exception:
            pass
    return None


def main():
    lang = get_setting(Settings.LANGUAGE)
    if lang:
        from sff.i18n import set_language
        set_language(str(lang))

    _pending_file = None
    for i, arg in enumerate(sys.argv):
        if arg in ("-f", "--file") and i + 1 < len(sys.argv):
            _pending_file = sys.argv[i + 1]
            break

    app = QApplication(sys.argv)
    app.setApplicationName("SteaMidra")
    app.setApplicationDisplayName("SteaMidra")

    from sff.single_instance import SingleInstanceGuard
    _guard = SingleInstanceGuard()
    if _pending_file:
        if _guard.try_activate_existing(f"FILE:{_pending_file}"):
            sys.exit(0)
    elif _guard.try_activate_existing():
        sys.exit(0)

    _app_icon = QIcon()
    _icon_candidates = list(("SFF.ico", "sff.ico", "SFF.png", "sff.png"))
    # PyInstaller onefile drops resources into _MEIPASS for the running
    # process. relative paths fail when steamidra was launched from a
    # different cwd (Start menu, taskbar pin), which is why a chunk of
    # users were getting a tray icon entry with no actual icon. resolve
    # against MEIPASS first, then app dir, then cwd as a last resort.
    _icon_search_dirs: list[str] = []
    try:
        _meipass = getattr(sys, "_MEIPASS", "") or ""
        if _meipass:
            _icon_search_dirs.append(_meipass)
    except Exception:
        pass
    try:
        _icon_search_dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    _icon_search_dirs.append(os.getcwd())
    if sys.platform == "linux":
        _appdir = os.environ.get("APPDIR", "")
        if _appdir:
            _icon_candidates.insert(0, os.path.join(_appdir, "SteaMidra.png"))
    _resolved_candidates: list[str] = []
    for _name in _icon_candidates:
        # absolute path entries (Linux APPDIR injection) get tested as-is
        if os.path.isabs(_name):
            _resolved_candidates.append(_name)
            continue
        for _d in _icon_search_dirs:
            if not _d:
                continue
            _p = os.path.join(_d, _name)
            if _p not in _resolved_candidates:
                _resolved_candidates.append(_p)
    for _ic in _resolved_candidates:
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

    if _pending_file:
        try:
            ui.process_lua_full(Path(_pending_file))
        except Exception:
            pass

    from sff.tray_icon import TrayIcon
    tray = TrayIcon(parent=app)
    tray.setup(_app_icon if not _app_icon.isNull() else app.windowIcon())
    window.set_tray(tray)
    app._tray = tray

    # Explorer can crash and re-broadcast TaskbarCreated; Qt does not
    # deliver that broadcast to widgets, so the icon stays gone until
    # the next process start unless we hook it at the app level.
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        from PyQt6.QtCore import QAbstractNativeEventFilter

        _TASKBAR_CREATED_MSG = ctypes.windll.user32.RegisterWindowMessageW("TaskbarCreated")

        class _MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]

        class TaskbarCreatedFilter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):
                if event_type == b"windows_generic_MSG":
                    try:
                        msg = _MSG.from_address(int(message))
                        if msg.message == _TASKBAR_CREATED_MSG:
                            tray.setup(_app_icon if not _app_icon.isNull() else app.windowIcon())
                            tray.show()
                    except Exception:
                        pass
                return False, 0

        _taskbar_filter = TaskbarCreatedFilter()
        app.installNativeEventFilter(_taskbar_filter)
        # Strong ref so Qt does not GC the filter.
        app._taskbar_filter = _taskbar_filter
    tray.show_requested.connect(window.showNormal)
    tray.show_requested.connect(window.activateWindow)
    tray.exit_requested.connect(app.quit)
    tray.exit_requested.connect(window.force_quit)

    # A13: explicit "Quit SteaMidra" entry on the tray context menu,
    # alongside the existing Exit. Always full-quits regardless of
    # CLOSE_TO_TRAY. Exit stays as-is (no rename, no rewire).
    from PyQt6.QtGui import QAction as _QAction

    def _on_tray_quit_steamidra():
        try:
            window.force_quit()
        finally:
            app.quit()

    _tray_menu = tray._menu if hasattr(tray, "_menu") else None
    if _tray_menu is not None:
        _quit_action = _QAction("Quit SteaMidra", _tray_menu)
        _quit_action.triggered.connect(_on_tray_quit_steamidra)
        _tray_menu.addAction(_quit_action)
        # Hold a strong ref so Qt does not GC the action.
        app._tray_quit_action = _quit_action

    def _on_show_from_second_instance():
        window.showNormal()
        window.activateWindow()
        window.raise_()

    def _on_file_from_second_instance(path_str):
        try:
            window.showNormal()
            window.activateWindow()
            window.raise_()
            ui.process_lua_full(Path(path_str))
        except Exception:
            pass

    _guard.start_server(_on_show_from_second_instance, on_file=_on_file_from_second_instance)
    app.aboutToQuit.connect(_guard.cleanup)

    from sff.uri_handler import UriHandler
    if not UriHandler.is_registered():
        UriHandler.register()

    # mirror Main.py:551-555 for the GUI entry point; defer so window.show() paints first
    if sys.platform == "linux":
        from PyQt6.QtCore import QTimer

        def _run_slssteam_update_check():
            try:
                from sff.linux.slssteam import check_and_notify_update
                check_and_notify_update()
            except Exception:
                pass

        QTimer.singleShot(0, _run_slssteam_update_check)
        _slssteam_timer = QTimer(app)
        _slssteam_timer.setInterval(60 * 60 * 1000)
        _slssteam_timer.timeout.connect(_run_slssteam_update_check)
        _slssteam_timer.start()
        app._slssteam_update_timer = _slssteam_timer

        # Auto-install .NET 9 on first Linux launch. DepotDownloaderMod and
        # Steamless both need it, and the user shouldn't have to dig into
        # Linux Tools Setup before their first download. Run on a daemon
        # thread because dotnet-install.sh takes 30-60s and would freeze
        # the window. The 6s defer keeps it off the critical path.
        def _maybe_install_dotnet_9_linux():
            try:
                from sff.dotnet_utils import get_dotnet_path, ensure_dotnet_9
                if get_dotnet_path():
                    return
                logger.info("Linux: .NET 9 not found, installing in background...")
                ensure_dotnet_9()
            except Exception as exc:
                logger.warning("Background .NET 9 install failed: %s", exc)

        def _kick_dotnet_install():
            import threading as _t
            _t.Thread(
                target=_maybe_install_dotnet_9_linux,
                name="sff-dotnet9-bootstrap",
                daemon=True,
            ).start()

        QTimer.singleShot(6000, _kick_dotnet_install)

    # A9: startup self-update popup. Defer 2s so the window paints first.
    # The whole body is wrapped so a GitHub failure or dialog construction
    # error never crashes the GUI (preservation requirement 3.20).
    from PyQt6.QtCore import QTimer

    def _maybe_self_update():
        try:
            auto = get_setting(Settings.AUTO_UPDATE_CHECK)
            # Default ON: only the explicit False / "False" disables it.
            if auto is False or (isinstance(auto, str) and auto.lower() == "false"):
                return
            from sff.updater import Updater, fetch_release_notes
            try:
                is_newer, release = Updater.update_available()
            except Exception:
                return
            if not is_newer or not release:
                return
            new_version = (release.get("tag_name") or "").strip()
            if not new_version:
                return
            skipped = get_setting(Settings.LAST_SKIPPED_VERSION) or ""
            if skipped == new_version:
                return
            notes = fetch_release_notes(new_version)
            from sff.gui.dialogs.self_update_dialog import SelfUpdateDialog
            dlg = SelfUpdateDialog(window, new_version, notes)

            def _do_download():
                # Reuse the manual update flow from the Settings button.
                try:
                    ui.check_updates(ui.os_type)
                except Exception:
                    pass

            def _do_skip():
                try:
                    set_setting(Settings.LAST_SKIPPED_VERSION, new_version)
                except Exception:
                    pass

            dlg.download_now.connect(_do_download)
            dlg.skip_this_version.connect(_do_skip)
            # remind_later just dismisses; nothing to wire.
            dlg.show()
            # Hold a reference so Qt does not garbage-collect the dialog.
            window._self_update_dialog = dlg
        except Exception:
            pass

    QTimer.singleShot(2000, _maybe_self_update)

    # A15: manifest preserver watcher is now started inside
    # SFFMainWindow.__init__ on a daemon thread. Nothing to do here.

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
