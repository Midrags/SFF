import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

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
)

from sff.gui.themes import THEMES
from sff.structs import MainMenu, MainReturnCode

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class StreamEmitter(QObject):
    text_written = pyqtSignal(str)

    def write(self, text: str) -> None:
        if text:
            self.text_written.emit(text)

    def flush(self) -> None:
        pass


class GenericWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self.func = func

    def run(self) -> None:
        try:
            result = self.func()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(None)


def _arrow_style_url(path: Path) -> str:
    """Return a stylesheet-ready url() string. Uses forward slashes for Windows Qt."""
    s = str(path.resolve()).replace("\\", "/")
    return f'"{s}"' if " " in s else s


_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"


class GameComboBox(QComboBox):
    """ComboBox with visible arrow that points down when closed, up when open."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._popup_open = False
        self._down_path = _RESOURCES_DIR / "arrow_down.png"
        self._up_path = _RESOURCES_DIR / "arrow_up.png"
        self._update_arrow()

    def showPopup(self) -> None:
        self._popup_open = True
        self._update_arrow()
        super().showPopup()

    def hidePopup(self) -> None:
        super().hidePopup()
        self._popup_open = False
        self._update_arrow()

    def _update_arrow(self) -> None:
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
    def __init__(self, ui: Any, steam_path: Path) -> None:
        super().__init__()
        self.ui = ui
        self.steam_path = steam_path
        self._current_theme = "dark"
        self._game_list: list[tuple[str, Any]] = []
        self._stream_emitter = StreamEmitter()
        self._worker: Optional[GenericWorker] = None
        self._worker_thread: Optional[QThread] = None

        self.setWindowTitle("SteamForge Fetcher (SFF)")
        self.setMinimumSize(960, 700)
        self.resize(1020, 780)

        from sff.gui.gui_prompts import update_parent
        update_parent(self)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        root_layout.addWidget(scroll, stretch=1)

        # ── Game / path ──────────────────────────────────────────
        path_group = QGroupBox("Game / path")
        path_layout = QVBoxLayout(path_group)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Path:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "Game folder (for outside Steam) or leave empty for Steam games"
        )
        path_row.addWidget(self.path_edit)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        path_layout.addLayout(path_row)

        source_row = QHBoxLayout()
        self.radio_steam = QRadioButton("Steam games")
        self.radio_steam.setChecked(True)
        self.radio_outside = QRadioButton("Games outside of Steam")
        self.radio_steam.toggled.connect(self._on_source_changed)
        self.radio_outside.toggled.connect(self._on_source_changed)
        source_row.addWidget(self.radio_steam)
        source_row.addWidget(self.radio_outside)
        source_row.addStretch()
        path_layout.addLayout(source_row)

        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("Game:"))
        self.game_combo = GameComboBox()
        self.game_combo.setMinimumWidth(280)
        game_row.addWidget(self.game_combo)
        refresh_btn = QPushButton("Refresh list")
        refresh_btn.clicked.connect(self._refresh_game_list)
        game_row.addWidget(refresh_btn)
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
        game_actions_group = QGroupBox("Game Actions")
        ga_layout = QVBoxLayout(game_actions_group)
        row1 = QHBoxLayout()
        for label, choice in [
            ("Crack game (gbe_fork)", MainMenu.CRACK_GAME),
            ("Remove SteamStub (Steamless)", MainMenu.REMOVE_DRM),
            ("UserGameStats", MainMenu.DL_USER_GAME_STATS),
            ("DLC check", MainMenu.DLC_CHECK),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, c=choice: self._run_game_action(c))
            row1.addWidget(btn)
        row1.addStretch()
        ga_layout.addLayout(row1)
        row2 = QHBoxLayout()
        for label, choice in [
            ("Workshop item", MainMenu.DL_WORKSHOP_ITEM),
            ("Multiplayer fix", MainMenu.MULTIPLAYER_FIX),
            ("DLC Unlockers", MainMenu.MANAGE_DLC_UNLOCKERS),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, c=choice: self._run_game_action(c))
            row2.addWidget(btn)
        row2.addStretch()
        ga_layout.addLayout(row2)
        layout.addWidget(game_actions_group)

        # ── Lua / Manifest Processing ────────────────────────────
        lua_group = QGroupBox("Lua / Manifest Processing")
        lua_layout = QVBoxLayout(lua_group)
        lua_row = QHBoxLayout()
        for label, func in [
            ("Process .lua file", lambda: self.ui.process_lua_full()),
            ("Download manifests only", lambda: self.ui.process_lua_minimal()),
            ("Recent .lua files", lambda: self.ui.recent_files_menu()),
            ("Update all manifests", lambda: self.ui.update_all_manifests()),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
            lua_row.addWidget(btn)
        lua_row.addStretch()
        lua_layout.addLayout(lua_row)
        layout.addWidget(lua_group)

        # ── Library & Steam Tools ────────────────────────────────
        tools_group = QGroupBox("Library && Steam Tools")
        tools_layout = QVBoxLayout(tools_group)
        tools_row1 = QHBoxLayout()
        for label, func in [
            ("Manage AppList IDs", lambda: self.ui.applist_menu()),
            ("Sync LUAs to Steam", lambda: self.ui.sync_lua_to_steam_menu()),
            ("Offline mode fix", lambda: self.ui.offline_fix_menu()),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
            tools_row1.addWidget(btn)
        tools_row1.addStretch()
        tools_layout.addLayout(tools_row1)

        if sys.platform == "win32":
            tools_row2 = QHBoxLayout()
            for label, func in [
                ("Remove game from library", lambda: self.ui.remove_game_menu()),
                ("Context menu", lambda: self.ui.manage_context_menu()),
            ]:
                btn = QPushButton(label)
                btn.clicked.connect(lambda checked=False, f=func: self._run_tool(f))
                tools_row2.addWidget(btn)
            tools_row2.addStretch()
            tools_layout.addLayout(tools_row2)
        layout.addWidget(tools_group)

        # ── Log ──────────────────────────────────────────────────
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(160)
        log_layout.addWidget(self.log_text)
        clear_btn = QPushButton("Clear log")
        clear_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_btn)
        layout.addWidget(log_group)

        # ── Menu bar ─────────────────────────────────────────────
        menubar = self.menuBar()
        settings_action = menubar.addAction("Settings")
        settings_action.triggered.connect(self._show_settings)
        theme_menu = menubar.addMenu("Theme")
        for key, (name, _) in THEMES.items():
            action = theme_menu.addAction(name)
            action.triggered.connect(lambda checked=False, k=key: self._set_theme(k))
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About").triggered.connect(self._show_about)
        help_menu.addAction("Check for updates").triggered.connect(
            lambda: self._run_tool(lambda: self.ui.check_updates(self.ui.os_type))
        )
        help_menu.addAction("Scan game library").triggered.connect(
            lambda: self._run_tool(lambda: self.ui.scan_library_menu())
        )
        help_menu.addAction("Analytics dashboard").triggered.connect(
            lambda: self._run_tool(lambda: self.ui.analytics_dashboard_menu())
        )

        self._stream_emitter.text_written.connect(self._append_log)
        self._set_theme(self._current_theme)
        self._on_source_changed()
        self._refresh_game_list()

    # ── Path / game source helpers ───────────────────────────────

    def _browse_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select game folder")
        if path:
            self.path_edit.setText(path)
            if self.radio_outside.isChecked() and not self.outside_name_edit.text().strip():
                self.outside_name_edit.setText(Path(path).name)

    def _on_source_changed(self) -> None:
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

    def _refresh_game_list(self) -> None:
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

    def _get_selected_acf(self) -> Optional[Any]:
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
        return ACFInfo(app_id, path, name=name)

    # ── Worker management ────────────────────────────────────────

    def _start_worker(self, func: Callable[[], Any], label: str = "action") -> None:
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

        def _on_finish(_result: Any) -> None:
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

    def _run_game_action(self, choice: Any) -> None:
        acf = self._get_selected_acf()
        if acf is None:
            QMessageBox.warning(
                self,
                "No game selected",
                "Select a Steam game from the list or set a path for a game outside of Steam.",
            )
            return
        label = str(getattr(choice, "value", choice))
        self._start_worker(
            lambda: self.ui.run_game_action_with_selection(choice, acf), label
        )

    def _run_tool(self, func: Callable[[], Any]) -> None:
        label = getattr(func, "__name__", "tool")
        self._start_worker(func, label)

    # ── Log ──────────────────────────────────────────────────────

    def _append_log(self, text: str) -> None:
        text = _ANSI_RE.sub("", text)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    # ── Theme ────────────────────────────────────────────────────

    def _set_theme(self, key: str) -> None:
        self._current_theme = key
        _, style = THEMES[key]
        self.setStyleSheet(style)

    # ── Settings dialog ──────────────────────────────────────────

    def _show_settings(self) -> None:
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

        def _refresh_list() -> None:
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

        def _edit_setting() -> None:
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

        def _delete_setting() -> None:
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

        def _export() -> None:
            path, _ = QFileDialog.getSaveFileName(dlg, "Export settings", "settings_export.json", "JSON (*.json)")
            if path:
                ok = export_settings(Path(path), include_sensitive=False)
                if ok:
                    QMessageBox.information(dlg, "Exported", f"Settings exported to {path}")
                else:
                    QMessageBox.warning(dlg, "Error", "Failed to export settings.")

        def _import() -> None:
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

    # ── About ────────────────────────────────────────────────────

    def _show_about(self) -> None:
        from sff.strings import VERSION

        QMessageBox.about(
            self,
            "About SFF",
            f"SteamForge Fetcher (SFF)\nVersion {VERSION}\n\n"
            "https://github.com/Midrags/SFF",
        )
