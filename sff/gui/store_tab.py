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

"""Store tab — browse and search the Hubcap Manifest library."""

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QUrl
from PyQt6.QtGui import QDesktopServices, QColor, QBrush, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QMessageBox, QProgressBar, QComboBox,
    QDialog, QDialogButtonBox, QCheckBox, QScrollArea, QFrame,
    QFormLayout,
)

logger = logging.getLogger(__name__)


class _ManualEntryDialog(QDialog):
    """Small dialog to enter a Depot ID + Manifest ID manually."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Depot Manually")
        self.setFixedSize(360, 140)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._depot_edit = QLineEdit()
        self._depot_edit.setPlaceholderText("e.g. 1234567")
        self._manifest_edit = QLineEdit()
        self._manifest_edit.setPlaceholderText("e.g. 1234567890123456789")
        form.addRow("Depot ID:", self._depot_edit)
        form.addRow("Manifest ID:", self._manifest_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        if not self._depot_edit.text().strip().isdigit():
            QMessageBox.warning(self, "Invalid Input", "Depot ID must be a number.")
            return
        if not self._manifest_edit.text().strip().isdigit():
            QMessageBox.warning(self, "Invalid Input", "Manifest ID must be a number.")
            return
        self.accept()

    def get_values(self) -> tuple[str, str]:
        return self._depot_edit.text().strip(), self._manifest_edit.text().strip()


class _DepotHistoryWorker(QObject):
    """Fetches depot list + manifest history for a game in background."""
    finished = pyqtSignal(object)  # dict: {depot_id: [ManifestEntry]}
    error = pyqtSignal(str)
    progress = pyqtSignal(str)     # live status messages (e.g. SteamDB per-depot)

    def __init__(self, app_id: int, client=None):
        super().__init__()
        self.app_id = app_id
        self.client = client

    def run(self):
        try:
            if self.client:
                try:
                    depot_ids = self.client.get_game_depots(self.app_id)
                    _ = depot_ids  # kept for Morrenus compatibility
                except Exception as e:
                    logger.debug(f"Morrenus depot list (unused): {e}")

            from sff.manifest.depot_history import get_depots_for_app
            result = get_depots_for_app(str(self.app_id), progress_cb=self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


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


class VersionPickerDialog(QDialog):
    """
    Shows depot manifest versions grouped by (date, branch, source).
    Each group has a colored header row with a master checkbox.
    Checking the header checks all depot rows in that version package.
    """

    # Source -> header background color (dark tints)
    _SOURCE_BG: dict[str, str] = {
        "Steam CM":       "#1e3a5f",
        "GitHub mirror":  "#1a3322",
        "local fallback": "#3a2e10",
        "SteamDB":        "#2e1a3a",
    }
    _DEFAULT_BG = "#2a2a2a"

    def __init__(self, app_id: int, game_name: str, depot_history: dict,
                 steam_path: Optional[Path], parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.game_name = game_name
        self.depot_history = depot_history  # {depot_id_str: [ManifestEntry]}
        self.steam_path = steam_path
        self.setWindowTitle(f"Download Version — {game_name} ({app_id})")
        self.setMinimumSize(860, 560)
        self._setup_ui()

    def _setup_ui(self):
        from sff.manifest.depot_history import group_by_version, has_depot_key

        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>{self.game_name}</b>  ·  App {self.app_id}<br>"
            "Each colored row is a <b>version package</b>. Check a header to select all its depots, "
            "then click <b>Download Selected</b>."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._checkboxes: list[tuple[str, str, QCheckBox]] = []  # (depot_id, manifest_id, chk)

        if not self.depot_history:
            layout.addWidget(QLabel(
                "⚠️  No manifest history found for this game.\n"
                "This game has no entries in the GitHub mirror or local fallback, and "
                "Steam CM returned no depot data."
            ))
        else:
            version_groups = group_by_version(self.depot_history)

            total_rows = sum(2 + len(g.entries) for g in version_groups)  # +1 per group for the "+" row
            self._table = QTableWidget()
            self._table.setColumnCount(7)
            self._table.setHorizontalHeaderLabels(
                ["✓", "Depot ID", "Manifest ID", "Date", "Branch", "Source", "Key"]
            )
            self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            self._table.setRowCount(total_rows)

            bold_font = QFont()
            bold_font.setBold(True)

            depot_idx = 0   # index into self._checkboxes
            table_row = 0

            for g_idx, group in enumerate(version_groups):
                hex_bg = self._SOURCE_BG.get(group.source, self._DEFAULT_BG)
                hdr_bg = QColor(hex_bg)
                white = QColor("#ffffff")
                first_group = (g_idx == 0)

                # ---- Header row ----
                master_chk = QCheckBox()
                master_chk.setChecked(first_group)
                chk_w = QWidget()
                chk_l = QHBoxLayout(chk_w)
                chk_l.addWidget(master_chk)
                chk_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                chk_l.setContentsMargins(2, 0, 2, 0)
                chk_w.setStyleSheet(f"background-color: {hex_bg};")
                self._table.setCellWidget(table_row, 0, chk_w)

                lbl_item = QTableWidgetItem(f"  {group.label}")
                lbl_item.setFont(bold_font)
                lbl_item.setBackground(QBrush(hdr_bg))
                lbl_item.setForeground(QBrush(white))
                lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self._table.setItem(table_row, 1, lbl_item)
                self._table.setSpan(table_row, 1, 1, 6)
                self._table.setRowHeight(table_row, 28)
                table_row += 1

                # ---- Depot rows ----
                group_start = depot_idx
                group_count = 0

                for depot_id, manifest_id in group.entries:
                    entry = group.entry_map.get(depot_id)

                    chk = QCheckBox()
                    chk.setChecked(first_group)
                    cw = QWidget()
                    cl = QHBoxLayout(cw)
                    cl.addWidget(chk)
                    cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cl.setContentsMargins(2, 0, 2, 0)
                    self._table.setCellWidget(table_row, 0, cw)

                    self._table.setItem(table_row, 1, QTableWidgetItem(depot_id))
                    self._table.setItem(table_row, 2, QTableWidgetItem(manifest_id))
                    date_val = entry.date if entry else "—"
                    self._table.setItem(table_row, 3, QTableWidgetItem(date_val))
                    branch_val = entry.branch if entry else group.branch
                    self._table.setItem(table_row, 4, QTableWidgetItem(branch_val))
                    src_val = entry.source if entry else group.source
                    self._table.setItem(table_row, 5, QTableWidgetItem(src_val))
                    key_str = "\u2713" if has_depot_key(depot_id) else "\u2013"
                    self._table.setItem(table_row, 6, QTableWidgetItem(key_str))

                    self._checkboxes.append((depot_id, manifest_id, chk))
                    depot_idx += 1
                    group_count += 1
                    table_row += 1

                # Wire master checkbox to toggle all depot checkboxes in this group
                def _make_handler(start: int, count: int):
                    def _handler(state: int) -> None:
                        checked = (state == 2)
                        for _, _, c in self._checkboxes[start:start + count]:
                            c.blockSignals(True)
                            c.setChecked(checked)
                            c.blockSignals(False)
                    return _handler

                master_chk.stateChanged.connect(_make_handler(group_start, group_count))

                # ---- "+ Add depot manually" row ----
                add_btn = QPushButton("\uff0b  Add depot manually\u2026")
                add_btn.setStyleSheet(
                    "QPushButton { color: #8888aa; border: none; text-align: left;"
                    " padding: 2px 10px; background: transparent; }"
                    "QPushButton:hover { color: #bbbbdd; }"
                )
                add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                add_btn.clicked.connect(self._make_add_handler(add_btn, group, hex_bg))
                self._table.setCellWidget(table_row, 0, add_btn)
                self._table.setSpan(table_row, 0, 1, 7)
                self._table.setRowHeight(table_row, 22)
                table_row += 1

            self._table.resizeColumnsToContents()
            self._table.setColumnWidth(0, 34)
            layout.addWidget(self._table)

        btns = QDialogButtonBox()
        self._dl_btn = btns.addButton("Download Selected", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_btn = btns.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self._dl_btn.clicked.connect(self._start_download)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(btns)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _make_add_handler(self, btn: QPushButton, group, hex_bg: str):
        """Return a click handler that inserts a manual depot row above the '+' row."""
        def _handler():
            dlg = _ManualEntryDialog(self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            depot_id, manifest_id = dlg.get_values()
            if not depot_id or not manifest_id:
                return

            vp = self._table.viewport()
            gpos = btn.mapToGlobal(btn.rect().center())
            lpos = vp.mapFromGlobal(gpos)
            add_row = self._table.rowAt(lpos.y())
            if add_row < 0:
                return

            self._table.insertRow(add_row)

            chk = QCheckBox()
            chk.setChecked(True)
            cw = QWidget()
            cl = QHBoxLayout(cw)
            cl.addWidget(chk)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.setContentsMargins(2, 0, 2, 0)
            self._table.setCellWidget(add_row, 0, cw)

            self._table.setItem(add_row, 1, QTableWidgetItem(depot_id))
            self._table.setItem(add_row, 2, QTableWidgetItem(manifest_id))
            self._table.setItem(add_row, 3, QTableWidgetItem("\u2014"))
            self._table.setItem(add_row, 4, QTableWidgetItem(group.branch))
            src_item = QTableWidgetItem("Manual")
            src_item.setForeground(QBrush(QColor("#ffaa44")))
            self._table.setItem(add_row, 5, src_item)
            self._table.setItem(add_row, 6, QTableWidgetItem("\u2013"))

            self._checkboxes.append((depot_id, manifest_id, chk))

        return _handler

    def _get_checked(self) -> list[tuple[str, str]]:
        """Return [(depot_id, manifest_id)] for checked rows."""
        if not hasattr(self, "_checkboxes"):
            return []
        return [
            (depot_id, manifest_id)
            for depot_id, manifest_id, chk in self._checkboxes
            if chk.isChecked()
        ]

    def _start_download(self):
        selections = self._get_checked()
        if not selections:
            QMessageBox.warning(self, "Nothing Selected", "Please check at least one manifest to download.")
            return

        if not self.steam_path or not self.steam_path.exists():
            QMessageBox.critical(self, "Error", "Steam path is not configured. Cannot write to depotcache.")
            return

        self._dl_btn.setEnabled(False)
        self._status_label.setText("Downloading manifests…")

        self._dl_thread = QThread()
        self._dl_worker = _ManifestDownloadWorker(
            app_id=str(self.app_id),
            selections=selections,
            steam_path=self.steam_path,
        )
        self._dl_worker.moveToThread(self._dl_thread)
        self._dl_worker.finished.connect(self._on_download_done)
        self._dl_worker.progress.connect(lambda msg: self._status_label.setText(msg))
        self._dl_thread.started.connect(self._dl_worker.run)
        self._dl_thread.start()

    def _on_download_done(self, ok: int, total: int):
        if self._dl_thread:
            self._dl_thread.quit()
            self._dl_thread.wait()
        self._dl_btn.setEnabled(True)
        self._status_label.setText(f"Done — {ok}/{total} manifests downloaded.")
        if ok == total:
            QMessageBox.information(self, "Done",
                f"✅ All {total} selected manifests downloaded to depotcache.\n"
                "Restart Steam to load them.")
        else:
            QMessageBox.warning(self, "Partial",
                f"Downloaded {ok}/{total} manifests. Check the log for errors.")


class _ManifestDownloadWorker(QObject):
    finished = pyqtSignal(int, int)
    progress = pyqtSignal(str)

    def __init__(self, app_id: str, selections: list[tuple[str, str]], steam_path: Path):
        super().__init__()
        self.app_id = app_id
        self.selections = selections
        self.steam_path = steam_path

    def run(self):
        from sff.manifest.downloader import ManifestDownloader
        from sff.steam_client import create_provider_for_current_thread

        ok = 0
        total = len(self.selections)

        try:
            prov = create_provider_for_current_thread()
            dl = ManifestDownloader(prov, self.steam_path)

            for depot_id, manifest_id in self.selections:
                self.progress.emit(f"Downloading depot {depot_id} manifest {manifest_id}…")
                try:
                    raw = dl.download_single_manifest(
                        depot_id=depot_id,
                        manifest_id=manifest_id,
                        app_id=self.app_id,
                    )
                    if raw is not None:
                        written = dl._write_manifest_to_depotcache(raw, depot_id, manifest_id)
                        if written:
                            ok += 1
                            self.progress.emit(f"  ✅ {depot_id}_{manifest_id}.manifest saved")
                        else:
                            self.progress.emit(f"  ⚠️ Depot {depot_id}: write failed")
                    else:
                        self.progress.emit(f"  ❌ Depot {depot_id}: all sources failed")
                except Exception as e:
                    self.progress.emit(f"  ❌ Depot {depot_id}: {e}")
        except Exception as e:
            self.progress.emit(f"Fatal error: {e}")

        self.finished.emit(ok, total)


class StoreTab(QWidget):

    def __init__(self, steam_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._client = None
        self._steam_path = steam_path
        self._current_page = 1
        self._total_pages = 1
        self._worker = None
        self._thread = None
        self._hist_worker = None
        self._hist_thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # API key config
        key_group = QGroupBox("API Configuration")
        key_layout = QHBoxLayout(key_group)
        key_layout.addWidget(QLabel("Hubcap API Key:"))
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
            saved_key = get_setting(Settings.HUBCAP_KEY)
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

        # download action row
        dl_row = QHBoxLayout()
        self._dl_btn = QPushButton("⬇  Download (choose version)…")
        self._dl_btn.setToolTip(
            "Select a game in the table or enter an App ID below, then choose a version "
            "to download (sources: Steam CM, GitHub mirror, local fallback, SteamDB)"
        )
        self._dl_btn.setEnabled(True)
        self._dl_btn.clicked.connect(self._open_version_picker)
        dl_row.addWidget(self._dl_btn)
        self._appid_edit = QLineEdit()
        self._appid_edit.setPlaceholderText("App ID (optional)")
        self._appid_edit.setMaximumWidth(130)
        self._appid_edit.setToolTip("Enter a Steam App ID directly to fetch version history without connecting")
        dl_row.addWidget(self._appid_edit)
        dl_row.addStretch()
        layout.addLayout(dl_row)

        # status
        self._status_label = QLabel("Enter API key and click Connect to start browsing.")
        layout.addWidget(self._status_label)

    def _connect(self):
        key = self._key_edit.text().strip()
        if not key:
            dlg = QMessageBox(self)
            dlg.setWindowTitle("No API Key")
            dlg.setIcon(QMessageBox.Icon.Information)
            dlg.setText(
                "No Hubcap API key set.\n\n"
                "Get your free API key at hubcapmanifest.com, "
                "then paste it in the field above."
            )
            dlg.addButton("Get API Key", QMessageBox.ButtonRole.ActionRole)
            dlg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            result = dlg.exec()
            if result == 0:
                QDesktopServices.openUrl(QUrl("https://hubcapmanifest.com/"))
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
                set_setting(Settings.HUBCAP_KEY, key)
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

        self._games_data: list = games
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

        # Enable download button when rows exist
        self._dl_btn.setEnabled(len(games) > 0)
        self._table.selectionModel().selectionChanged.connect(
            lambda: self._dl_btn.setEnabled(bool(self._table.selectedItems()))
        )

    def _on_error(self, msg):
        self._search_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._status_label.setText(f"Error: {msg}")

    def _open_version_picker(self):
        direct = self._appid_edit.text().strip()
        if direct.isdigit():
            app_id = int(direct)
            game_name = f"App {app_id}"
        else:
            row = self._table.currentRow()
            if row < 0:
                QMessageBox.information(
                    self, "Select a game",
                    "Click a row in the table or enter an App ID in the field next to this button."
                )
                return
            app_id_item = self._table.item(row, 0)
            name_item = self._table.item(row, 1)
            if not app_id_item:
                return
            app_id = int(app_id_item.text())
            game_name = name_item.text() if name_item else f"App {app_id}"

        self._status_label.setText(f"Fetching depot history for {game_name}…")
        self._dl_btn.setEnabled(False)

        self._hist_thread = QThread()
        self._hist_worker = _DepotHistoryWorker(app_id=app_id, client=self._client)
        self._hist_worker.moveToThread(self._hist_thread)
        self._hist_worker.finished.connect(
            lambda hist: self._on_hist_done(app_id, game_name, hist)
        )
        self._hist_worker.error.connect(self._on_hist_error)
        self._hist_worker.progress.connect(self._status_label.setText)
        self._hist_thread.started.connect(self._hist_worker.run)
        self._hist_thread.start()

    def _on_hist_done(self, app_id: int, game_name: str, hist: dict):
        if self._hist_thread:
            self._hist_thread.quit()
            self._hist_thread.wait()
        self._dl_btn.setEnabled(True)
        self._status_label.setText(
            f"Loaded history for {game_name} — {sum(len(v) for v in hist.values())} manifest entries"
            if hist else f"No manifest history found for {game_name}"
        )
        dlg = VersionPickerDialog(
            app_id=app_id,
            game_name=game_name,
            depot_history=hist,
            steam_path=self._steam_path,
            parent=self,
        )
        dlg.exec()

    def _on_hist_error(self, msg: str):
        if self._hist_thread:
            self._hist_thread.quit()
            self._hist_thread.wait()
        self._dl_btn.setEnabled(True)
        self._status_label.setText(f"Error fetching depot history: {msg}")
