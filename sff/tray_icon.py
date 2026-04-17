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

"""
System tray icon for SteaMidra.

Provides minimize-to-tray, notification popups, and quick-access
context menu (show/hide, recent, downloads, settings, exit).
"""

import logging

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QObject

logger = logging.getLogger(__name__)


class TrayIcon(QObject):
    """
    System tray icon with context menu.
    
    Signals:
        show_requested: user clicked "Show"
        exit_requested: user clicked "Exit"
    """

    show_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None, icon_path = ""):
        super().__init__(parent)
        self._tray: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._icon_path = icon_path
        self._minimize_to_tray = True

    def setup(self, app_icon = None):
        """initialize the tray icon — call this after QApplication is created"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray not available")
            return

        self._tray = QSystemTrayIcon(self.parent())

        if app_icon:
            self._tray.setIcon(app_icon)
        elif self._icon_path:
            self._tray.setIcon(QIcon(self._icon_path))

        self._tray.setToolTip("SteaMidra")
        self._build_menu()

        self._tray.activated.connect(self._on_activated)
        self._tray.show()
        logger.info("System tray icon created")

    def _build_menu(self):
        """build the right-click context menu"""
        self._menu = QMenu()

        show_action = QAction("Show SteaMidra", self._menu)
        show_action.triggered.connect(self.show_requested.emit)
        self._menu.addAction(show_action)

        self._menu.addSeparator()

        # placeholder for recent games - populated dynamically
        self._recent_menu = self._menu.addMenu("Recent Games")
        self._recent_menu.addAction("(none)")

        self._menu.addSeparator()

        exit_action = QAction("Exit", self._menu)
        exit_action.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(exit_action)

        self._tray.setContextMenu(self._menu)

    def _on_activated(self, reason):
        """handle tray icon clicks"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # single click — show/hide
            self.show_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_requested.emit()

    def notify(self, title, message, duration_ms = 3000):
        """show a tray notification balloon"""
        if self._tray:
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, duration_ms)

    def update_recent_games(self, games: list[tuple[str, int]]):
        """update the recent games submenu with (name, app_id) pairs"""
        if not self._recent_menu:
            return
        self._recent_menu.clear()
        if not games:
            self._recent_menu.addAction("(none)")
            return
        for name, app_id in games[:5]:
            action = QAction(f"{name} ({app_id})", self._recent_menu)
            self._recent_menu.addAction(action)

    @property
    def minimize_to_tray(self):
        return self._minimize_to_tray

    @minimize_to_tray.setter
    def minimize_to_tray(self, value):
        self._minimize_to_tray = value

    def hide(self):
        """hide the tray icon"""
        if self._tray:
            self._tray.hide()

    def show(self):
        """show the tray icon"""
        if self._tray:
            self._tray.show()
