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

"""Cloud Saves tab — Steam userdata remote/ backup and restore."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QFileDialog, QFrame,
)

from sff.cloud_saves import CloudSaves
from sff.storage.settings import get_setting, set_setting
from sff.structs import Settings

logger = logging.getLogger(__name__)


class _BackupWorker(QObject):
    log_msg = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        mode: str,
        steam_path: str,
        steam32_id: str,
        app_id: int,
        game_name: str,
        dest_folder: str,
    ):
        super().__init__()
        self.mode = mode
        self.steam_path = steam_path
        self.steam32_id = steam32_id
        self.app_id = app_id
        self.game_name = game_name
        self.dest_folder = dest_folder

    def run(self):
        mgr = CloudSaves()
        if self.mode == "backup":
            result = mgr.backup_steam_save(
                self.steam_path,
                self.steam32_id,
                self.app_id,
                self.game_name,
                self.dest_folder,
                log_func=self.log_msg.emit,
            )
            if result:
                self.finished.emit(True, result)
            else:
                self.finished.emit(False, "Backup failed — check log above.")
        else:
            ok = mgr.restore_steam_save(
                self.dest_folder,
                self.steam_path,
                self.steam32_id,
                self.app_id,
                log_func=self.log_msg.emit,
            )
            self.finished.emit(ok, "" if ok else "Restore failed — check log above.")


class CloudSavesTab(QWidget):

    def __init__(self, steam_path, parent=None):
        super().__init__(parent)
        self.steam_path = steam_path
        self._manager = CloudSaves()
        self._worker: Optional[_BackupWorker] = None
        self._thread: Optional[QThread] = None
        self._games: list[tuple[int, str]] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from sff.gui.help_buttons import add_help_button
        add_help_button(
            layout,
            "Cloud Saves",
            "Cloud Saves — Backup & Restore\n\n"
            "Backup and restore Steam cloud save files. Useful for\n"
            "transferring saves between accounts or keeping a safety copy.\n\n"
            "Setup:\n"
            "  1. Set your Steam installation path.\n"
            "  2. Enter your Steam32 ID (find yours at steamid.xyz).\n"
            "  3. Click 'Scan Games' to find games with save data.\n\n"
            "Backup: Select a game and destination folder. Creates a\n"
            "  structured backup of the game's remote/ save folder.\n\n"
            "Import (Restore): Browse to a previously created backup\n"
            "  folder and restore saves back to Steam. Your current saves\n"
            "  are automatically backed up first as a safety measure.",
            parent_widget=self,
        )
        # ── Setup group ──────────────────────────────────────────
        setup_group = QGroupBox("Steam Setup")
        setup_layout = QVBoxLayout(setup_group)
        # Steam path row
        sp_row = QHBoxLayout()
        sp_row.addWidget(QLabel("Steam Path:"))
        self._steam_path_edit = QLineEdit(str(self.steam_path))
        sp_row.addWidget(self._steam_path_edit)
        browse_sp = QPushButton("Browse")
        browse_sp.clicked.connect(self._browse_steam_path)
        sp_row.addWidget(browse_sp)
        setup_layout.addLayout(sp_row)
        # Steam32 ID row
        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("Steam32 ID:"))
        self._steam32_edit = QLineEdit()
        saved_id = get_setting(Settings.STEAM32_ID)
        if saved_id:
            self._steam32_edit.setText(str(saved_id))
        else:
            self._steam32_edit.setPlaceholderText("e.g. 123456789  (find at steamid.xyz)")
        id_row.addWidget(self._steam32_edit)
        save_id_btn = QPushButton("Save ID")
        save_id_btn.clicked.connect(self._save_steam32_id)
        id_row.addWidget(save_id_btn)
        setup_layout.addLayout(id_row)
        scan_btn = QPushButton("Scan Games")
        scan_btn.clicked.connect(self._scan_games)
        setup_layout.addWidget(scan_btn)
        layout.addWidget(setup_group)
        # ── Game list ────────────────────────────────────────────
        games_group = QGroupBox("Games with Cloud Saves (remote/ folder)")
        games_layout = QVBoxLayout(games_group)
        self._games_table = QTableWidget()
        self._games_table.setColumnCount(2)
        self._games_table.setHorizontalHeaderLabels(["App ID", "Game Name"])
        self._games_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._games_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._games_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._games_table.setAlternatingRowColors(True)
        games_layout.addWidget(self._games_table)
        layout.addWidget(games_group)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)
        # ── Backup group ─────────────────────────────────────────
        backup_group = QGroupBox("Backup Saves")
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.addWidget(QLabel(
            "Select a game above, then choose where to save the backup.\n"
            "Creates: <destination>/<Game Name> [AppID]/remote/"
        ))
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Backup Destination:"))
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Choose a folder…")
        dest_row.addWidget(self._dest_edit)
        browse_dest = QPushButton("Browse")
        browse_dest.clicked.connect(self._browse_dest)
        dest_row.addWidget(browse_dest)
        backup_layout.addLayout(dest_row)
        self._backup_btn = QPushButton("Backup Selected Game")
        self._backup_btn.clicked.connect(self._do_backup)
        backup_layout.addWidget(self._backup_btn)
        layout.addWidget(backup_group)
        # ── Import / Restore group ───────────────────────────────
        restore_group = QGroupBox("Import (Restore) Saves")
        restore_layout = QVBoxLayout(restore_group)
        restore_layout.addWidget(QLabel(
            "Select a game above, then browse to the backup folder\n"
            "(the '<Game Name> [AppID]' folder created during backup).\n"
            "Current saves are automatically backed up before overwrite."
        ))
        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("Backup Folder:"))
        self._import_edit = QLineEdit()
        self._import_edit.setPlaceholderText("Browse to <Game Name> [AppID] folder…")
        import_row.addWidget(self._import_edit)
        browse_import = QPushButton("Browse")
        browse_import.clicked.connect(self._browse_import)
        import_row.addWidget(browse_import)
        restore_layout.addLayout(import_row)
        self._restore_btn = QPushButton("Import Saves → Steam")
        self._restore_btn.clicked.connect(self._do_restore)
        restore_layout.addWidget(self._restore_btn)
        layout.addWidget(restore_group)
        # ── Log ──────────────────────────────────────────────────
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(160)
        self._log.setPlaceholderText("Output will appear here…")
        layout.addWidget(self._log)

    # ── helpers ──────────────────────────────────────────────────

    def _browse_steam_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Steam Folder", str(self.steam_path))
        if path:
            self._steam_path_edit.setText(path)

    def _save_steam32_id(self):
        val = self._steam32_edit.text().strip()
        if not val.isdigit():
            QMessageBox.warning(self, "Invalid Steam32 ID", "Steam32 ID must be a number.\nFind yours at https://steamid.xyz/")
            return
        set_setting(Settings.STEAM32_ID, val)
        self._log.append(f"✓ Steam32 ID saved: {val}")

    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, "Select Backup Destination")
        if path:
            self._dest_edit.setText(path)

    def _browse_import(self):
        path = QFileDialog.getExistingDirectory(self, "Select Backup Folder (the '<Game Name> [AppID]' folder)")
        if path:
            self._import_edit.setText(path)

    def _validate_setup(self):
        """Returns (steam_path, steam32_id) or None if validation fails."""
        steam_path = self._steam_path_edit.text().strip()
        if not steam_path or not Path(steam_path).exists():
            QMessageBox.warning(self, "Invalid Steam Path", "Please enter a valid Steam installation path.")
            return None
        steam32_id = self._steam32_edit.text().strip()
        if not steam32_id or not steam32_id.isdigit():
            QMessageBox.warning(
                self, "Steam32 ID Missing",
                "Please enter your Steam32 ID.\nFind it at https://steamid.xyz/"
            )
            return None
        return steam_path, steam32_id

    def _scan_games(self):
        result = self._validate_setup()
        if not result:
            return
        steam_path, steam32_id = result
        self._log.clear()
        self._log.append(f"Scanning {steam_path}/userdata/{steam32_id}/ …")
        self._games = CloudSaves.list_steam_games(steam_path, steam32_id)
        self._games_table.setRowCount(len(self._games))
        for i, (app_id, game_name) in enumerate(self._games):
            self._games_table.setItem(i, 0, QTableWidgetItem(str(app_id)))
            self._games_table.setItem(i, 1, QTableWidgetItem(game_name))
        self._log.append(f"✓ Found {len(self._games)} game(s) with save data.")

    def _selected_game(self):
        row = self._games_table.currentRow()
        if row < 0 or row >= len(self._games):
            QMessageBox.warning(self, "No Game Selected", "Please select a game from the list.")
            return None
        return self._games[row]

    def _set_buttons_enabled(self, enabled):
        self._backup_btn.setEnabled(enabled)
        self._restore_btn.setEnabled(enabled)

    def _do_backup(self):
        result = self._validate_setup()
        if not result:
            return
        steam_path, steam32_id = result
        game = self._selected_game()
        if not game:
            return
        app_id, game_name = game
        dest = self._dest_edit.text().strip()
        if not dest:
            QMessageBox.warning(self, "No Destination", "Please choose a backup destination folder.")
            return
        self._run_worker("backup", steam_path, steam32_id, app_id, game_name, dest)

    def _do_restore(self):
        result = self._validate_setup()
        if not result:
            return
        steam_path, steam32_id = result
        game = self._selected_game()
        if not game:
            return
        app_id, game_name = game
        backup_folder = self._import_edit.text().strip()
        if not backup_folder:
            QMessageBox.warning(self, "No Backup Folder", "Please browse to the backup folder.")
            return
        reply = QMessageBox.question(
            self, "Confirm Import",
            f"Import saves for {game_name}?\n\nThis will overwrite current Steam saves.\n"
            f"(A safety backup is created automatically first.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_worker("restore", steam_path, steam32_id, app_id, game_name, backup_folder)

    def _run_worker(
        self, mode: str, steam_path: str, steam32_id: str,
        app_id: int, game_name: str, dest_folder: str,
    ):
        if self._thread and self._thread.isRunning():
            return
        self._log.clear()
        self._set_buttons_enabled(False)
        self._thread = QThread()
        self._worker = _BackupWorker(mode, steam_path, steam32_id, app_id, game_name, dest_folder)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log_msg.connect(self._log.append)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_done(self, succeeded, detail):
        self._set_buttons_enabled(True)
        if succeeded:
            self._log.append(f"\n✓ Done! {detail}")
        else:
            self._log.append(f"\n✗ {detail}")
