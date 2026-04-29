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
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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
from sff.gui.themes import THEMES
from sff.i18n import T
from sff.structs import MainMenu, MainReturnCode

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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
        self._game_list = []
        self._stream_emitter = StreamEmitter()
        self._log_window = GlobalLogWindow(self)
        self._log_handler = QtLogHandler()
        self._log_handler.setFormatter(
            __import__('logging').Formatter("%(name)s — %(message)s")
        )
        self._log_handler.setLevel(__import__('logging').DEBUG)
        self._log_handler.record_emitted.connect(self._log_window.append_record)
        __import__('logging').getLogger().addHandler(self._log_handler)
        self._worker = None
        self._worker_thread = None
        self.setWindowTitle("SteaMidra")
        self.setMinimumSize(960, 700)
        self.resize(1020, 780)
        from sff.gui.gui_prompts import update_parent
        update_parent(self)
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)
        main_tab_widget = QWidget()
        main_tab_layout = QVBoxLayout(main_tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        main_tab_layout.addWidget(scroll, stretch=1)
        self.tabs.addTab(main_tab_widget, "Main")
        from sff.gui.help_buttons import add_help_button
        add_help_button(
            layout,
            "Main Hub",
            "SteaMidra Main Hub\n\n"
            "Game / Path:\n"
            "  Select a Steam game from the dropdown or browse to a game\n"
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
            "  - Fixes/Bypasses (Ryuu): Apply community-maintained fixes.\n"
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
            "  - Manage AppList IDs: Add/remove App IDs in the GreenLuma\n"
            "    AppList folder so Steam shows them in your library.\n"
            "  - Offline mode fix: Patch config.vdf so Steam starts in\n"
            "    offline mode reliably.\n"
            "  - Mute: Toggle background music on/off.\n"
            "  - Remove game from library: Remove a game's ACF and AppList entry.\n"
            "  - Context menu: Add/remove SteaMidra from Windows Explorer\n"
            "    right-click menu.",
            parent_widget=self,
        )
        from sff.gui.store_tab import StoreTab
        from sff.gui.downloads_tab import DownloadsTab
        from sff.gui.fix_game_tab import FixGameTab
        from sff.gui.tools_tab import ToolsTab
        from sff.gui.cloud_saves_tab import CloudSavesTab
        from sff.download_manager import DownloadManager
        # Shared download manager — used by both the tracking tab and
        # the backend (process_lua_full) so downloads show up in the UI.
        self._download_manager = DownloadManager()
        self.ui.download_manager = self._download_manager
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
        # ── Game / path ──────────────────────────────────────────
        path_group = QGroupBox(T("Game / path"))
        path_layout = QVBoxLayout(path_group)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel(T("Path:")))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            T("Game folder (for outside Steam) or leave empty for Steam games")
        )
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
        quick_cc_btn = QPushButton("⚡ Quick ColdClient")
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
        for w in (
            self._outside_name_label,
            self.outside_name_edit,
            self._outside_appid_label,
            self.outside_appid_edit,
        ):
            w.setVisible(False)
        layout.addWidget(path_group)
        # ── Game Actions (need selected game) ────────────────────
        game_actions_group = QGroupBox(T("Game Actions"))
        ga_layout = QVBoxLayout(game_actions_group)
        ga_layout.setSpacing(6)
        _TOOLTIPS = {
            T("Crack game (gbe_fork)"): "Replace steam_api DLLs with Goldberg Emulator",
            T("Remove SteamStub (Steamless)"): "Strip Valve's SteamStub DRM from a game executable",
            T("UserGameStats"): "Download achievement / stats data for this game",
            T("DLC check"): "See which DLCs exist and which are unlocked",
            T("Workshop item"): "Download a Steam Workshop mod by its ID",
            T("Open Workshop"): "Browse the Steam Workshop for this game",
            T("Check mod updates"): "Check if downloaded Workshop mods have newer versions",
            T("Multiplayer fix"): "Apply online-fix.me multiplayer patches",
            T("Fixes/Bypasses (Ryuu)"): "Apply community-maintained fixes from Ryuu's collection",
            T("DLC Unlockers"): "Manage CreamAPI / SmokeAPI / other DLC unlocker DLLs",
            T("SteamAutoCrack"): "Run the SteamAutoCrack CLI tool on this game",
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
            (T("Fixes/Bypasses (Ryuu)"), MainMenu.RYUU_FIX),
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
        # ── Lua / Manifest Processing ────────────────────────────
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
        # ── Library & Steam Tools ────────────────────────────────
        tools_group = QGroupBox(T("Library & Steam Tools"))
        tools_layout = QVBoxLayout(tools_group)
        tools_row1 = QHBoxLayout()
        for label, func in [
            (T("Manage AppList IDs"), lambda: self.ui.applist_menu()),
            (T("Offline mode fix"), lambda: self.ui.offline_fix_menu()),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
            tools_row1.addWidget(btn)
        self._mute_btn = QPushButton("🔇 Mute")
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
        # ── Log ──────────────────────────────────────────────────
        log_group = QGroupBox(T("Log"))
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(160)
        log_layout.addWidget(self.log_text)
        clear_btn = QPushButton(T("Clear log"))
        clear_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_btn)
        layout.addWidget(log_group)
        # ── Menu bar ─────────────────────────────────────────────
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
        logs_action = menubar.addAction("Logs")
        logs_action.triggered.connect(self._show_log_window)
        self._stream_emitter.text_written.connect(self._append_log)
        self._set_theme(self._current_theme)
        self._on_source_changed()
        self._refresh_game_list()

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

    # ── Worker management ────────────────────────────────────────

    def _start_worker(self, func, label: str = "action"):
        if self._worker_thread is not None and self._worker_thread.isRunning():
            QMessageBox.information(self, "Busy", "An action is already running.")
            return
        self._append_log(f"\n--- Running: {label} ---\n")
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = self._stream_emitter  # type: ignore[assignment]
        sys.stderr = self._stream_emitter  # type: ignore[assignment]
        self._worker = GenericWorker(func)
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        def _on_finish(_result):
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            if self._worker_thread:
                self._worker_thread.quit()
                self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None
            self._append_log(f"--- Done: {label} ---\n")
        self._worker.finished.connect(_on_finish)
        self._worker.error.connect(lambda msg: self._append_log(f"Error: {msg}\n"))
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
            self._start_worker(
                lambda: self.ui.run_steamless_direct(acf, exe_path), label
            )
            return
        self._start_worker(
            lambda: self.ui.run_game_action_with_selection(choice, acf), label
        )

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
        game_path = acf.path
        app_id = acf.app_id or "0"
        def _job():
            run_steamauto(game_path, app_id, print_func=print)
        self._start_worker(_job, label="SteamAutoCrack")

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
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    # ── Theme ────────────────────────────────────────────────────

    def _set_theme(self, key):
        self._current_theme = key
        _, style = THEMES[key]
        self.setStyleSheet(style)
        self.game_combo._update_arrow()
        from sff.storage.settings import set_setting
        from sff.structs import Settings as _S
        set_setting(_S.THEME, key)

    # ── Music mute ───────────────────────────────────────────────

    def _toggle_mute(self):
        if self.ui.midi_player is None:
            return
        self._music_muted = not self._music_muted
        self.ui.midi_player.set_muted(self._music_muted)
        self._mute_btn.setText("🔊 Unmute" if self._music_muted else "🔇 Mute")

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
        win_only = {Settings.APPLIST_FOLDER, Settings.GL_VERSION}
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
        elif s == Settings.APPLIST_FOLDER:
            try:
                from sff.app_injector.applist import AppListManager
                import sys
                if sys.platform == "win32":
                    self.ui.app_list_man = AppListManager(
                        self.ui.steam_path, self.ui.provider
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to reinit AppListManager: {e}")
        elif s == Settings.STEAM_PATH:
            if parent_widget:
                QMessageBox.information(
                    parent_widget,
                    "Restart Recommended",
                    "Steam path changed. Please restart SteaMidra for all changes to take full effect.",
                )
        elif s == Settings.LANGUAGE:
            if parent_widget:
                QMessageBox.information(
                    parent_widget,
                    "Restart Required",
                    "Language changed. Please restart SteaMidra to apply the new language.",
                )

    # ── About ────────────────────────────────────────────────────

    def _show_about(self):
        from sff.strings import VERSION
        QMessageBox.about(
            self,
            "About SteaMidra",
            f"SteaMidra\nVersion {VERSION}\n\n"
            "https://github.com/Midrags/SFF/releases",
        )
