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

"""Cloud Saves tab — STFixer mode + backup/restore game saves."""

import logging
from pathlib import Path
from typing import Optional
import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget, QTextEdit, QFrame,
)
from PyQt6.QtCore import Qt

from sff.cloud_saves import CloudSaves, BackupInfo

logger = logging.getLogger(__name__)


class CloudSavesTab(QWidget):

    def __init__(self, steam_path: Path, parent=None):
        super().__init__(parent)
        self.steam_path = steam_path
        self._manager = CloudSaves()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # mode selector
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Select how SteaMidra handles your saves:"))
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        cards_layout = QHBoxLayout()

        self._stfixer_btn = QPushButton("STFixer Mode")
        self._stfixer_btn.setCheckable(True)
        self._stfixer_btn.setChecked(True)
        self._stfixer_btn.setMinimumHeight(60)
        self._stfixer_btn.setToolTip(
            "Standard mode. Fixes broken saving in most Capcom games\n"
            "and some others without enabling save syncing to a cloud provider.\n"
            "Also enables the ability to use manifest pinning."
        )
        self._stfixer_btn.clicked.connect(lambda: self._switch_mode(0))
        cards_layout.addWidget(self._stfixer_btn)

        self._backup_btn = QPushButton("Backup / Restore Mode")
        self._backup_btn.setCheckable(True)
        self._backup_btn.setMinimumHeight(60)
        self._backup_btn.setToolTip(
            "Manually backup and restore game save files.\n"
            "Create snapshots of your saves and restore them later."
        )
        self._backup_btn.clicked.connect(lambda: self._switch_mode(1))
        cards_layout.addWidget(self._backup_btn)

        layout.addLayout(cards_layout)

        # separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # stacked pages
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_stfixer_page())
        self._stack.addWidget(self._build_backup_page())
        layout.addWidget(self._stack)

    def _switch_mode(self, index: int):
        self._stack.setCurrentIndex(index)
        self._stfixer_btn.setChecked(index == 0)
        self._backup_btn.setChecked(index == 1)

    # ── STFixer page ──────────────────────────────────────────

    def _build_stfixer_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        desc = QLabel(
            "STFixer patches broken save behavior in Capcom games (and some others).\n"
            "Based on STFixer v0.7.1 by Selectively11."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._stfix_log = QTextEdit()
        self._stfix_log.setReadOnly(True)
        self._stfix_log.setPlaceholderText("Fix output will appear here...")
        layout.addWidget(self._stfix_log)

        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply Fix")
        apply_btn.clicked.connect(self._apply_stfixer)
        btn_layout.addWidget(apply_btn)

        restore_btn = QPushButton("Restore Original")
        restore_btn.clicked.connect(self._restore_stfixer)
        btn_layout.addWidget(restore_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return page

    def _apply_stfixer(self):
        self._stfix_log.clear()
        try:
            from sff.tools.capcom_save_fix import CapcomSaveFix
            fixer = CapcomSaveFix()
            steam_dir = str(self.steam_path)
            self._stfix_log.append(f"Applying Capcom Save Fix (STFixer) to {steam_dir}...")
            result = fixer.apply(steam_dir, log_func=lambda msg: self._stfix_log.append(msg))
            if result.succeeded:
                self._stfix_log.append("Fix applied successfully!")
            elif result.error:
                self._stfix_log.append(f"ERROR: {result.error}")
        except Exception as e:
            self._stfix_log.append(f"CRITICAL ERROR: {e}")

    def _restore_stfixer(self):
        self._stfix_log.clear()
        try:
            from sff.tools.capcom_save_fix import CapcomSaveFix
            fixer = CapcomSaveFix()
            steam_dir = str(self.steam_path)
            self._stfix_log.append(f"Restoring original files in {steam_dir}...")
            result = fixer.restore(steam_dir, log_func=lambda msg: self._stfix_log.append(msg))
            if result.succeeded:
                self._stfix_log.append("Restore completed!")
            elif result.error:
                self._stfix_log.append(f"ERROR: {result.error}")
        except Exception as e:
            self._stfix_log.append(f"CRITICAL ERROR: {e}")

    # ── Backup / Restore page ─────────────────────────────────

    def _build_backup_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # target game
        target_group = QGroupBox("Target Game")
        target_layout = QVBoxLayout(target_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("App ID:"))
        self._app_id_edit = QLineEdit()
        row1.addWidget(self._app_id_edit)

        row1.addWidget(QLabel("Game Name:"))
        self._game_name_edit = QLineEdit()
        row1.addWidget(self._game_name_edit)

        detect_btn = QPushButton("Load Backups")
        detect_btn.clicked.connect(self._load_backups)
        row1.addWidget(detect_btn)
        target_layout.addLayout(row1)

        row2 = QHBoxLayout()
        backup_btn = QPushButton("Create New Backup")
        backup_btn.clicked.connect(self._create_backup)
        row2.addWidget(backup_btn)
        target_layout.addLayout(row2)

        layout.addWidget(target_group)

        # backups list
        list_group = QGroupBox("Available Backups")
        list_layout = QVBoxLayout(list_group)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Date", "App ID", "Game", "Size (bytes)"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        list_layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        restore_btn = QPushButton("Restore Selected")
        restore_btn.clicked.connect(self._restore_selected)
        btn_layout.addWidget(restore_btn)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        refresh_btn = QPushButton("Refresh All")
        refresh_btn.clicked.connect(self._refresh_all)
        btn_layout.addWidget(refresh_btn)

        list_layout.addLayout(btn_layout)
        layout.addWidget(list_group)

        self._refresh_all()
        return page

    # ── Backup logic ──────────────────────────────────────────

    def _load_backups(self):
        app_id_str = self._app_id_edit.text().strip()
        if app_id_str and app_id_str.isdigit():
            backups = self._manager.get_backups(int(app_id_str))
            self._populate_table(backups)
        else:
            QMessageBox.warning(self, "Invalid Request", "Please specify a valid App ID.")

    def _refresh_all(self):
        all_backups = []
        if self._manager.backup_dir.exists():
            for app_dir in self._manager.backup_dir.iterdir():
                if app_dir.is_dir() and app_dir.name.isdigit():
                    all_backups.extend(self._manager.get_backups(int(app_dir.name)))
        self._populate_table(all_backups)

    def _populate_table(self, backups: list[BackupInfo]):
        backups.sort(key=lambda b: b.timestamp, reverse=True)
        self._table.setRowCount(len(backups))
        for i, b in enumerate(backups):
            dt = datetime.datetime.fromtimestamp(b.timestamp).strftime('%Y-%m-%d %H:%M:%S')
            self._table.setItem(i, 0, QTableWidgetItem(dt))
            self._table.setItem(i, 1, QTableWidgetItem(str(b.app_id)))
            self._table.setItem(i, 2, QTableWidgetItem(b.game_name))
            self._table.setItem(i, 3, QTableWidgetItem(str(b.total_size)))
            self._table.item(i, 0).setData(Qt.ItemDataRole.UserRole, b)

    def _create_backup(self):
        app_id_str = self._app_id_edit.text().strip()
        game_name = self._game_name_edit.text().strip() or "Unknown Game"

        if not app_id_str or not app_id_str.isdigit():
            QMessageBox.warning(self, "Invalid Input", "Please provide a valid App ID.")
            return

        app_id = int(app_id_str)
        try:
            saves = self._manager.detect_saves(app_id, game_name)
            if not saves:
                QMessageBox.warning(self, "No Saves Found", "Could not detect save locations for this game.")
                return

            save_path = saves[0].save_path
            backup_info = self._manager.backup(app_id, save_path, game_name)
            if backup_info:
                QMessageBox.information(self, "Success", f"Backup created successfully at:\n{backup_info.backup_path}")
                self._load_backups()
            else:
                QMessageBox.critical(self, "Error", "Failed to create backup.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create backup: {e}")

    def _get_selected_backup(self) -> Optional[BackupInfo]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _restore_selected(self):
        backup = self._get_selected_backup()
        if not backup:
            return

        reply = QMessageBox.question(
            self, "Restore Backup",
            f"Restore backup for {backup.game_name}?\n\nWARNING: This will overwrite current save files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                manifest = self._manager._load_manifest(backup.app_id)
                save_path = manifest.get("save_path")
                if not save_path:
                    saves = self._manager.detect_saves(backup.app_id, backup.game_name)
                    save_path = saves[0].save_path if saves else ""

                if not save_path:
                    QMessageBox.warning(self, "Error", "Could not determine save path to restore to.")
                    return

                success = self._manager.restore(backup.app_id, backup.backup_path, save_path)
                if success:
                    QMessageBox.information(self, "Success", "Backup restored successfully.")
                else:
                    QMessageBox.critical(self, "Error", "Failed to restore backup.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restore backup: {e}")

    def _delete_selected(self):
        backup = self._get_selected_backup()
        if not backup:
            return

        reply = QMessageBox.question(
            self, "Delete Backup",
            f"Delete backup for {backup.game_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = self._manager.delete_backup(backup.backup_path)
                if success:
                    self._refresh_all()
                else:
                    QMessageBox.critical(self, "Error", "Failed to delete backup.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete backup: {e}")
