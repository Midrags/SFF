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
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QByteArray, QEasingCurve, QEvent, QObject, QPropertyAnimation, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QTextCursor
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QTabWidget,
)

from sff.gui.log_window import GlobalLogWindow, QtLogHandler
from sff.gui.themes import THEMES, theme_background, titlebar_colors
from sff.i18n import T
from sff.structs import MainMenu, MainReturnCode

# Import preserver at module level so its dependency imports run
# during Python's single-threaded import phase, not inside a background
# thread where importlib concurrency can race with QtWebEngine init.
try:
    from sff.manifests.preserver import start_watcher as _start_watcher
except Exception:
    _start_watcher = None

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
logger = logging.getLogger(__name__)


class StreamEmitter(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        if text:
            self.text_written.emit(text)

    def flush(self):
        pass


class GenericWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func):
        super().__init__()
        self.func = func

    def run(self):
        try:
            result = self.func()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(None)


def _arrow_style_url(path):
    s = str(path.resolve()).replace("\\", "/")
    return f'"{s}"' if " " in s else s


_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"


class GameComboBox(QComboBox):
    """ComboBox with visible arrow that points down when closed, up when open."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_open = False
        self._down_path = _RESOURCES_DIR / "arrow_down.png"
        self._up_path = _RESOURCES_DIR / "arrow_up.png"
        self._update_arrow()

    def showPopup(self):
        self._popup_open = True
        self._update_arrow()
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        self._popup_open = False
        self._update_arrow()

    def _update_arrow(self):
        if not self._down_path.exists() or not self._up_path.exists():
            return
        p = self._up_path if self._popup_open else self._down_path
        url = _arrow_style_url(p)
        self.setStyleSheet(
            f"QComboBox::down-arrow {{ image: url({url}); width: 14px; height: 14px; }}"
            "QComboBox::drop-down {"
            " subcontrol-origin: padding; subcontrol-position: center right;"
            " width: 24px; min-width: 24px; border: none; }"
        )


class SFFMainWindow(QMainWindow):
    def __init__(self, ui, steam_path):
        super().__init__()
        self.ui = ui
        self.steam_path = steam_path
        from sff.storage.settings import get_setting
        from sff.structs import Settings as _S
        _saved_theme = get_setting(_S.THEME)
        self._current_theme = _saved_theme if (_saved_theme and _saved_theme in THEMES) else "dark"
        self._music_muted = False
        self._last_web_stdout_time = 0.0
        # Batched log forwarding to the web UI. Each emit crosses the
        # C++/JS boundary via QtWebChannel; under load (parallel
        # manifest downloads, DDMod stdout, debug logging) the per-line
        # emit was queueing tens of thousands of QString allocations
        # that QtWebEngine retains in its renderer process for tens of
        # seconds. Batched flush every 100ms means at most 10 messages
        # per second cross the boundary regardless of producer rate;
        # the DEBUG drop below 200 buffered lines keeps the burst
        # bounded if a consumer (the Python-side worker) outpaces the
        # 100ms flush.
        self._web_log_buffer: list[str] = []
        self._web_log_buffer_max = 200
        self._web_log_dropped = 0
        # Same idea on the Qt-side log surfaces (the dockable
        # GlobalLogWindow and the legacy menubar QTextEdit). Each
        # print() from the worker thread used to fire the signal
        # synchronously and run insertHtml + 2 moveCursor calls per
        # line on the GUI thread. The Steam-option download path
        # prints hundreds of lines per depot and that locked up the
        # whole window for the duration. Now we buffer and drain
        # every 100ms so a print burst becomes one batched insert.
        self._qt_log_buffer: list[str] = []
        self._qt_log_buffer_max = 400
        self._qt_log_dropped = 0
        from PyQt6.QtCore import QTimer as _QTimer
        self._web_log_flush_timer = _QTimer(self)
        self._web_log_flush_timer.setInterval(250)
        self._web_log_flush_timer.timeout.connect(self._flush_web_log_buffer)
        self._web_log_flush_timer.start()
        self._qt_log_flush_timer = _QTimer(self)
        self._qt_log_flush_timer.setInterval(250)
        self._qt_log_flush_timer.timeout.connect(self._flush_qt_log_buffer)
        self._qt_log_flush_timer.start()
        self._game_list = []
        self._stream_emitter = StreamEmitter()
        self._log_window = GlobalLogWindow(self)
        self._log_handler = QtLogHandler()
        self._log_handler.setFormatter(
            __import__('logging').Formatter("%(name)s — %(message)s")
        )
        self._log_handler.setLevel(__import__('logging').DEBUG)
        self._log_handler.record_emitted.connect(self._log_window.append_record)
        self._log_handler.record_emitted.connect(self._forward_log_to_web)
        __import__('logging').getLogger().addHandler(self._log_handler)
        self._stream_emitter.text_written.connect(self._forward_stdout_to_web)
        self._stream_emitter.text_written.connect(self._buffer_qt_log)
        self._worker = None
        self._worker_thread = None
        self.setWindowTitle("SteaMidra")
        self.setMinimumSize(960, 700)
        if sys.platform == "win32":
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        geom = get_setting(_S.WINDOW_GEOMETRY)
        if geom:
            try:
                self.restoreGeometry(QByteArray.fromHex(str(geom).encode()))
            except Exception:
                self.resize(1020, 780)
        else:
            self.resize(1020, 780)
        from sff.gui.gui_prompts import update_parent
        update_parent(self)
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        central.installEventFilter(self)

        # ── Title bar buttons (Windows only, overlay top-right) ──
        if sys.platform == "win32":
            from PyQt6.QtWidgets import QPushButton as _PB
            from PyQt6.QtCore import Qt as _Qt

            self._tb_maximized = False
            self._tb_buttons = []

            _btn_style = (
                "QPushButton { background: transparent; border: none; color: #e8e8e8; font-size: 22px; padding: 0; }"
                "QPushButton:hover { background-color: rgba(255,255,255,15); }"
            )
            _close_style = (
                "QPushButton { background: transparent; border: none; color: #e8e8e8; font-size: 22px; padding: 0; }"
                "QPushButton:hover { background-color: #e81123; color: #ffffff; }"
            )

            for _text, _slot, _style in [
                ("\u2013", self.showMinimized, _btn_style),
                ("\u25a1", self._tb_toggle_max, _btn_style),
                ("\u2715", self.close, _close_style),
            ]:
                _b = _PB(_text, central)
                _b.setFixedSize(64, 56)
                _b.setFocusPolicy(_Qt.FocusPolicy.NoFocus)
                _b.setStyleSheet(_style)
                _b.clicked.connect(_slot)
                _b.show()
                self._tb_buttons.append(_b)
            self._tb_max_btn = self._tb_buttons[1]

            def _position_buttons():
                w = self.width()
                x = w - 4
                for _b in reversed(self._tb_buttons):
                    x -= 64
                    _b.move(x, 0)

            self._position_tb_buttons = _position_buttons
            self._tb_drag_pos = None

            self._position_tb_buttons = _position_buttons
            self._tb_drag_pos = None
        else:
            self._tb_buttons = None
            self._tb_max_btn = None

        # ── LumaCore status banner (hidden until a poll finds missing TOML) ──
        self._lumacore_banner = QLabel()
        self._lumacore_banner.setObjectName("LumaCoreStatusBanner")
        self._lumacore_banner.setVisible(False)
        self._lumacore_banner.setWordWrap(True)
        self._lumacore_banner.setStyleSheet(
            "QLabel#LumaCoreStatusBanner {"
            " background-color: #5c3c0e;"
            " color: #f0d080;"
            " padding: 6px 12px;"
            " font-size: 12px;"
            " border-bottom: 1px solid #7a5018;"
            "}"
        )
        root_layout.addWidget(self._lumacore_banner)

        # ── Classic tab UI (hidden by default — new UI is primary) ──
        self.tabs = QTabWidget()
        self.tabs.setVisible(False)
        self.tabs.setUpdatesEnabled(False)
        self.tabs.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        root_layout.addWidget(self.tabs)

        # ── New Web UI (visible by default) ──
        self._web_view = QWebEngineView()
        self._web_view_freed = False
        self._web_index_path = None
        # Mark the view as opaque so Qt's drag/resize/paint pipeline skips
        # the parent-erase step under it. Without this, every drag tick on
        # Windows DWM hands the compositor a frame where the parent gets
        # erased to the platform default background under the WebEngine
        # surface for one frame before the renderer's texture lands on top,
        # producing the brief white / checker flash users see during drag,
        # download start, and theme switches. The flash is worse on dark
        # themes because the contrast is higher.
        # Windows-only. On Linux these attributes interact badly with
        # X11 + Mesa compositors and the page doesnt paint. 6.2.3
        # didnt set them and rendered fine on Mint, so leave the
        # default Qt opaque painting for Linux.
        if sys.platform == "win32":
            try:
                from PyQt6.QtCore import Qt as _Qt
                self._web_view.setAttribute(_Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
                self._web_view.setAttribute(_Qt.WidgetAttribute.WA_NoSystemBackground, True)
                self._web_view.setAutoFillBackground(False)
            except Exception:
                pass
        root_layout.addWidget(self._web_view)

        # Invisible drag strip above web view — captures mouse for window move
        if sys.platform == "win32":
            class _DragStrip(QWidget):
                def mousePressEvent(self, ev):
                    if ev.button() == Qt.MouseButton.LeftButton:
                        self._drag_pos = ev.globalPosition().toPoint()
                def mouseMoveEvent(self, ev):
                    if ev.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos') and self._drag_pos is not None:
                        if self.window().isMaximized():
                            self.window().showNormal()
                        delta = ev.globalPosition().toPoint() - self._drag_pos
                        self.window().move(self.window().pos() + delta)
                        self._drag_pos = ev.globalPosition().toPoint()
                def mouseReleaseEvent(self, ev):
                    self._drag_pos = None
                def mouseDoubleClickEvent(self, ev):
                    if ev.button() == Qt.MouseButton.LeftButton:
                        w = self.window()
                        if w.isMaximized(): w.showNormal()
                        else: w.showMaximized()
            _ds = _DragStrip(central)
            _ds._drag_pos = None
            _ds.setStyleSheet("background: transparent;")
            _ds.setCursor(Qt.CursorShape.ArrowCursor)
            self._drag_strip = _ds

        self._web_channel = QWebChannel()
        from sff.gui.web_bridge import WebBridge
        self._web_bridge = WebBridge(ui=ui, steam_path=steam_path, parent=self)
        self._web_channel.registerObject("bridge", self._web_bridge)
        self._web_view.page().setWebChannel(self._web_channel)
        # Allow loading Steam CDN images from local file:// page
        self._web_view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._web_view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True
        )
        self._web_view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.WebGLEnabled, True
        )
        self._web_view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.ShowScrollBars, False
        )
        self._web_view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.ErrorPageEnabled, False
        )
        self._web_view.page().renderProcessTerminated.connect(self._on_render_crash)
        self._install_web_splash()
        saved_ui_mode = get_setting(_S.USE_MODERN_UI)
        self._web_ui_active = True if saved_ui_mode is None else bool(saved_ui_mode)
        self._web_ui_loaded = False

        # LumaCore status banner poller. Reads <steam>\lumacore\status.json
        # every 2 s and shows a banner when the TOML pattern file is missing
        # for either steamclient or steamui. Parented to self so the timer
        # is cleaned up when the window closes.
        try:
            from sff.lumacore.status_banner import StatusBannerPoller
            self._status_poller = StatusBannerPoller(steam_path, parent=self)
            self._status_poller.unavailable.connect(self._show_lumacore_banner)
            self._status_poller.cleared.connect(self._hide_lumacore_banner)
        except Exception:
            self._status_poller = None
            logger.exception("Failed to create LumaCore status banner poller")

        # Manifest preservation watcher. The staging dir under
        # <sff_data>/manifests/ already holds every manifest SteaMidra has
        # downloaded. The watcher checks the two Steam-side caches that get
        # cleared on game uninstall (<steam>/depotcache and
        # <steam>/config/depotcache) and copies the manifest back from the
        # staging dir if a file goes missing. No backup tree, no startup walk;
        # the staging dir IS the backup.
        try:
            import threading as _threading

            def _start_manifest_preserver():
                if _start_watcher is not None:
                    try:
                        _start_watcher(self.steam_path)
                    except Exception:
                        pass

            _threading.Thread(
                target=_start_manifest_preserver,
                name="sff-manifest-preserver-init",
                daemon=True,
            ).start()
        except Exception:
            pass
        _should_save = _saved_theme is None or _saved_theme in THEMES
        self._set_theme(self._current_theme, save=_should_save)
        if not self._web_ui_active:
            self._build_classic_ui(steam_path)
            self._on_source_changed()
            self._refresh_game_list()
            self.menuBar().setVisible(True)
            self.tabs.setVisible(True)
            self._web_view.setVisible(False)
        else:
            self.tabs.setVisible(False)
            self._web_view.setVisible(True)
            self._load_web_ui()
            self._web_ui_loaded = True
        self._tray = None
        self._tray_hide_notified = False
        self._save_watcher_timer = QTimer(self)
        self._save_watcher_timer.timeout.connect(self._run_background_save_watcher)
        self._start_save_watcher()
        # 6.2.5: per-app update-available periodic timer. The tick runs
        # every 5 minutes, walks app_list_man, applies per-app overrides
        # and the global gate, and dispatches at most one
        # check_game_update call per app per UPDATE_CHECK_INTERVAL_MIN.
        # Cross-app dispatches are paced one per 2 seconds via
        # QTimer.singleShot chaining.
        self._update_check_timer = QTimer(self)
        self._update_check_timer.timeout.connect(self._run_update_check_tick)
        self._update_check_dispatched_at: dict[str, float] = {}
        self._update_check_pending_queue: list[str] = []
        self._update_check_dispatching = False
        self._update_check_timer.start(5 * 60 * 1000)
        # First tick after a short delay so the UI settles before the
        # initial sweep fires.
        QTimer.singleShot(15 * 1000, self._run_update_check_tick)

        # 6.2.6: surface a leftover updater log if the previous launch's
        # in-place update bat hit an error. The bat runs headless, so a
        # robocopy failure (locked _internal\, antivirus, partial copy)
        # otherwise dies silently and the user keeps running the old
        # build without knowing why. Cleanup the log after surfacing so
        # subsequent launches don't re-warn.
        QTimer.singleShot(2 * 1000, self._surface_stale_updater_log)

    def _build_classic_ui(self, steam_path):
        if getattr(self, '_classic_ui_built', False):
            return
        self._classic_ui_built = True

        from sff.download_manager import DownloadManager
        self._download_manager = DownloadManager()
        self.ui.download_manager = self._download_manager

        from sff.gui.store_tab import StoreTab
        from sff.gui.downloads_tab import DownloadsTab
        from sff.gui.fix_game_tab import FixGameTab
        from sff.gui.tools_tab import ToolsTab
        from sff.gui.cloud_saves_tab import CloudSavesTab

        self.store_tab = StoreTab(steam_path=steam_path, ui=self.ui, run_tool_fn=self._run_tool)
        self.tabs.addTab(self.store_tab, "Store")
        self.downloads_tab = DownloadsTab(download_manager=self._download_manager)
        self.tabs.addTab(self.downloads_tab, "Download Tracking")
        self.fix_game_tab = FixGameTab(steam_path=steam_path)
        self.tabs.addTab(self.fix_game_tab, "Fix Game")
        self.tools_tab = ToolsTab(steam_path)
        self.tabs.addTab(self.tools_tab, "Tools")
        self.cloud_saves_tab = CloudSavesTab(steam_path)
        self.tabs.addTab(self.cloud_saves_tab, "Cloud Saves")

        main_tab_widget = QWidget()
        main_tab_layout = QVBoxLayout(main_tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        main_tab_layout.addWidget(scroll, stretch=1)
        self.tabs.insertTab(0, main_tab_widget, "Main")
        from sff.gui.help_buttons import add_help_button
        add_help_button(layout, "Main Hub", "SteaMidra Main Hub\n\n"
            "Game / Path:\n  Select a Steam game from the dropdown or browse to a game\n"
            "  folder outside Steam. Used by all Game Actions below.\n\n"
            "Game Actions:\n"
            "  - Crack game (gbe_fork): Replace steam_api DLLs with Goldberg\n"
            "    Emulator so the game runs without Steam ownership.\n"
            "  - Remove SteamStub: Strip Valve's SteamStub DRM wrapper from\n"
            "    a game executable using Steamless.\n"
            "  - UserGameStats: Download achievement data for the selected game.\n"
            "  - DLC check: See which DLCs exist and which are unlocked.\n"
            "  - Workshop item: Download a Steam Workshop mod by ID.\n"
            "  - Open Workshop: Browse the Workshop for the selected game.\n"
            "  - Check mod updates: See if downloaded Workshop mods have\n"
            "    newer versions available.\n"
            "  - Multiplayer fix: Apply online-fix.me multiplayer patches.\n"
            "  - Fixes & Bypasses: Apply community-maintained fixes.\n"
            "  - DLC Unlockers: Manage CreamAPI / SmokeAPI / other DLC\n"
            "    unlocker DLLs for the selected game.\n"
            "  - SteamAutoCrack: Run the SteamAutoCrack CLI tool on the game.\n\n"
            "Lua / Manifest Processing:\n"
            "  - Download Games: Parse a .lua file and download all game\n"
            "    files (depots, manifests, ACF) to your Steam library.\n"
            "  - Download manifests only: Download just the .manifest files\n"
            "    without game content.\n"
            "  - Recent .lua files: Re-open a previously used .lua file.\n"
            "  - Update all manifests: Refresh manifests for all previously\n"
            "    downloaded games.\n\n"
            "Library & Steam Tools:\n"
            "  - Manage Injection Profiles: Create, switch, save, merge,\n"
            "    delete, or rename app ID injection profiles.\n"
            "  - Mute: Toggle background music on/off.\n"
            "  - Remove game from library: Remove a game's ACF and registered app ID.\n"
            "  - Context menu: Add/remove SteaMidra from Windows Explorer\n"
            "    right-click menu.",
            parent_widget=self,
        )
        path_group = QGroupBox(T("Game / path"))
        path_layout = QVBoxLayout(path_group)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel(T("Path:")))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(T("Game folder (for outside Steam) or leave empty for Steam games"))
        path_row.addWidget(self.path_edit)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        path_layout.addLayout(path_row)
        source_row = QHBoxLayout()
        self.radio_steam = QRadioButton(T("Steam games"))
        self.radio_steam.setChecked(True)
        self.radio_outside = QRadioButton(T("Games outside of Steam"))
        self.radio_steam.toggled.connect(self._on_source_changed)
        self.radio_outside.toggled.connect(self._on_source_changed)
        source_row.addWidget(self.radio_steam)
        source_row.addWidget(self.radio_outside)
        source_row.addStretch()
        path_layout.addLayout(source_row)
        game_row = QHBoxLayout()
        game_row.addWidget(QLabel(T("Game:")))
        self.game_combo = GameComboBox()
        self.game_combo.setMinimumWidth(280)
        game_row.addWidget(self.game_combo)
        refresh_btn = QPushButton(T("Refresh list"))
        refresh_btn.clicked.connect(self._refresh_game_list)
        game_row.addWidget(refresh_btn)
        quick_cc_btn = QPushButton("Quick ColdClient")
        quick_cc_btn.setToolTip("Open Fix Game tab with ColdClient mode pre-filled for the selected game")
        quick_cc_btn.clicked.connect(self._quick_coldclient)
        game_row.addWidget(quick_cc_btn)
        game_row.addStretch()
        path_layout.addLayout(game_row)
        outside_row = QHBoxLayout()
        self._outside_name_label = QLabel("Game name:")
        outside_row.addWidget(self._outside_name_label)
        self.outside_name_edit = QLineEdit()
        self.outside_name_edit.setPlaceholderText("For search (e.g. online-fix.me)")
        outside_row.addWidget(self.outside_name_edit)
        self._outside_appid_label = QLabel("App ID:")
        outside_row.addWidget(self._outside_appid_label)
        self.outside_appid_edit = QLineEdit()
        self.outside_appid_edit.setPlaceholderText("Optional")
        self.outside_appid_edit.setMaximumWidth(80)
        outside_row.addWidget(self.outside_appid_edit)
        outside_row.addStretch()
        path_layout.addLayout(outside_row)
        for w in (self._outside_name_label, self.outside_name_edit, self._outside_appid_label, self.outside_appid_edit):
            w.setVisible(False)
        layout.addWidget(path_group)
        game_actions_group = QGroupBox(T("Game Actions"))
        ga_layout = QVBoxLayout(game_actions_group)
        ga_layout.setSpacing(6)
        _TOOLTIPS = {
            T("Crack game (gbe_fork)"): "Replace steam_api DLLs with Goldberg Emulator. Breaks Steam achievements and cloud saves.",
            T("Remove SteamStub (Steamless)"): "Strip Valve's SteamStub DRM from a game executable. Achievements stay working.",
            T("UserGameStats"): "Download achievement / stats data for this game",
            T("DLC check"): "See which DLCs exist and which are unlocked",
            T("Workshop item"): "Download a Steam Workshop mod by its ID",
            T("Open Workshop"): "Browse the Steam Workshop for this game",
            T("Check mod updates"): "Check if downloaded Workshop mods have newer versions",
            T("Multiplayer fix"): "Apply online-fix.me multiplayer patches",
            T("Fixes & Bypasses"): "Apply community-maintained fixes and bypasses (CrakFiles repo). Achievement-safe.",
            T("DLC Unlockers"): "Manage CreamAPI / SmokeAPI / other DLC unlocker DLLs",
            T("SteamAutoCrack"): "Run the SteamAutoCrack CLI tool on this game. Breaks Steam achievements and cloud saves.",
        }
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        for label, choice in [
            (T("Crack game (gbe_fork)"), MainMenu.CRACK_GAME),
            (T("Remove SteamStub (Steamless)"), MainMenu.REMOVE_DRM),
            (T("UserGameStats"), MainMenu.DL_USER_GAME_STATS),
            (T("DLC check"), MainMenu.DLC_CHECK),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(_TOOLTIPS.get(label, ""))
            btn.clicked.connect(lambda checked=False, c=choice: self._run_game_action(c))
            row1.addWidget(btn)
        row1.addStretch()
        ga_layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        for label, choice in [
            (T("Workshop item"), MainMenu.DL_WORKSHOP_ITEM),
            (T("Open Workshop"), None),
            (T("Check mod updates"), MainMenu.CHECK_MOD_UPDATES),
            (T("Multiplayer fix"), MainMenu.MULTIPLAYER_FIX),
            (T("Fixes & Bypasses"), MainMenu.CRACK_FIX),
            (T("HyperVisor (HVAuto)"), MainMenu.HV_FIX),
            (T("DLC Unlockers"), MainMenu.MANAGE_DLC_UNLOCKERS),
            (T("SteamAutoCrack"), None),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(_TOOLTIPS.get(label, ""))
            if choice is not None:
                btn.clicked.connect(lambda checked=False, c=choice: self._run_game_action(c))
            elif label == T("SteamAutoCrack"):
                btn.clicked.connect(self._run_steam_auto_gui)
            else:
                btn.clicked.connect(self._open_workshop)
            row2.addWidget(btn)
        row2.addStretch()
        ga_layout.addLayout(row2)
        layout.addWidget(game_actions_group)
        lua_group = QGroupBox(T("Lua / Manifest Processing"))
        lua_layout = QVBoxLayout(lua_group)
        lua_row = QHBoxLayout()
        for label, func in [
            (T("Download Games"), lambda: self.ui.process_lua_full()),
            (T("Download manifests only"), lambda: self.ui.process_lua_minimal()),
            (T("Recent .lua files"), lambda: self.ui.recent_files_menu()),
            (T("Update all manifests"), lambda: self.ui.update_all_manifests()),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
            lua_row.addWidget(btn)
        lua_row.addStretch()
        lua_layout.addLayout(lua_row)
        layout.addWidget(lua_group)
        tools_group = QGroupBox(T("Library & Steam Tools"))
        tools_layout = QVBoxLayout(tools_group)
        tools_row1 = QHBoxLayout()
        for label, func in [
            (T("Manage Injection Profiles"), lambda: self.ui.injection_menu()),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
            tools_row1.addWidget(btn)
        self._mute_btn = QPushButton("Mute")
        self._mute_btn.clicked.connect(self._toggle_mute)
        tools_row1.addWidget(self._mute_btn)
        tools_row1.addStretch()
        tools_layout.addLayout(tools_row1)
        if sys.platform == "win32":
            tools_row2 = QHBoxLayout()
            for label, func in [
                (T("Remove game from library"), lambda: self.ui.remove_game_menu()),
                (T("Context menu"), lambda: self.ui.manage_context_menu()),
            ]:
                btn = QPushButton(label)
                btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
                tools_row2.addWidget(btn)
            tools_row2.addStretch()
            tools_layout.addLayout(tools_row2)
        layout.addWidget(tools_group)
        if sys.platform == "win32":
            lc_group = QGroupBox(T("LumaCore Setup"))
            lc_layout = QVBoxLayout(lc_group)
            lc_row1 = QHBoxLayout()
            lc_row1.setSpacing(4)
            lc_install_btn = QPushButton(T("Install / Update LumaCore"))
            lc_install_btn.setToolTip(T("Download the latest LumaCore release and install it into the Steam folder."))
            lc_install_btn.clicked.connect(self._install_lumacore_gui)
            lc_row1.addWidget(lc_install_btn)
            lc_deact_btn = QPushButton(T("Deactivate LumaCore"))
            lc_deact_btn.setToolTip(T("Close Steam and remove the LumaCore DLLs."))
            lc_deact_btn.clicked.connect(self._deactivate_lumacore_gui)
            lc_row1.addWidget(lc_deact_btn)
            lc_ver_btn = QPushButton(T("Check Version"))
            lc_ver_btn.setToolTip(T("Compare the installed LumaCore version with the latest release."))
            lc_ver_btn.clicked.connect(self._check_lumacore_version_gui)
            lc_row1.addWidget(lc_ver_btn)
            lc_row1.addStretch()
            lc_layout.addLayout(lc_row1)
            lc_row2 = QHBoxLayout()
            lc_row2.setSpacing(4)
            lc_onlinefix_btn = QPushButton(T("LC Online Fix (selected game)"))
            lc_onlinefix_btn.setToolTip(T("Toggle the -onlinefix launch flag for the selected game."))
            lc_onlinefix_btn.clicked.connect(self._toggle_online_fix_gui)
            lc_row2.addWidget(lc_onlinefix_btn)
            lc_row2.addStretch()
            lc_layout.addLayout(lc_row2)
            layout.addWidget(lc_group)
        log_group = QGroupBox(T("Log"))
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(5000)
        self.log_text.setMinimumHeight(160)
        log_layout.addWidget(self.log_text)
        clear_btn = QPushButton(T("Clear log"))
        clear_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_btn)
        layout.addWidget(log_group)

        menubar = self.menuBar()
        settings_action = menubar.addAction(T("Settings"))
        settings_action.triggered.connect(self._show_settings)
        theme_menu = menubar.addMenu(T("Theme"))
        for key, (name, _) in THEMES.items():
            action = theme_menu.addAction(name)
            action.triggered.connect(lambda checked=False, k=key: self._set_theme(k))
        help_menu = menubar.addMenu(T("Help"))
        help_menu.addAction(T("About")).triggered.connect(self._show_about)
        help_menu.addAction(T("Check for updates")).triggered.connect(
            lambda: self._run_tool(lambda: self.ui.check_updates(self.ui.os_type))
        )
        help_menu.addAction(T("Scan game library")).triggered.connect(
            lambda: self._run_tool(lambda: self.ui.scan_library_menu())
        )
        help_menu.addAction(T("Analytics dashboard")).triggered.connect(
            lambda: self._run_tool(lambda: self.ui.analytics_dashboard_menu())
        )
        help_menu.addAction(T("Dump Achievement Diagnostic")).triggered.connect(
            self._dump_achievement_diagnostic
        )
        logs_action = menubar.addAction("Logs")
        logs_action.triggered.connect(self._show_log_window)

        switch_btn = QPushButton(T("Switch to Modern UI"))
        switch_btn.setStyleSheet(
            "QPushButton { background: rgba(44,44,44,185); color: #f4f4f4;"
            " border: 1px solid rgba(255,255,255,55); border-radius: 4px;"
            " padding: 4px 10px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(65,65,65,225);"
            " border-color: rgba(255,255,255,95); }"
        )
        switch_btn.clicked.connect(self._toggle_web_ui)
        self.tabs.setCornerWidget(switch_btn, Qt.Corner.TopRightCorner)

    def _surface_stale_updater_log(self):
        try:
            from pathlib import Path
            import sys
            if not getattr(sys, "frozen", False):
                return
            app_dir = Path(sys.executable).resolve().parent

            # Sweep leftovers from a previous in-place update. The bat
            # cleans these up on success AND failure now, but a user who
            # rebooted mid-update, or who hit Ctrl-C on the headless cmd
            # window, can still leave them on disk. Reported case: a
            # 6.2.5 installer ran, the bat copied the new files, the
            # user rebooted before the bat reached its cleanup step,
            # and the next launch saw `tmp_update\` (a full copy of the
            # build the user had just upgraded to) plus `update.zip`
            # sitting next to the EXE. The leftovers don't break
            # anything but they're confusing and waste a few hundred MB.
            for stale_name in ("tmp_update", "update.zip", "update.rar"):
                stale_path = app_dir / stale_name
                if not stale_path.exists():
                    continue
                try:
                    if stale_path.is_dir():
                        import shutil as _shutil
                        _shutil.rmtree(stale_path, ignore_errors=True)
                    else:
                        stale_path.unlink()
                    logger.info("updater leftover swept: %s", stale_path.name)
                except OSError as exc:
                    logger.debug("could not sweep updater leftover %s: %s",
                                 stale_path, exc)

            log_path = app_dir / "tmp_updater.log"
            if not log_path.exists():
                return
            text = ""
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
            failed = "FAIL" in text or "WARN" in text
            try:
                log_path.unlink()
            except OSError:
                pass
            if not text:
                return
            level = "warning" if failed else "info"
            tail = "\n".join(text.strip().splitlines()[-12:])
            msg = "Last in-place update reported an issue:\n\n" + tail if failed \
                  else "Update applied. Last log:\n\n" + tail
            try:
                logger.warning("updater log (%s):\n%s", level, tail) if failed \
                    else logger.info("updater log:\n%s", tail)
            except Exception:
                pass
            if failed:
                try:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "SteaMidra update — issue", msg)
                except Exception:
                    pass
        except Exception:
            logger.debug("_surface_stale_updater_log crashed", exc_info=True)

    # ── Path / game source helpers ───────────────────────────────

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select game folder")
        if path:
            self.path_edit.setText(path)
            if self.radio_outside.isChecked() and not self.outside_name_edit.text().strip():
                self.outside_name_edit.setText(Path(path).name)

    def _on_source_changed(self):
        from_steam = self.radio_steam.isChecked()
        self.game_combo.setEnabled(from_steam)
        self.path_edit.setEnabled(not from_steam)
        for w in (
            self._outside_name_label,
            self.outside_name_edit,
            self._outside_appid_label,
            self.outside_appid_edit,
        ):
            w.setVisible(not from_steam)

    def _refresh_game_list(self):
        from sff.game_specific import GameHandler
        from sff.storage.vdf import get_steam_libs
        self.game_combo.clear()
        self._game_list = []
        injection = self.ui.app_list_man or self.ui.sls_man
        if not injection:
            self.game_combo.addItem("(Unsupported on this OS)", None)
            return
        steam_libs = get_steam_libs(self.steam_path)
        lib_path = steam_libs[0] if steam_libs else self.steam_path
        handler = GameHandler(self.steam_path, lib_path, self.ui.provider, injection)
        self._game_list = handler.get_game_list()
        if not self._game_list:
            self.game_combo.addItem("(No games found)", None)
            return
        for name, acf in self._game_list:
            self.game_combo.addItem(name, acf)

    def _quick_coldclient(self):
        """Switch to Fix Game tab with ColdClient mode pre-filled from the selected game."""
        from sff.fix_game.service import EmuMode
        acf = self._get_selected_acf()
        if acf is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Game Selected",
                                "Please select a game from the dropdown first.")
            return
        game_path = str(getattr(acf, "path", "") or "")
        app_id = str(getattr(acf, "app_id", "") or "")
        self.fix_game_tab.prefill(game_path, app_id, EmuMode.COLDCLIENT_SIMPLE)
        # switch to Fix Game tab
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Fix Game":
                self.tabs.setCurrentIndex(i)
                break

    def _get_selected_acf(self):
        from sff.game_specific import ACFInfo
        if self.radio_steam.isChecked():
            return self.game_combo.currentData()
        path_str = self.path_edit.text().strip()
        if not path_str:
            return None
        path = Path(path_str).resolve()
        if not path.is_dir():
            return None
        name = self.outside_name_edit.text().strip() or path.name
        app_id = self.outside_appid_edit.text().strip() or "0"
        return ACFInfo(app_id, path)

    # ── Web UI toggle ────────────────────────────────────────────

    def _toggle_web_ui(self):
        self._web_ui_active = not self._web_ui_active
        from sff.storage.settings import set_setting
        from sff.structs import Settings as _S
        set_setting(_S.USE_MODERN_UI, self._web_ui_active)

        if self._web_ui_active:
            if self._web_view_freed:
                self._load_web_ui()
                self._web_view_freed = False
                self._web_ui_loaded = True
            elif not self._web_ui_loaded:
                self._load_web_ui()
                self._web_ui_loaded = True
            else:
                if self._web_index_path:
                    self._web_view.page().load(QUrl.fromLocalFile(str(self._web_index_path)))
            self.tabs.setVisible(False)
            self.tabs.setUpdatesEnabled(False)
            self.tabs.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._web_view.setVisible(True)
            self.menuBar().setVisible(False)
        else:
            self._build_classic_ui(self.steam_path)
            self.tabs.setVisible(True)
            self.tabs.setUpdatesEnabled(True)
            self.tabs.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self._web_view.setVisible(False)
            self._web_view.setUrl(QUrl("about:blank"))
            self._web_view_freed = True
            self.menuBar().setVisible(True)

    def _load_web_ui(self):
        """Load index.html into the QWebEngineView."""
        if getattr(sys, 'frozen', False):
            webui_dir = Path(sys._MEIPASS) / "sff" / "webui"
        else:
            webui_dir = Path(__file__).resolve().parent.parent / "webui"

        self._web_index_path = webui_dir / "index.html"
        if self._web_index_path.exists():
            self._web_view.setUrl(QUrl.fromLocalFile(str(self._web_index_path)))
        else:
            import logging
            logging.getLogger(__name__).error(
                "Web UI not found at %s", self._web_index_path
            )

    # ── Web UI splash overlay ────────────────────────────────────
    #
    # QtWebEngine paints a white surface for a few hundred ms between widget
    # show and the first frame from the renderer. The splash sits on top of
    # the QWebEngineView until index.html signals loadFinished(True), then
    # fades out over 150 ms. The label is parented to the view (not the
    # main window) so it does not register as a separate top-level window
    # or earn a taskbar entry.

    def _install_web_splash(self):
        # Linux: skip splash overlay entirely. The QLabel sitting on top
        # of the QWebEngineView interacts badly with Mesa-on-X11 surface
        # composition and leaves users (Sc0rthyn on Mint, Glitch on Mint)
        # staring at the splash because the fade-out doesnt fire when the
        # GPU swap chain is in software fallback. 6.2.3 didn't have a
        # splash and worked fine — keeping the same default.
        if sys.platform != "win32":
            self._web_splash = None
            self._web_splash_anim = None
            self._web_splash_effect = None
            return

        bg_hex = theme_background(self._current_theme)

        # QtWebEngine paints white before the page is up. setBackgroundColor
        # on the page plus an opaque widget background sheet means the
        # transition under the splash matches the theme.
        try:
            self._web_view.page().setBackgroundColor(QColor(bg_hex))
        except Exception:
            pass
        self._web_view.setStyleSheet(f"background-color: {bg_hex};")

        splash = QLabel(self._web_view)
        splash.setObjectName("WebSplashOverlay")
        splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        splash.setStyleSheet(
            f"QLabel#WebSplashOverlay {{ background-color: {bg_hex}; }}"
        )
        splash.setAutoFillBackground(True)

        for candidate in ("SFF.png", "SFF.ico"):
            try:
                from sff.utils import root_folder as _root_folder
                logo_path = _root_folder() / candidate
            except Exception:
                logo_path = Path(candidate)
            if logo_path.exists():
                pix = QPixmap(str(logo_path))
                if not pix.isNull():
                    splash.setPixmap(pix.scaled(
                        256, 256,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ))
                    break

        splash.resize(self._web_view.size())
        splash.raise_()
        splash.show()

        self._web_splash = splash
        self._web_splash_anim = None
        self._web_splash_effect = None

        # Keep the splash sized to the view across resizes.
        self._web_view.installEventFilter(self)

        self._web_view.loadFinished.connect(self._on_web_view_load_finished)

    def _on_web_view_load_finished(self, ok: bool):
        if not ok:
            self._web_view.setHtml(
                "<html><body style='background:#1a1a1a;color:#ccc;display:flex;"
                "align-items:center;justify-content:center;height:100vh;"
                "font-family:sans-serif;text-align:center'>"
                "<div><h2 style='color:#f0c040'>SteaMidra UI failed to load</h2>"
                "<p>Try restarting or switching to Classic UI in Settings.</p></div>"
                "</body></html>"
            )
        self.dismiss_splash()

    def _on_render_crash(self, status):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("QWebEngine render process crashed (status=%s), reloading once", status)
        try:
            self._install_web_splash()
            self._web_view.reload()
        except Exception:
            pass

    def dismiss_splash(self):
        splash = getattr(self, "_web_splash", None)
        if splash is None or not splash.isVisible():
            return

        effect = QGraphicsOpacityEffect(splash)
        effect.setOpacity(1.0)
        splash.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", splash)
        anim.setDuration(150)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_finished():
            try:
                splash.hide()
                splash.setGraphicsEffect(None)
            finally:
                self._web_splash_anim = None
                self._web_splash_effect = None

        anim.finished.connect(_on_finished)
        # Hold strong refs; the animation and effect die with the splash if
        # the user closes the window mid-fade.
        self._web_splash_effect = effect
        self._web_splash_anim = anim
        anim.start()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_web_view", None) and event.type() == QEvent.Type.Resize:
            splash = getattr(self, "_web_splash", None)
            if splash is not None and splash.isVisible():
                splash.resize(self._web_view.size())
        # Drag window by clicking the top 56px (where buttons are).
        # The web view intercepts mouse events so we handle it here.
        if sys.platform == "win32" and obj is getattr(self, "_web_view", None):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                y = event.position().y()
                if y < 56:
                    self._tb_drag_pos = event.globalPosition().toPoint()
                    return True
            elif event.type() == QEvent.Type.MouseMove and self._tb_drag_pos is not None:
                delta = event.globalPosition().toPoint() - self._tb_drag_pos
                self.move(self.pos() + delta)
                self._tb_drag_pos = event.globalPosition().toPoint()
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._tb_drag_pos = None
        return super().eventFilter(obj, event)

    # ── LumaCore status banner ───────────────────────────────────

    def _show_lumacore_banner(self, text: str):
        banner = getattr(self, "_lumacore_banner", None)
        if banner is None:
            return
        banner.setText(text)
        banner.setVisible(True)

    def _hide_lumacore_banner(self):
        banner = getattr(self, "_lumacore_banner", None)
        if banner is None:
            return
        banner.setVisible(False)

    # ── Worker management ────────────────────────────────────────

    def _start_worker(self, func, label: str = "action", on_done=None):
        # Detect a stale worker thread that is "not running" but the
        # references weren't reset yet (subprocess that opened a separate
        # cmd window and returned can leave us in this state). Treat
        # that as completed and proceed.
        if self._worker_thread is not None:
            try:
                still_running = self._worker_thread.isRunning()
            except Exception:
                still_running = False
            if not still_running:
                self._worker_thread = None
                self._worker = None
        if self._worker_thread is not None and self._worker_thread.isRunning():
            QMessageBox.information(self, "Busy", "An action is already running.")
            return
        self._append_log(f"\n--- Running: {label} ---\n")
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = self._stream_emitter  # type: ignore[assignment]
        sys.stderr = self._stream_emitter  # type: ignore[assignment]
        worker_error = {"message": ""}
        self._worker = GenericWorker(func)
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        def _on_finish(_result):
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            wt = self._worker_thread
            if wt is not None:
                try:
                    wt.quit()
                    # Cap the wait so a stuck thread doesn't freeze the
                    # whole window. The worker subprocess (Steamless,
                    # cmd window) has already returned by this point;
                    # we just need the QThread event loop to drain.
                    wt.wait(2000)
                except Exception:
                    pass
                try:
                    wt.deleteLater()
                except Exception:
                    pass
            self._worker_thread = None
            self._worker = None
            self._append_log(f"--- Done: {label} ---\n")
            if on_done:
                self._last_worker_error = worker_error.get("message", "")
                on_done()
        def _on_error(msg):
            worker_error["message"] = str(msg or "")
            self._append_log(f"Error: {msg}\n")
        self._worker.finished.connect(_on_finish)
        self._worker.error.connect(_on_error)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _open_workshop(self):
        acf = self._get_selected_acf()
        if acf is None:
            QMessageBox.warning(
                self,
                "No game selected",
                "Select a Steam game from the list or set a path for a game outside of Steam.",
            )
            return
        app_id = acf.app_id
        if not app_id:
            QMessageBox.warning(self, "No app ID", "Could not determine the game's App ID.")
            return
        from sff.gui.workshop_browser import open_workshop_browser
        open_workshop_browser(app_id, self)

    def _run_steamless_for_acf(self, acf):
        """Web UI entry point for Remove DRM (Steamless).

        Pops a single QFileDialog rooted at the game folder, runs Steamless
        on the picked exe, and surfaces the (success, message) tuple as a
        task_finished signal so the JS handler can show the result.

        Mirrors the classic UI Library-tab flow exactly so behaviour matches
        regardless of which UI the user clicked from.
        """
        import json
        from sff.gui.gui_prompts import _on_gui_thread

        def _pick_exe():
            start_dir = str(acf.path) if acf and acf.path else ""
            exe_path_str, _ = QFileDialog.getOpenFileName(
                self,
                "Select game executable",
                start_dir,
                "Executables (*.exe)",
            )
            return exe_path_str

        # Marshal to GUI thread because web_bridge calls us from a worker thread.
        exe_path_str = _on_gui_thread(_pick_exe)
        if not exe_path_str:
            # User cancelled — emit task_finished with a polite message.
            if hasattr(self, "_web_bridge") and self._web_bridge is not None:
                self._web_bridge.task_finished.emit(json.dumps({
                    "task": "steamstub",
                    "success": False,
                    "message": "Cancelled — no executable selected.",
                }))
            return

        exe_path = Path(exe_path_str)

        result_box: dict = {}
        def _runner():
            result_box["result"] = self.ui.run_steamless_direct(acf, exe_path)

        def _show_result():
            tup = result_box.get("result")
            ok, msg = (False, "Steamless: no result returned")
            if isinstance(tup, tuple) and len(tup) == 2:
                ok, msg = bool(tup[0]), str(tup[1])
            if hasattr(self, "_web_bridge") and self._web_bridge is not None:
                self._web_bridge.task_finished.emit(json.dumps({
                    "task": "steamstub",
                    "success": ok,
                    "message": msg,
                }))

        self._start_worker(_runner, "Remove SteamStub (Steamless)", on_done=_show_result)

    def _confirm_achievement_break(self, action_label: str) -> bool:
        """Warn before running an action that breaks Steam achievements.

        Returns True to proceed, False to cancel.
        Setting `WARN_BEFORE_BREAKING_ACHIEVEMENTS` is treated as opt-OUT:
        unset / True means warn, False means skip warning.
        """
        from sff.storage.settings import get_setting
        from sff.structs import Settings as _S
        try:
            val = get_setting(_S.WARN_BEFORE_BREAKING_ACHIEVEMENTS)
        except Exception:
            val = None
        # Only skip the warning when the user has explicitly opted out.
        if val is False:
            return True
        reply = QMessageBox.warning(
            self,
            f"{action_label} — breaks Steam achievements",
            f"Heads up — {action_label} will break Steam achievements.\n\n"
            "Replacing Steam's API with an emulator means achievements you earn after this "
            "will only save locally and will not appear on your Steam profile. Cloud saves "
            "will also stop syncing.\n\n"
            "For Steam-DRM games (Teardown, Doom Eternal, etc.) prefer "
            "Remove SteamStub (Steamless) instead — it strips the DRM wrapper without "
            "touching the Steam API, so achievements keep working.\n\n"
            "Continue anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _run_game_action(self, choice):
        from sff.structs import MainMenu
        acf = self._get_selected_acf()
        if acf is None:
            QMessageBox.warning(
                self,
                "No game selected",
                "Select a Steam game from the list or set a path for a game outside of Steam.",
            )
            return
        # Achievement-breakage gate — only for the gbe_fork crack path.
        if choice == MainMenu.CRACK_GAME:
            if not self._confirm_achievement_break("Crack game (gbe_fork)"):
                return
        label = str(getattr(choice, "value", choice))
        # Steamless: ask user to pick the exe directly so we never touch the Steam API
        # on a background thread (that's what causes WinError 2)
        if choice == MainMenu.REMOVE_DRM:
            exe_path_str, _ = QFileDialog.getOpenFileName(
                self,
                "Select game executable",
                str(acf.path),
                "Executables (*.exe)",
            )
            if not exe_path_str:
                return
            exe_path = Path(exe_path_str)
            # Capture the (success, message) tuple from apply_steamless via a
            # closure-stashed dict, then surface the result in a Qt popup so
            # users don't have to dig through the log panel.
            result_box: dict = {}
            def _runner():
                result_box["result"] = self.ui.run_steamless_direct(acf, exe_path)
            def _show_result():
                tup = result_box.get("result")
                if not tup:
                    return
                ok, msg = tup
                if ok:
                    QMessageBox.information(self, "Remove SteamStub (Steamless)", msg)
                else:
                    QMessageBox.warning(self, "Remove SteamStub (Steamless)", msg)
            self._start_worker(_runner, label, on_done=_show_result)
            return
        self._start_worker(
            lambda: self.ui.run_game_action_with_selection(choice, acf), label
        )

    def _ask_steamauto_mode(self) -> str | None:
        """Ask the user whether to run SteamAutoCrack in full mode
        (Goldberg + Steamless, breaks Steam achievements) or Steamless-only
        mode (just unpack SteamStub, achievement-safe).

        Returns 'full', 'steamless_only', or None if the user cancels.

        Honours the STEAMAUTO_DEFAULT_MODE setting: if set to "full" or
        "steamless_only", returns that directly without prompting. Empty
        string / unset means ask every time (the historical behaviour).
        """
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            saved = (get_setting(Settings.STEAMAUTO_DEFAULT_MODE) or "").strip()
            if saved in ("full", "steamless_only"):
                return saved
        except Exception:
            # Settings module not loaded yet, or the value is corrupt.
            # Fall through to the picker so the user is never blocked.
            pass

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("SteamAutoCrack Mode")
        box.setText("How would you like to run SteamAutoCrack?")
        box.setInformativeText(
            "Apply Both: install Goldberg emulator AND remove SteamStub. "
            "Breaks Steam achievements (Goldberg replaces the Steam API).\n\n"
            "Steamless only: just remove the SteamStub DRM wrapper. "
            "Achievement-safe — keeps the Steam API intact."
        )
        full_btn = box.addButton("Apply Both (Goldberg + Steamless)", QMessageBox.ButtonRole.AcceptRole)
        sl_btn = box.addButton("Steamless Only (achievement-safe)", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is full_btn:
            return "full"
        if clicked is sl_btn:
            return "steamless_only"
        return None

    def _run_steam_auto_gui(self):
        from sff.steamauto import get_steamauto_cli_path, run_steamauto
        if get_steamauto_cli_path() is None:
            QMessageBox.critical(
                self,
                "SteamAutoCrack not found",
                "SteamAutoCrack CLI is missing. Place the Steam-auto-crack repo in "
                "third_party/SteamAutoCrack and build the CLI into third_party/SteamAutoCrack/cli/.",
            )
            return
        acf = self._get_selected_acf()
        if acf is None:
            QMessageBox.warning(
                self,
                "No game selected",
                "Select a Steam game from the list or set a path for a game outside of Steam.",
            )
            return
        mode = self._ask_steamauto_mode()
        if mode is None:
            return
        # Steamless-only is achievement-safe, skip the warning. Full mode
        # still goes through the standard "this will break achievements"
        # confirmation.
        if mode == "full" and not self._confirm_achievement_break("SteamAutoCrack"):
            return
        game_path = acf.path
        app_id = acf.app_id or "0"
        def _job():
            code = run_steamauto(game_path, app_id, mode=mode, print_func=print)
            if code != 0:
                raise RuntimeError(f"SteamAutoCrack ({mode}) failed with exit code {code}")
        self._start_worker(_job, label=f"SteamAutoCrack ({mode})")

    def _run_steam_auto_with_acf(self, acf, mode: str | None = None):
        """Web UI entry point — ACF already resolved, runs on main thread via _start_worker.

        mode arg lets the Web UI pre-pick the mode after its own dialog.
        When None (legacy callers), this falls back to the Qt mode picker.
        """
        import json
        from sff.steamauto import run_steamauto
        if mode is None:
            mode = self._ask_steamauto_mode()
            if mode is None:
                return
        # The web UI shows its own confirmation dialog before calling here, so we
        # set _skip_next_achievement_warn from web_bridge to suppress the Qt prompt
        # and avoid double-warning. Classic UI calls _run_steam_auto_gui instead.
        if mode == "full" and not getattr(self, '_skip_next_achievement_warn', False):
            if not self._confirm_achievement_break("SteamAutoCrack"):
                return
        self._skip_next_achievement_warn = False
        game_path = acf.path
        app_id = acf.app_id or "0"
        result_box: dict = {"code": None}
        def _job():
            result_box["code"] = run_steamauto(game_path, app_id, mode=mode, print_func=print)
        def _done():
            if hasattr(self, '_web_bridge') and self._web_bridge:
                worker_error = getattr(self, "_last_worker_error", "")
                code = result_box.get("code")
                success = (not worker_error) and code == 0
                if worker_error:
                    message = f"SteamAutoCrack ({mode}) failed: {worker_error}"
                elif code == 0:
                    message = f"SteamAutoCrack ({mode}) completed"
                else:
                    message = f"SteamAutoCrack ({mode}) failed with exit code {code}"
                self._web_bridge.task_finished.emit(json.dumps({
                    "task": "steam_auto", "success": success,
                    "message": message,
                }))
        self._start_worker(_job, label=f"SteamAutoCrack ({mode})", on_done=_done)

    def _run_tool(self, func):
        label = getattr(func, "__name__", "tool")
        self._start_worker(func, label)

    # ── Log ──────────────────────────────────────────────────────

    def _show_log_window(self):
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def _append_log(self, text):
        text = _ANSI_RE.sub("", text)
        if not hasattr(self, 'log_text') or self.log_text is None:
            return
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    # ── Theme ────────────────────────────────────────────────────

    def _set_theme(self, key, save=True):
        self._current_theme = key
        _, style = THEMES[key]
        self.setStyleSheet(style)
        if hasattr(self, 'game_combo') and self.game_combo is not None:
            self.game_combo._update_arrow()
        if hasattr(self, '_tb_buttons') and self._tb_buttons:
            c = titlebar_colors(key)
            _s = (
                f"QPushButton {{ background: transparent; border: none; color: {c['fg']}; font-size: 22px; padding: 0; }}"
                f"QPushButton:hover {{ background-color: rgba(255,255,255,15); }}"
            )
            for _b in self._tb_buttons[:-1]:
                _b.setStyleSheet(_s)
            self._tb_buttons[-1].setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {c['fg']}; font-size: 22px; padding: 0; }}"
                f"QPushButton:hover {{ background-color: {c['close']}; color: #ffffff; }}"
            )
        if save:
            from sff.storage.settings import set_setting
            from sff.structs import Settings as _S
            set_setting(_S.THEME, key)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.windowState() & Qt.WindowState.WindowMaximized
            if self._tb_max_btn is not None:
                self._tb_maximized = bool(maximized)
                self._tb_max_btn.setText("\u29c9" if maximized else "\u25a1")
        super().changeEvent(event)

    if sys.platform == "win32":
        def nativeEvent(self, eventType, message):
            try:
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                if msg.message == 0x0083 and msg.wParam:
                    rect = ctypes.cast(
                        msg.lParam, ctypes.POINTER(ctypes.wintypes.RECT)
                    )
                    rimmed = ctypes.wintypes.RECT.from_address(
                        ctypes.addressof(rect.contents)
                    )
                    rect.contents.top = rimmed.top + 1
                    rect.contents.left = rimmed.left + 1
                    rect.contents.right = rimmed.right - 1
                    rect.contents.bottom = rimmed.bottom - 1
                    return (True, 0)
                if msg.message == 0x0084:
                    from PyQt6.QtCore import QPoint
                    pos = self.mapFromGlobal(QPoint(
                        ctypes.wintypes.LOWORD(msg.lParam),
                        ctypes.wintypes.HIWORD(msg.lParam),
                    ))
                    w, h = self.width(), self.height()
                    margin = 12
                    edge = 0
                    if pos.x() < margin:
                        edge |= 1
                    if pos.x() >= w - margin:
                        edge |= 2
                    if pos.y() < margin:
                        edge |= 4
                    if pos.y() >= h - margin:
                        edge |= 8
                    if edge:
                        HT_map = {
                            5: 13, 6: 14, 9: 16, 10: 17,
                            4: 12, 8: 15, 1: 10, 2: 11,
                        }
                        return (True, ctypes.c_ulong(HT_map.get(edge, 12)))
            except Exception:
                pass
            return (False, 0)

    # ── Log forwarding to web UI ────────────────────────────────

    def _forward_log_to_web(self, levelno: int, html: str):
        """Forward log records to the web bridge so the web UI log panel shows them.

        Buffered. The actual emit happens in `_flush_web_log_buffer`
        on a 100ms timer so a producer firing thousands of records
        per second cannot overwhelm QtWebEngine's renderer process.
        """
        if not getattr(self, '_web_ui_active', True):
            return
        if not (hasattr(self, '_web_bridge') and self._web_bridge):
            return
        import logging
        if levelno <= logging.DEBUG:
            lvl = 'DEBU'
        elif levelno <= logging.INFO:
            lvl = 'INFO'
        elif levelno <= logging.WARNING:
            lvl = 'WARN'
        else:
            lvl = 'ERRO'
        # Strip HTML tags for the web UI (it applies its own formatting)
        import re
        text = re.sub(r'<[^>]+>', '', html).strip()
        # Remove the leading HH:MM:SS timestamp already embedded by QtLogHandler
        # to avoid double-timestamps when the JS log panel adds its own.
        text = re.sub(r'^\d{2}:\d{2}:\d{2}\s*', '', text)
        if not text:
            return
        # Hard-drop list for known-spammy debug patterns. These fire per
        # filtered row during Store search and during preserver tick;
        # they're useful in debug.log on disk but in the live log panel
        # they pile up to hundreds of lines per query and the modern UI
        # gets bogged down. File log keeps them for triage. Live log
        # never sees them. The "not responding" reports during searching
        # were caused by this exact spam.
        if lvl == 'DEBU':
            _SPAM_NEEDLES = (
                'search_games: filtered Hubcap',
                'restore_manifest: no staged copy',
                'Cache hit for key:',
                'Cache expired for key:',
                'Loaded app ',
                'Cached data for key:',
                'Saved cache with',
            )
            for needle in _SPAM_NEEDLES:
                if needle in text:
                    return
        # Drop DEBUG lines first when the buffer is hot — debug noise
        # during parallel manifest downloads is the main offender and
        # the user can re-enable verbose logging from the log panel
        # itself if they need it.
        if lvl == 'DEBU' and len(self._web_log_buffer) > self._web_log_buffer_max // 2:
            self._web_log_dropped += 1
            return
        if len(self._web_log_buffer) >= self._web_log_buffer_max:
            self._web_log_dropped += 1
            return
        self._web_log_buffer.append(f'[{lvl}] {text}')

    def _forward_stdout_to_web(self, text: str):
        """Forward _stream_emitter stdout lines to the web UI log panel.

        Buffered. Same flush path as `_forward_log_to_web`.
        """
        if not getattr(self, '_web_ui_active', True):
            return
        if not (hasattr(self, '_web_bridge') and self._web_bridge):
            return
        text = _ANSI_RE.sub("", text).strip()
        if not text:
            return
        if len(self._web_log_buffer) >= self._web_log_buffer_max:
            self._web_log_dropped += 1
            return
        self._web_log_buffer.append(f'[INFO] {text}')

    def _buffer_qt_log(self, text: str):
        """Buffer a print() line for the Qt-side log surfaces.

        The legacy menubar QTextEdit and the dockable GlobalLogWindow
        used to be wired straight to the StreamEmitter signal, which
        meant every print() ran insertHtml + moveCursor on the GUI
        thread synchronously. The Steam-option download path prints
        hundreds of lines per depot and that turned the whole window
        unresponsive for the length of the download (c's 10-minute
        freeze). Buffer here, drain on the 100ms timer.
        """
        text = _ANSI_RE.sub("", text).strip()
        if not text:
            return
        if len(self._qt_log_buffer) >= self._qt_log_buffer_max:
            self._qt_log_dropped += 1
            return
        self._qt_log_buffer.append(text)

    def _flush_qt_log_buffer(self):
        """Drain buffered print() lines onto the Qt-side log surfaces.

        Two consumers: the dockable GlobalLogWindow and the legacy
        menubar QTextEdit. We join the buffered lines and run ONE
        insertHtml / insertPlainText per surface per tick, so a 200-
        line burst becomes 1 GUI-thread reflow instead of 200.
        """
        if not self._qt_log_buffer and not self._qt_log_dropped:
            return
        if self._qt_log_dropped > 0 and self._qt_log_buffer:
            dropped = self._qt_log_dropped
            self._qt_log_dropped = 0
            try:
                self._qt_log_buffer.append(
                    f'(Qt log batch dropped {dropped} line(s); throttled)'
                )
            except Exception:
                pass
        try:
            payload = '\n'.join(self._qt_log_buffer)
        except Exception:
            payload = ''
        self._qt_log_buffer.clear()
        if not payload:
            return
        log_window = getattr(self, '_log_window', None)
        if log_window is not None:
            try:
                log_window.append_text(payload)
            except Exception:
                pass
        log_text = getattr(self, 'log_text', None)
        if log_text is not None:
            try:
                self._append_log(payload + "\n")
            except Exception:
                pass

    def _flush_web_log_buffer(self):
        """Drain the buffered log lines onto the QtWebChannel.

        At most one emit per timer tick (100ms) and the payload is
        joined with newlines so the JS side does one DOM batch
        insert per tick, not per line.
        """
        if not getattr(self, '_web_ui_active', True):
            self._web_log_buffer.clear()
            return
        if not (hasattr(self, '_web_bridge') and self._web_bridge):
            return
        if not self._web_log_buffer and not self._web_log_dropped:
            return
        if self._web_log_dropped > 0 and self._web_log_buffer:
            # Surface dropped-lines count once per flush so the user
            # knows logging was throttled. Do not amplify under load:
            # the dropped marker counts towards the buffer cap on
            # the next tick.
            dropped = self._web_log_dropped
            self._web_log_dropped = 0
            try:
                self._web_log_buffer.append(
                    f'[WARN] (web log batch dropped {dropped} line(s) — verbose logging is throttled)'
                )
            except Exception:
                pass
        try:
            payload = '\n'.join(self._web_log_buffer)
        except Exception:
            payload = ''
        self._web_log_buffer.clear()
        if payload:
            try:
                self._web_bridge.log_message.emit(payload)
            except Exception:
                # Web bridge tore down between buffer fill and flush;
                # next tick will be a no-op.
                pass

    # ── Music mute ───────────────────────────────────────────────

    def _toggle_mute(self):
        if self.ui.midi_player is None:
            return
        self._music_muted = not self._music_muted
        self.ui.midi_player.set_muted(self._music_muted)
        self._mute_btn.setText("Unmute" if self._music_muted else "Mute")

    # ── Settings dialog ──────────────────────────────────────────

    def _show_settings(self):
        from sff.storage.settings import (
            clear_setting,
            export_settings,
            get_setting,
            import_settings,
            load_all_settings,
            set_setting,
        )
        from sff.structs import SettingCustomTypes, Settings
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumSize(620, 500)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Double-click a setting to edit. Select and press Delete to clear."))
        win_only: set[Settings] = set()
        linux_only = {Settings.SLS_CONFIG_LOCATION}
        skip: set[Settings] = set()
        if sys.platform == "win32":
            skip = linux_only
        elif sys.platform == "linux":
            skip = win_only
        lw = QListWidget()
        saved = load_all_settings()
        settings_order: list[Settings] = [s for s in Settings if s not in skip]
        def _refresh_list():
            nonlocal saved
            saved = load_all_settings()
            lw.clear()
            for s in settings_order:
                raw = saved.get(s.key_name)
                if raw is None:
                    val_str = "(unset)"
                elif s.hidden:
                    val_str = "[ENCRYPTED]"
                elif s.type == dict:
                    val_str = "(managed internally)"
                else:
                    val_str = str(raw)
                item = QListWidgetItem(f"{s.clean_name}: {val_str}")
                item.setData(Qt.ItemDataRole.UserRole, s)
                lw.addItem(item)
        from PyQt6.QtCore import Qt
        _refresh_list()
        layout.addWidget(lw)
        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        delete_btn = QPushButton("Delete")
        export_btn = QPushButton("Export")
        import_btn = QPushButton("Import")
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(export_btn)
        btn_row.addWidget(import_btn)
        layout.addLayout(btn_row)
        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(dlg.reject)
        layout.addWidget(close_btn)
        def _edit_setting():
            item = lw.currentItem()
            if not item:
                return
            s: Settings = item.data(Qt.ItemDataRole.UserRole)
            if s.type == dict:
                QMessageBox.information(dlg, "Info", f"{s.clean_name} is managed automatically.")
                return
            if s.type == bool:
                cur = get_setting(s)
                new_val = QMessageBox.question(
                    dlg,
                    s.clean_name,
                    f"Enable {s.clean_name}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes if cur else QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes
                set_setting(s, new_val)
            elif isinstance(s.type, list):
                names = [e.value for e in s.type]
                chosen, ok = QInputDialog.getItem(dlg, s.clean_name, "Select:", names, 0, False)
                if ok and chosen:
                    set_setting(s, chosen)
            elif s.type == SettingCustomTypes.DIR:
                path = QFileDialog.getExistingDirectory(dlg, s.clean_name)
                if path:
                    set_setting(s, str(Path(path).resolve()))
            elif s.type == SettingCustomTypes.FILE:
                path, _ = QFileDialog.getOpenFileName(dlg, s.clean_name)
                if path:
                    set_setting(s, str(Path(path).resolve()))
            elif s.type == str:
                if s.hidden:
                    val, ok = QInputDialog.getText(
                        dlg, s.clean_name, f"Enter {s.clean_name}:", QLineEdit.EchoMode.Password,
                    )
                else:
                    cur_val = get_setting(s) or ""
                    val, ok = QInputDialog.getText(
                        dlg, s.clean_name, f"Enter {s.clean_name}:", QLineEdit.EchoMode.Normal, str(cur_val),
                    )
                if ok:
                    set_setting(s, val)
            else:
                cur_val = get_setting(s) or ""
                val, ok = QInputDialog.getText(
                    dlg, s.clean_name, f"Enter {s.clean_name}:", QLineEdit.EchoMode.Normal, str(cur_val),
                )
                if ok:
                    set_setting(s, val)
            _refresh_list()
            self._apply_setting_live(s, dlg)
        def _delete_setting():
            item = lw.currentItem()
            if not item:
                return
            s: Settings = item.data(Qt.ItemDataRole.UserRole)
            if QMessageBox.question(
                dlg, "Delete", f"Clear {s.clean_name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                clear_setting(s)
                _refresh_list()
                self._apply_setting_live(s, dlg)
        def _export():
            path, _ = QFileDialog.getSaveFileName(dlg, "Export settings", "settings_export.json", "JSON (*.json)")
            if path:
                ok = export_settings(Path(path), include_sensitive=False)
                if ok:
                    QMessageBox.information(dlg, "Exported", f"Settings exported to {path}")
                else:
                    QMessageBox.warning(dlg, "Error", "Failed to export settings.")
        def _import():
            path, _ = QFileDialog.getOpenFileName(dlg, "Import settings", "", "JSON (*.json)")
            if not path:
                return
            if QMessageBox.question(
                dlg, "Import", "This will overwrite existing settings. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            ok, msg = import_settings(Path(path))
            if ok:
                QMessageBox.information(dlg, "Imported", msg)
                _refresh_list()
            else:
                QMessageBox.warning(dlg, "Error", msg)
        edit_btn.clicked.connect(_edit_setting)
        lw.itemDoubleClicked.connect(lambda _: _edit_setting())
        delete_btn.clicked.connect(_delete_setting)
        export_btn.clicked.connect(_export)
        import_btn.clicked.connect(_import)
        dlg.exec()

    def _apply_setting_live(self, s, parent_widget=None):
        from sff.structs import Settings
        if s == Settings.PLAY_MUSIC:
            from sff.storage.settings import get_setting
            val = get_setting(Settings.PLAY_MUSIC)
            if val:
                self.ui.kill_midi_player()
                self.ui.init_midi_player()
            else:
                self.ui.kill_midi_player()
        elif s == Settings.STEAM_PATH:
            if parent_widget:
                QMessageBox.information(
                    parent_widget,
                    "Restart Recommended",
                    "Steam path changed. Please restart SteaMidra for all changes to take full effect.",
                )
        elif s == Settings.LANGUAGE:
            from sff.i18n import set_language
            from sff.storage.settings import get_setting
            set_language(get_setting(Settings.LANGUAGE))
        elif s == Settings.SAVE_WATCHER_INTERVAL:
            self._start_save_watcher()
        elif s == Settings.SHOW_UPDATE_PROMPTS:
            # Apply the toggle to disk on the spot. LumaCore's hot-reload
            # watcher picks the .lua up without a Steam restart so the
            # next time the user looks at their library the prompt state
            # matches the toggle.
            try:
                from sff.update_prompt_override import apply_setting
                from sff.storage.settings import get_setting
                from sff.steam_path import validate_steam_path
                raw = get_setting(Settings.STEAM_PATH)
                steam_path = Path(raw) if raw else None
                if steam_path is not None and validate_steam_path(steam_path):
                    apply_setting(steam_path, bool(get_setting(Settings.SHOW_UPDATE_PROMPTS)))
            except Exception:
                logger.exception("SHOW_UPDATE_PROMPTS apply_setting raised")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_position_tb_buttons'):
            self._position_tb_buttons()
        if hasattr(self, '_drag_strip'):
            self._drag_strip.setGeometry(0, 0, self.width(), 56)
            self._drag_strip.raise_()

    def _tb_toggle_max(self):
        if self._tb_maximized:
            self.showNormal()
        else:
            self.showMaximized()

    def showEvent(self, event):
        super().showEvent(event)
        self._restore_webview_gpu()
        if hasattr(self, '_position_tb_buttons'):
            self._position_tb_buttons()
            for _b in self._tb_buttons:
                _b.raise_()
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_STYLE = -16
                WS_THICKFRAME = 0x00040000
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)
                SWP_FRAMECHANGED = 0x0020
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0,
                    SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
                )
            except Exception:
                pass

    def _release_webview_gpu(self):
        if not self._web_ui_active or not hasattr(self, '_web_view'):
            return
        try:
            self._web_view.setVisible(False)
        except Exception:
            pass

    def _restore_webview_gpu(self):
        if not self._web_ui_active or not hasattr(self, '_web_view'):
            return
        self._web_view.setVisible(True)

    # ── Tray / close-to-tray ────────────────────────────────────

    def set_tray(self, tray):
        self._tray = tray

    def force_quit(self):
        self._save_watcher_timer.stop()
        if hasattr(self, "_update_check_timer"):
            self._update_check_timer.stop()
        if hasattr(self, "_web_log_flush_timer") and self._web_log_flush_timer.isActive():
            self._web_log_flush_timer.stop()
        if hasattr(self, "_qt_log_flush_timer") and self._qt_log_flush_timer.isActive():
            self._qt_log_flush_timer.stop()
        if self._tray is not None:
            self._tray.minimize_to_tray = False
        self.close()

    def closeEvent(self, event):
        from sff.storage.settings import set_setting
        from sff.structs import Settings as _S
        try:
            set_setting(_S.WINDOW_GEOMETRY, self.saveGeometry().toHex().data().decode())
        except Exception:
            pass
        # Read live so Settings toggles take effect without restart.
        # Default ON: X button hides to tray. The user can flip the
        # CLOSE_TO_TRAY checkbox in Settings to make X quit instead.
        # Treat missing / empty / explicit-True values as ON; only
        # "False" / "false" / "0" disable tray behaviour.
        from sff.storage.settings import get_setting
        try:
            raw = get_setting(_S.CLOSE_TO_TRAY)
        except Exception:
            raw = None
        if raw is None or raw == "":
            close_to_tray = True
        elif isinstance(raw, bool):
            close_to_tray = raw
        else:
            close_to_tray = str(raw).strip().lower() not in ("false", "0", "no", "off")
        if (
            self._tray is not None
            and self._tray.minimize_to_tray
            and close_to_tray
        ):
            event.ignore()
            self.hide()
            self._release_webview_gpu()
            if not self._tray_hide_notified:
                self._tray_hide_notified = True
                self._tray.notify(
                    "SteaMidra",
                    "SteaMidra is running in the system tray. Click the ^ arrow near the clock to find it.",
                )
        else:
            # OFF branch: the tray icon is parented to QApplication, so leaving
            # it alive after event.accept() keeps the process running. Hide it
            # and drop the reference so QApplication has nothing to hold onto,
            # then quit + accept so the close finishes within ~1 s.
            if not getattr(self, "_quitting", False):
                self._quitting = True
                self._save_watcher_timer.stop()
                if hasattr(self, "_update_check_timer"):
                    self._update_check_timer.stop()
                tray = self._tray
                if tray is not None:
                    self._tray = None
                    try:
                        tray.minimize_to_tray = False
                    except Exception:
                        pass
                    try:
                        tray.hide()
                    except Exception:
                        pass
                QApplication.instance().quit()
            event.accept()

    # ── Background save watcher ──────────────────────────────────

    def _start_save_watcher(self):
        from sff.storage.settings import get_setting
        from sff.structs import Settings as _S
        try:
            interval_min = int(get_setting(_S.SAVE_WATCHER_INTERVAL) or 10)
        except (ValueError, TypeError):
            interval_min = 10
        self._save_watcher_timer.stop()
        if interval_min > 0:
            self._save_watcher_timer.start(interval_min * 60 * 1000)

    def _run_background_save_watcher(self):
        import threading
        t = threading.Thread(target=self._do_background_save_backup, daemon=True)
        t.start()

    def _do_background_save_backup(self):
        import json
        from sff.storage.settings import get_setting
        from sff.structs import Settings as _S
        steam32_id = get_setting(_S.STEAM32_ID)
        steam_path = getattr(self, 'steam_path', None)
        provider_config_raw = get_setting(_S.LAST_BACKUP_PROVIDER_CONFIG)
        if not steam32_id or not steam_path:
            return
        try:
            if provider_config_raw:
                cfg = json.loads(provider_config_raw)
                self._cloud_save_backup(cfg, steam_path, steam32_id)
            else:
                self._local_save_backup(steam_path, steam32_id)
        except Exception:
            logger.debug('Save watcher error', exc_info=True)

    def _local_save_backup(self, steam_path, steam32_id):
        from sff.cloud_saves import CloudSaves
        userdata_dir = Path(steam_path) / 'userdata' / str(steam32_id)
        if not userdata_dir.exists():
            return
        cs = CloudSaves()
        backed_up = 0
        for app_dir in userdata_dir.iterdir():
            if not app_dir.is_dir():
                continue
            remote_dir = app_dir / 'remote'
            if not remote_dir.exists():
                continue
            all_files = [f for f in remote_dir.rglob('*') if f.is_file()]
            if not all_files:
                continue
            last_mtime = max(f.stat().st_mtime for f in all_files)
            existing = cs.get_backups(app_dir.name)
            if existing:
                newest_ts = max(b.timestamp for b in existing)
                if last_mtime <= newest_ts:
                    continue
            cs.backup(app_dir.name, str(remote_dir))
            backed_up += 1
        if backed_up:
            logger.debug('Save watcher (local): backed up %d game(s)', backed_up)

    # ── 6.2.5: per-game update-available periodic check ──────────

    def _run_update_check_tick(self):
        """Walk installed apps and queue update checks under the gates.

        Reads GLOBAL_UPDATE_CHECK plus UPDATE_CHECK_INTERVAL_MIN on
        every tick so settings changes apply on the next sweep. Per-app
        overrides come from UPDATE_CHECK_OVERRIDES. Apps already
        dispatched within the last interval are skipped. The actual
        bridge calls fire one per 2 seconds across all apps via
        QTimer.singleShot chaining so the Steam CM provider is not
        hammered.
        """
        import time
        from sff.storage.settings import get_setting
        from sff.structs import Settings as _S
        try:
            global_on = get_setting(_S.GLOBAL_UPDATE_CHECK)
            if global_on is None or global_on == "":
                global_on = False
            if isinstance(global_on, str):
                global_on = global_on.lower() in ("true", "1", "yes", "on")
            if not global_on:
                # silenced — fires every 5 minutes and the user already
                # knows the toggle is off because they set it that way
                return
            try:
                interval_min = int(get_setting(_S.UPDATE_CHECK_INTERVAL_MIN) or 60)
            except (TypeError, ValueError):
                interval_min = 60
            if interval_min <= 0:
                return
            interval_sec = interval_min * 60
            raw = get_setting(_S.UPDATE_CHECK_OVERRIDES) or "{}"
            try:
                import json as _json
                overrides = _json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                overrides = {}
            if not isinstance(overrides, dict):
                overrides = {}
            bridge = getattr(self, "_web_bridge", None)
            if bridge is None or not hasattr(bridge, "check_game_update"):
                return
            try:
                installed = _json.loads(bridge.get_installed_games() or "[]")
            except Exception:
                installed = []
            now = time.time()
            queued: list[str] = []
            MAX_BATCH = 50
            for game in installed:
                app_id = str(game.get("app_id") or "").strip()
                if not app_id or app_id == "0":
                    continue
                if app_id in overrides and not bool(overrides[app_id]):
                    continue
                last = self._update_check_dispatched_at.get(app_id, 0.0)
                if now - last < interval_sec:
                    continue
                queued.append(app_id)
                if len(queued) >= MAX_BATCH:
                    break
            if not queued:
                return
            logger.info(
                "update-check tick: queued %d app(s) (interval=%dmin)",
                len(queued), interval_min,
            )
            self._update_check_pending_queue.extend(queued)
            if not self._update_check_dispatching:
                self._update_check_dispatching = True
                QTimer.singleShot(0, self._drain_update_check_queue)
        except Exception:
            logger.debug("update-check tick crashed", exc_info=True)

    def _drain_update_check_queue(self):
        """Pop one app off the pending queue and dispatch.

        Re-arms a 2-second singleShot until the queue empties. Errors
        from the bridge call propagate through the existing
        check_game_update path and never break the chain.
        """
        import time
        try:
            if not self._update_check_pending_queue:
                self._update_check_dispatching = False
                return
            app_id = self._update_check_pending_queue.pop(0)
            bridge = getattr(self, "_web_bridge", None)
            if bridge is not None and hasattr(bridge, "check_game_update"):
                try:
                    bridge.check_game_update(str(app_id))
                    self._update_check_dispatched_at[str(app_id)] = time.time()
                except Exception:
                    logger.debug(
                        "update-check dispatch failed for app_id=%s",
                        app_id, exc_info=True,
                    )
            if self._update_check_pending_queue:
                QTimer.singleShot(2000, self._drain_update_check_queue)
            else:
                self._update_check_dispatching = False
        except Exception:
            self._update_check_dispatching = False
            logger.debug("update-check drain crashed", exc_info=True)

    def _cloud_save_backup(self, cfg, steam_path, steam32_id):
        from sff.cloud_saves import (
            scan_all_save_locations,
            backup_save_location_local,
            backup_save_location_rclone,
            backup_save_location_gdrive,
        )
        entries = scan_all_save_locations(steam_path=steam_path, steam32_id=steam32_id)
        if not entries:
            return
        provider = cfg.get('provider', 'local').lower()
        backed_up = 0
        if provider == 'local':
            dest_path = cfg.get('dest_path', '')
            if not dest_path:
                return
            for entry in entries:
                if backup_save_location_local(entry, dest_path):
                    backed_up += 1
        elif provider == 'rclone':
            import subprocess
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import sys as _sys
            rclone_exe = cfg.get('rclone_exe', '')
            remote_dest = cfg.get('remote_dest', '')
            if not rclone_exe:
                from sff.utils import root_folder
                # Use the platform-aware folder: rclone (Windows) vs rclone_linux (Linux).
                _bundle_dir = "rclone" if _sys.platform == "win32" else "rclone_linux"
                _bundle_name = "rclone.exe" if _sys.platform == "win32" else "rclone"
                _bundled = root_folder() / "third_party" / _bundle_dir / _bundle_name
                if _bundled.exists():
                    rclone_exe = str(_bundled)
            if not rclone_exe or not remote_dest:
                return
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = {ex.submit(backup_save_location_rclone, e, rclone_exe, remote_dest): e for e in entries}
                for fut in as_completed(futures):
                    try:
                        if fut.result():
                            backed_up += 1
                    except Exception:
                        pass
        elif provider == 'gdrive_api':
            from sff.google_drive import get_service, get_backup_root, is_authenticated
            from concurrent.futures import ThreadPoolExecutor, as_completed
            if not is_authenticated():
                return
            svc = get_service()
            if not svc:
                return
            root_id = get_backup_root(svc)
            if not root_id:
                return
            folder_cache = {}
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = {ex.submit(backup_save_location_gdrive, e, get_service(), root_id,
                                     None, dict(folder_cache)): e for e in entries}
                for fut in as_completed(futures):
                    try:
                        if fut.result():
                            backed_up += 1
                    except Exception:
                        pass
        if backed_up:
            logger.debug('Save watcher (%s): backed up %d entries', provider, backed_up)

    # ── About ────────────────────────────────────────────────────

    def _show_about(self):
        from sff.strings import VERSION
        QMessageBox.about(
            self,
            "About SteaMidra",
            f"SteaMidra\nVersion {VERSION}\n\n"
            "https://github.com/Midrags/SFF/releases",
        )

    def _dump_achievement_diagnostic(self):
        """A16: read the LumaCore achievement diagnostic ring and surface
        it in a QMessageBox. LumaCore writes the file on detach, so a
        running session may see it empty until Steam restarts."""
        try:
            from sff.utils import sff_data_dir
            path = sff_data_dir() / "lumacore_diag.txt"
            if not path.exists():
                QMessageBox.information(
                    self,
                    T("Dump Achievement Diagnostic"),
                    T("No diagnostic captured yet (LumaCore writes on detach)"),
                )
                return
            data = path.read_bytes()
            tail = data[-16384:] if len(data) > 16384 else data
            text = tail.decode("utf-8", errors="replace") or T(
                "No diagnostic captured yet (LumaCore writes on detach)"
            )
            box = QMessageBox(self)
            box.setWindowTitle(T("Dump Achievement Diagnostic"))
            box.setText(f"{path}")
            box.setDetailedText(text)
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.exec()
        except Exception as exc:
            logger.exception("dump achievement diagnostic failed: %s", exc)
            QMessageBox.warning(
                self,
                T("Dump Achievement Diagnostic"),
                str(exc),
            )

    # ── LumaCore Setup helpers ────────────────────────────────────

    def _install_lumacore_gui(self):
        reply = QMessageBox.question(
            self,
            T("Install / Update LumaCore"),
            T("Steam will be closed and LumaCore will be installed into your Steam folder.\n\nContinue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        steam_path = self.steam_path
        if not steam_path or not Path(steam_path).is_dir():
            QMessageBox.warning(self, T("LumaCore Setup"), T("Steam path not found or invalid."))
            return

        def _job():
            from sff.lumacore_setup import install_lumacore
            install_lumacore(Path(steam_path), progress_callback=print)

        self._start_worker(_job, label="Install LumaCore")

    def _deactivate_lumacore_gui(self):
        reply = QMessageBox.warning(
            self,
            T("Deactivate LumaCore"),
            T("Steam will be closed and the LumaCore DLLs will be removed.\n\nContinue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        steam_path = self.steam_path
        if not steam_path or not Path(steam_path).is_dir():
            QMessageBox.warning(self, T("LumaCore Setup"), T("Steam path not found or invalid."))
            return

        def _job():
            from sff.lumacore_setup import deactivate_lumacore
            deactivate_lumacore(Path(steam_path), progress_callback=print)

        self._start_worker(_job, label="Deactivate LumaCore")

    def _check_lumacore_version_gui(self):
        steam_path = self.steam_path
        if not steam_path or not Path(steam_path).is_dir():
            QMessageBox.warning(self, T("LumaCore Version"), T("Steam path not found or invalid."))
            return
        result_box: dict = {}

        def _job():
            from sff.lumacore_setup import check_for_lumacore_update
            result_box["result"] = check_for_lumacore_update(Path(steam_path), force=True)

        def _show():
            result = result_box.get("result")
            if not isinstance(result, dict):
                QMessageBox.warning(self, T("LumaCore Version"), T("Version check failed."))
                return
            installed = result.get("installed") or T("not installed")
            latest = result.get("latest") or T("unknown")
            if result.get("update_available", False):
                msg = T(f"Update available!\n\nInstalled: {installed}\nLatest: {latest}")
            else:
                msg = T(f"LumaCore is up to date.\n\nInstalled: {installed}\nLatest: {latest}")
            QMessageBox.information(self, T("LumaCore Version"), msg)

        self._start_worker(_job, label="Check LumaCore Version", on_done=_show)

    def _toggle_online_fix_gui(self):
        acf = self._get_selected_acf()
        if acf is None:
            QMessageBox.warning(
                self,
                T("LC Online Fix"),
                T("Select a Steam game from the list first."),
            )
            return
        app_id = str(getattr(acf, "app_id", "") or "")
        if not app_id:
            QMessageBox.warning(self, T("LC Online Fix"), T("Could not determine the game's App ID."))
            return
        steam_path = self.steam_path
        if not steam_path or not Path(steam_path).is_dir():
            QMessageBox.warning(self, T("LC Online Fix"), T("Steam path not found or invalid."))
            return

        def _job():
            from sff.launch_options import toggle_online_fix
            ok, msg = toggle_online_fix(Path(steam_path), app_id)
            print(msg)
            return ok

        self._start_worker(_job, label=f"LC Online Fix ({app_id})")
