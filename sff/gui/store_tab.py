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

"""Store tab — browse and search the Morrenus manifest library."""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QMessageBox, QProgressBar, QComboBox,
)

logger = logging.getLogger(__name__)


class _FetchWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, client, query, page, per_page=100):
        super().__init__()
        self.client = client
        self.query = query
        self.page = page
        self.per_page = per_page

    def run(self):
        try:
            offset = (self.page - 1) * self.per_page
            # always use /library endpoint (supports search= param) for proper pagination
            result = self.client.get_library(
                limit=self.per_page,
                offset=offset,
                search=self.query if self.query else None,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class StoreTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = None
        self._current_page = 1
        self._total_pages = 1
        self._worker = None
        self._thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # API key config
        key_group = QGroupBox("API Configuration")
        key_layout = QHBoxLayout(key_group)
        key_layout.addWidget(QLabel("Morrenus API Key:"))
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("Enter your smm_ API key")
        key_layout.addWidget(self._key_edit)
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._connect)
        key_layout.addWidget(self._connect_btn)
        layout.addWidget(key_group)

        # try to load saved key
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            saved_key = get_setting(Settings.MORRENUS_KEY)
            if saved_key:
                self._key_edit.setText(str(saved_key))
        except Exception:
            pass

        # search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Game name or App ID...")
        self._search_edit.returnPressed.connect(self._search)
        search_layout.addWidget(self._search_edit)
        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._search)
        search_layout.addWidget(self._search_btn)
        self._browse_btn = QPushButton("Browse All")
        self._browse_btn.clicked.connect(self._browse_all)
        search_layout.addWidget(self._browse_btn)
        layout.addLayout(search_layout)

        # results table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["App ID", "Name", "Status", "Last Updated"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # pagination
        page_layout = QHBoxLayout()
        self._prev_btn = QPushButton("← Previous")
        self._prev_btn.clicked.connect(self._prev_page)
        self._prev_btn.setEnabled(False)
        page_layout.addWidget(self._prev_btn)
        page_layout.addStretch()
        self._page_label = QLabel("Page 1 of 1")
        page_layout.addWidget(self._page_label)
        page_layout.addStretch()
        self._next_btn = QPushButton("Next →")
        self._next_btn.clicked.connect(self._next_page)
        self._next_btn.setEnabled(False)
        page_layout.addWidget(self._next_btn)
        layout.addLayout(page_layout)

        # status
        self._status_label = QLabel("Enter API key and click Connect to start browsing.")
        layout.addWidget(self._status_label)

    def _connect(self):
        key = self._key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Missing Key", "Please enter your Morrenus API key.")
            return

        try:
            from sff.store_browser import StoreApiClient
            if not StoreApiClient.validate_api_key(key):
                QMessageBox.warning(self, "Invalid Key", "API key should start with 'smm_' and be at least 10 characters.")
                return
            self._client = StoreApiClient(api_key=key)
            self._status_label.setText("Connected! Search or browse the library.")
            self._connect_btn.setText("Reconnect")

            # save key
            try:
                from sff.storage.settings import set_setting
                from sff.structs import Settings
                set_setting(Settings.MORRENUS_KEY, key)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", str(e))

    def _search(self):
        query = self._search_edit.text().strip()
        if not query:
            return
        self._current_page = 1
        self._fetch(query)

    def _browse_all(self):
        self._current_page = 1
        self._search_edit.clear()
        self._fetch("")

    def _prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._fetch(self._search_edit.text().strip())

    def _next_page(self):
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._fetch(self._search_edit.text().strip())

    def _fetch(self, query: str):
        if not self._client:
            QMessageBox.warning(self, "Not Connected", "Connect with your API key first.")
            return

        self._status_label.setText("Loading...")
        self._search_btn.setEnabled(False)

        self._thread = QThread()
        self._worker = _FetchWorker(self._client, query, self._current_page)
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_results(self, result):
        self._search_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()

        if result is None:
            self._status_label.setText("No results.")
            return

        games = result.games if hasattr(result, 'games') else []
        self._total_pages = result.total_pages if hasattr(result, 'total_pages') else 1

        self._table.setRowCount(len(games))
        for row, game in enumerate(games):
            self._table.setItem(row, 0, QTableWidgetItem(str(game.app_id)))
            self._table.setItem(row, 1, QTableWidgetItem(game.name))
            status = game.status if hasattr(game, 'status') else "unknown"
            self._table.setItem(row, 2, QTableWidgetItem(status))
            updated = game.last_updated if hasattr(game, 'last_updated') else ""
            self._table.setItem(row, 3, QTableWidgetItem(str(updated)))

        self._page_label.setText(f"Page {self._current_page} of {self._total_pages}")
        self._prev_btn.setEnabled(self._current_page > 1)
        self._next_btn.setEnabled(self._current_page < self._total_pages)
        self._status_label.setText(f"Showing {len(games)} results (page {self._current_page}/{self._total_pages})")

    def _on_error(self, msg):
        self._search_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._status_label.setText(f"Error: {msg}")
