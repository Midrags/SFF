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

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QPixmap, QCursor
from pathlib import Path
import sys


class TitleBarWidget(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._drag_pos = None
        self._maximized = False
        self._colors = {
            "bg": "#1a1a1a", "fg": "#e8e8e8", "accent": "#4a9eff",
            "close": "#e81123", "border": "#444444",
        }
        self.setFixedHeight(56)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        logo_path = self._find_logo()
        if logo_path:
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                icon = QLabel()
                icon.setPixmap(pix.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                layout.addWidget(icon)
                layout.addSpacing(8)

        title = QLabel("SteaMidra")
        title.setObjectName("TitleBarLabel")
        layout.addWidget(title)
        layout.addStretch()

        self._min_btn = QPushButton("─")
        self._max_btn = QPushButton("□")
        self._close_btn = QPushButton("✕")

        for btn in (self._min_btn, self._max_btn, self._close_btn):
            btn.setFixedSize(170, 56)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setObjectName("TitleBarButton")

        self._min_btn.clicked.connect(self._window.showMinimized)
        self._max_btn.clicked.connect(self._toggle_maximize)
        self._close_btn.clicked.connect(self._window.close)

        layout.addWidget(self._min_btn)
        layout.addWidget(self._max_btn)
        layout.addWidget(self._close_btn)

    def _find_logo(self):
        candidates = []
        try:
            from sff.utils import root_folder
            candidates.append(root_folder() / "SFF.png")
            candidates.append(root_folder() / "SFF.ico")
        except Exception:
            pass
        candidates.append(Path("SFF.png"))
        candidates.append(Path("SFF.ico"))
        if getattr(sys, 'frozen', False):
            try:
                base = Path(sys._MEIPASS)
                candidates.insert(0, base / "SFF.png")
                candidates.insert(0, base / "SFF.ico")
            except Exception:
                pass
        for p in candidates:
            if p.exists():
                return p
        return None

    def _apply_styles(self):
        c = self._colors
        self.setStyleSheet(
            f"TitleBarWidget {{ background-color: {c['bg']}; border-bottom: 1px solid {c['border']}; }}"
            f"QLabel#TitleBarLabel {{"
            f"  color: {c['fg']}; font-size: 16px; font-weight: 600;"
            f"  background: transparent;"
            f"}}"
            f"QPushButton#TitleBarButton {{"
            f"  background: transparent; border: none; border-radius: 0;"
            f"  color: {c['fg']}; font-size: 24px; padding: 0;"
            f"  min-width: 0;"
            f"}}"
            f"QPushButton#TitleBarButton:hover {{"
            f"  background-color: {c['accent']}; color: #ffffff;"
            f"}}"
            f"QPushButton#TitleBarButton:pressed {{"
            f"  background-color: rgba(255,255,255,30);"
            f"}}"
        )
        self._close_btn.setStyleSheet(
            f"QPushButton#TitleBarButton {{"
            f"  background: transparent; border: none; border-radius: 0;"
            f"  color: {c['fg']}; font-size: 24px; padding: 0;"
            f"  min-width: 0;"
            f"}}"
            f"QPushButton#TitleBarButton:hover {{"
            f"  background-color: {c['close']}; color: #ffffff;"
            f"}}"
            f"QPushButton#TitleBarButton:pressed {{"
            f"  background-color: rgba(200,20,20,150);"
            f"}}"
        )

    def set_colors(self, bg, fg, accent, close_color="#e81123", border="#444444"):
        self._colors = {"bg": bg, "fg": fg, "accent": accent, "close": close_color, "border": border}
        self._apply_styles()

    def _toggle_maximize(self):
        if self._maximized:
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def set_maximized(self, maximized):
        self._maximized = maximized
        self._max_btn.setText("❐" if maximized else "□")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._start_geometry = self._window.geometry()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_system_menu(event.globalPosition().toPoint())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            if self._maximized:
                ratio = event.position().x() / self.width()
                self._window.showNormal()
                new_pos = self._window.pos() + QPoint(int(self.width() * ratio), 0)
                self._window.move(new_pos)
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._window.move(self._window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _show_system_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        restore_a = menu.addAction("&Restore")
        menu.addSeparator()
        move_a = menu.addAction("&Move")
        size_a = menu.addAction("&Size")
        menu.addSeparator()
        min_a = menu.addAction("Mi&nimize")
        max_a = menu.addAction("Ma&ximize")
        menu.addSeparator()
        close_a = menu.addAction("&Close")

        restore_a.triggered.connect(lambda: self._window.showNormal())
        move_a.triggered.connect(lambda: self._window.move(QCursor.pos()))
        size_a.triggered.connect(lambda: self._window.showNormal())
        min_a.triggered.connect(self._window.showMinimized)
        max_a.triggered.connect(self._window.showMaximized)
        close_a.triggered.connect(self._window.close)

        menu.exec(pos)
