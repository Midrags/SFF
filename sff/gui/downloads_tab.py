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

"""Download Tracking tab — active queue, progress, and history."""

import time
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QProgressBar, QMessageBox,
)

from sff.download_manager import DownloadManager, DownloadStatus

logger = logging.getLogger(__name__)


class DownloadsTab(QWidget):

    def __init__(self, download_manager = None, parent=None):
        super().__init__(parent)
        self._dm = download_manager or DownloadManager()
        self._setup_ui()
        # refresh timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from sff.gui.help_buttons import add_help_button
        add_help_button(
            layout,
            "Download Tracking",
            "Download Tracking\n\n"
            "Monitor all your game downloads in real-time.\n\n"
            "Sections:\n"
            "  - Active Download: Shows the currently downloading game\n"
            "    with a progress bar and speed indicator.\n"
            "  - Queue: Games waiting to be downloaded next.\n"
            "  - Completed: Successfully finished downloads with timestamps.\n"
            "  - Failed: Downloads that encountered errors. Select one and\n"
            "    click Retry to try again.\n"
            "  - Download History: Full log of all past downloads.\n\n"
            "This tab auto-refreshes every second.",
            parent_widget=self,
        )
        # active download
        active_group = QGroupBox("Active Download")
        active_layout = QVBoxLayout(active_group)
        self._active_label = QLabel("No active download")
        active_layout.addWidget(self._active_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        active_layout.addWidget(self._progress_bar)
        self._speed_label = QLabel("")
        active_layout.addWidget(self._speed_label)
        layout.addWidget(active_group)
        # queue
        queue_group = QGroupBox("Queue")
        queue_layout = QVBoxLayout(queue_group)
        self._queue_table = QTableWidget()
        self._queue_table.setColumnCount(3)
        self._queue_table.setHorizontalHeaderLabels(["App ID", "Game", "Mode"])
        self._queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._queue_table.setMaximumHeight(150)
        queue_layout.addWidget(self._queue_table)
        layout.addWidget(queue_group)
        # completed
        done_group = QGroupBox("Completed")
        done_layout = QVBoxLayout(done_group)
        self._done_table = QTableWidget()
        self._done_table.setColumnCount(3)
        self._done_table.setHorizontalHeaderLabels(["App ID", "Game", "Time"])
        self._done_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._done_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._done_table.setMaximumHeight(150)
        done_layout.addWidget(self._done_table)
        clear_done_btn = QPushButton("Clear Completed")
        clear_done_btn.clicked.connect(self._clear_completed)
        done_layout.addWidget(clear_done_btn)
        layout.addWidget(done_group)
        # failed
        fail_group = QGroupBox("Failed")
        fail_layout = QVBoxLayout(fail_group)
        self._fail_table = QTableWidget()
        self._fail_table.setColumnCount(4)
        self._fail_table.setHorizontalHeaderLabels(["App ID", "Game", "Error", "Retries"])
        self._fail_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._fail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._fail_table.setMaximumHeight(150)
        fail_layout.addWidget(self._fail_table)
        fail_btn_layout = QHBoxLayout()
        retry_btn = QPushButton("Retry Selected")
        retry_btn.clicked.connect(self._retry_selected)
        fail_btn_layout.addWidget(retry_btn)
        clear_fail_btn = QPushButton("Clear Failed")
        clear_fail_btn.clicked.connect(self._clear_failed)
        fail_btn_layout.addWidget(clear_fail_btn)
        fail_btn_layout.addStretch()
        fail_layout.addLayout(fail_btn_layout)
        layout.addWidget(fail_group)
        # history
        hist_group = QGroupBox(f"Download History ({self._dm.history.count} entries)")
        hist_layout = QVBoxLayout(hist_group)
        self._hist_table = QTableWidget()
        self._hist_table.setColumnCount(4)
        self._hist_table.setHorizontalHeaderLabels(["App ID", "Game", "Status", "Date"])
        self._hist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._hist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hist_layout.addWidget(self._hist_table)
        clear_hist_btn = QPushButton("Clear History")
        clear_hist_btn.clicked.connect(self._clear_history)
        hist_layout.addWidget(clear_hist_btn)
        self._hist_group = hist_group
        layout.addWidget(hist_group)
        self._load_history()

    def _refresh(self):
        # active
        active = self._dm.get_active()
        if active:
            self._active_label.setText(f"{active.game_name} ({active.app_id})")
            self._progress_bar.setValue(active.progress)
            if active.total_bytes > 0:
                mb = active.downloaded_bytes / (1024 * 1024)
                total_mb = active.total_bytes / (1024 * 1024)
                self._speed_label.setText(f"{mb:.1f} / {total_mb:.1f} MB")
            else:
                self._speed_label.setText(f"{active.progress}%")
        else:
            self._active_label.setText("No active download")
            self._progress_bar.setValue(0)
            self._speed_label.setText("")
        # queue
        queue = self._dm.get_queue()
        self._queue_table.setRowCount(len(queue))
        for i, item in enumerate(queue):
            self._queue_table.setItem(i, 0, QTableWidgetItem(str(item.app_id)))
            self._queue_table.setItem(i, 1, QTableWidgetItem(item.game_name))
            self._queue_table.setItem(i, 2, QTableWidgetItem(item.mode.value))
        # completed
        completed = self._dm.get_completed()
        self._done_table.setRowCount(len(completed))
        for i, item in enumerate(completed):
            self._done_table.setItem(i, 0, QTableWidgetItem(str(item.app_id)))
            self._done_table.setItem(i, 1, QTableWidgetItem(item.game_name))
            t = time.strftime("%H:%M:%S", time.localtime(item.completed_at)) if item.completed_at else ""
            self._done_table.setItem(i, 2, QTableWidgetItem(t))
        # failed
        failed = self._dm.get_failed()
        self._fail_table.setRowCount(len(failed))
        for i, item in enumerate(failed):
            self._fail_table.setItem(i, 0, QTableWidgetItem(str(item.app_id)))
            self._fail_table.setItem(i, 1, QTableWidgetItem(item.game_name))
            self._fail_table.setItem(i, 2, QTableWidgetItem(item.error[:80]))
            self._fail_table.setItem(i, 3, QTableWidgetItem(f"{item.retry_count}/{item.max_retries}"))

    def _load_history(self):
        entries = self._dm.history.get_all()
        self._hist_table.setRowCount(len(entries))
        for i, entry in enumerate(reversed(entries)):
            self._hist_table.setItem(i, 0, QTableWidgetItem(str(entry.app_id)))
            self._hist_table.setItem(i, 1, QTableWidgetItem(entry.game_name))
            self._hist_table.setItem(i, 2, QTableWidgetItem(entry.status))
            t = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.timestamp)) if entry.timestamp else ""
            self._hist_table.setItem(i, 3, QTableWidgetItem(t))
        self._hist_group.setTitle(f"Download History ({len(entries)} entries)")

    def _clear_completed(self):
        self._dm.clear_completed()

    def _clear_failed(self):
        self._dm.clear_failed()

    def _retry_selected(self):
        row = self._fail_table.currentRow()
        if row < 0:
            return
        item = self._fail_table.item(row, 0)
        if item:
            app_id = int(item.text())
            self._dm.retry_download(app_id)

    def _clear_history(self):
        if QMessageBox.question(
            self, "Clear History", "Clear all download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._dm.history.clear()
            self._load_history()

    @property
    def download_manager(self):
        return self._dm
