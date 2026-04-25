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

"""Reusable '?' help button for tab headers."""

from PyQt6.QtWidgets import (
    QHBoxLayout, QMessageBox, QPushButton, QWidget,
)


def add_help_button(parent_layout, title: str, text: str, *, parent_widget: QWidget = None):
    """Insert a right-aligned '?' button at the top of *parent_layout*.

    Clicking it opens a QMessageBox with *title* and *text*.
    """
    row = QHBoxLayout()
    row.addStretch()
    btn = QPushButton("?")
    btn.setFixedSize(28, 28)
    btn.setToolTip(f"What is {title}?")
    btn.setStyleSheet(
        "QPushButton { font-weight: bold; font-size: 14px; border-radius: 14px; }"
    )

    def _show():
        dlg = QMessageBox(parent_widget or btn)
        dlg.setWindowTitle(title)
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setText(text)
        dlg.exec()

    btn.clicked.connect(_show)
    row.addWidget(btn)
    parent_layout.addLayout(row)
