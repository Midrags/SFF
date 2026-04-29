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

"""Global floating log window — captures all Python logging output."""

import logging
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QComboBox, QLabel, QApplication,
)


_LEVEL_COLORS = {
    logging.DEBUG:    "#888888",
    logging.INFO:     "#e0e0e0",
    logging.WARNING:  "#f0c040",
    logging.ERROR:    "#f06060",
    logging.CRITICAL: "#ff4040",
}


class _LogSignalEmitter(QObject):
    """Thread-safe bridge: emits log records as HTML strings on the GUI thread."""
    record_emitted = pyqtSignal(int, str)  # (levelno, html_line)


class QtLogHandler(logging.Handler):
    """
    Logging handler that forwards records to GlobalLogWindow via Qt signals.
    Safe to install from any thread — Qt queues the signal delivery to the GUI thread.
    """

    def __init__(self):
        super().__init__()
        self._emitter = _LogSignalEmitter()
        self.record_emitted = self._emitter.record_emitted

    def emit(self, record):
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            level = record.levelname[:4]
            msg = self.format(record)
            color = _LEVEL_COLORS.get(record.levelno, "#e0e0e0")
            safe_msg = (
                msg
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            html = (
                f'<span style="color:#666666;">{ts}</span> '
                f'<span style="color:{color};font-weight:bold;">[{level}]</span> '
                f'<span style="color:{color};">{safe_msg}</span>'
            )
            self._emitter.record_emitted.emit(record.levelno, html)
        except Exception:
            pass


class GlobalLogWindow(QDialog):
    """
    Non-modal floating window showing all Python logging output (DEBUG and above).
    Closing the window hides it rather than destroying it.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("SteaMidra — Log Viewer")
        self.setMinimumSize(700, 450)
        self.resize(820, 500)
        self._min_level = logging.DEBUG
        self._pending: list[tuple[int, str]] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar row
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Level filter:"))
        self._level_combo = QComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._level_combo.currentIndexChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._level_combo)
        toolbar.addStretch()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(70)
        self._clear_btn.clicked.connect(self._text.clear if hasattr(self, '_text') else lambda: None)
        toolbar.addWidget(self._clear_btn)
        self._copy_btn = QPushButton("Copy All")
        self._copy_btn.setFixedWidth(80)
        self._copy_btn.clicked.connect(self._copy_all)
        toolbar.addWidget(self._copy_btn)
        layout.addLayout(toolbar)

        # Log text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text)

        # Fix clear button now that _text exists
        self._clear_btn.clicked.disconnect()
        self._clear_btn.clicked.connect(self._text.clear)

    def _on_level_changed(self, index):
        levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
        self._min_level = levels[index]

    def append_record(self, levelno: int, html: str):
        """Called from QtLogHandler signal — always on GUI thread."""
        if levelno < self._min_level:
            return
        self._text.moveCursor(QTextCursor.MoveOperation.End)
        self._text.insertHtml(html + "<br>")
        self._text.moveCursor(QTextCursor.MoveOperation.End)

    def _copy_all(self):
        QApplication.clipboard().setText(self._text.toPlainText())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
