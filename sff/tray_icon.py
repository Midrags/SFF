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

Provides minimize-to-tray, notification popups, and a quick-access
context menu (show/hide, recent, exit). Hardened against the common
failure modes seen in the wild:

- The shell may not be ready when our process starts (tray returns
  isSystemTrayAvailable=False for ~10-30s after a fresh boot or
  fresh install). We retry every 3s for up to 90s instead of giving
  up after one attempt.
- Explorer.exe can restart (e.g. crash, taskkill, theme change).
  Windows broadcasts TaskbarCreated to every top-level window when
  this happens. Watching the activation/visibility state of the
  underlying QSystemTrayIcon and forcing a re-show on a slow timer
  covers the case without needing a native message hook.
- The QSystemTrayIcon must outlive the visible window. We parent it
  to QApplication.instance() so closing/destroying the main window
  does not garbage-collect the tray.
- Menu actions are populated lazily on aboutToShow so recent-games
  reflect current state without us having to push updates.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt

logger = logging.getLogger(__name__)

# Retry cadence: every 3 s for up to 90 s. Covers the worst-case
# Windows shell startup delay we have observed (cold boot on a low-spec
# machine, which can take ~30 s before the system tray becomes available).
_RETRY_INTERVAL_MS = 3000
_RETRY_TIMEOUT_MS = 90_000

# How often to nudge the tray icon back to visible. Catches Explorer
# restarts and the occasional cases where the icon "falls off" the tray.
_HEARTBEAT_INTERVAL_MS = 30_000


class TrayIcon(QObject):
    """System tray icon with context menu.

    Signals:
        show_requested: user clicked "Show" or activated the icon
        exit_requested: user clicked "Exit"
    """

    show_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None, icon_path=""):
        # Parent to QApplication if no explicit parent so the tray
        # outlives any single window. We still accept a parent= kwarg
        # for backwards compatibility with the existing call site.
        super().__init__(parent or QApplication.instance())
        self._tray: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._recent_menu: Optional[QMenu] = None
        self._icon_path = icon_path
        self._minimize_to_tray = True
        self._pending_icon: Optional[QIcon] = None
        self._retry_total_ms = 0
        self._heartbeat: Optional[QTimer] = None
        self._recent_games: list[tuple[str, int]] = []

    # ── Setup ──────────────────────────────────────────────────────

    def setup(self, app_icon=None):
        """Create the tray icon. Call once after QApplication exists.

        If the system tray is not yet available, schedules retries.
        Idempotent: if called again after the icon is already up, no-ops.
        """
        if self._tray is not None:
            return
        self._pending_icon = app_icon
        self._retry_total_ms = 0
        self._setup_attempt()

    def _setup_attempt(self):
        if self._tray is not None:
            return  # already created on a previous tick

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._retry_total_ms += _RETRY_INTERVAL_MS
            if self._retry_total_ms >= _RETRY_TIMEOUT_MS:
                logger.warning(
                    "System tray not available after %ds — giving up",
                    _RETRY_TIMEOUT_MS // 1000,
                )
                return
            logger.info(
                "System tray not available yet (waited %ds), retrying...",
                self._retry_total_ms // 1000,
            )
            QTimer.singleShot(_RETRY_INTERVAL_MS, self._setup_attempt)
            return

        try:
            self._create_tray()
        except Exception as e:
            # Non-fatal: app keeps working without a tray icon.
            logger.error("Tray creation failed: %s", e)
            self._tray = None

    def _create_tray(self):
        # Parent the QSystemTrayIcon to QApplication so it survives the
        # main window being closed or the parent QObject being destroyed.
        self._tray = QSystemTrayIcon(QApplication.instance())

        icon = self._pending_icon
        if icon is not None and not icon.isNull():
            self._tray.setIcon(icon)
        elif self._icon_path:
            self._tray.setIcon(QIcon(self._icon_path))

        self._tray.setToolTip("SteaMidra")
        self._build_menu()
        self._tray.activated.connect(self._on_activated)
        self._tray.show()
        logger.info("System tray icon created")

        # Heartbeat: re-show the icon periodically. Cheap insurance
        # against Explorer restarts and DPI changes that can drop the
        # icon without telling Qt.
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(_HEARTBEAT_INTERVAL_MS)
        self._heartbeat.timeout.connect(self._heartbeat_tick)
        self._heartbeat.start()

    def _heartbeat_tick(self):
        if self._tray is None:
            return
        try:
            if not self._tray.isVisible():
                logger.info("Tray icon not visible — re-showing")
                self._tray.show()
        except RuntimeError:
            # Underlying C++ object went away (rare, e.g. during shutdown)
            self._tray = None

    # ── Menu ───────────────────────────────────────────────────────

    def _build_menu(self):
        self._menu = QMenu()

        show_action = QAction("Show SteaMidra", self._menu)
        show_action.triggered.connect(self.show_requested.emit)
        self._menu.addAction(show_action)

        self._menu.addSeparator()

        self._recent_menu = self._menu.addMenu("Recent Games")
        self._recent_menu.aboutToShow.connect(self._refresh_recent_menu)
        self._recent_menu.addAction("(none)")

        self._menu.addSeparator()

        exit_action = QAction("Exit", self._menu)
        # DirectConnection so Exit fires immediately on the GUI thread
        # without queueing — same pattern antimicrox uses to avoid the
        # menu staying open while the window is already tearing down.
        exit_action.triggered.connect(
            self.exit_requested.emit, Qt.ConnectionType.DirectConnection
        )
        self._menu.addAction(exit_action)

        self._tray.setContextMenu(self._menu)

    def _refresh_recent_menu(self):
        """Lazily rebuild the recent-games submenu when it's about to show."""
        if self._recent_menu is None:
            return
        self._recent_menu.clear()
        if not self._recent_games:
            self._recent_menu.addAction("(none)")
            return
        for name, app_id in self._recent_games[:5]:
            action = QAction(f"{name} ({app_id})", self._recent_menu)
            self._recent_menu.addAction(action)

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_requested.emit()

    # ── Public API ─────────────────────────────────────────────────

    def notify(self, title, message, duration_ms=3000):
        if self._tray is not None:
            try:
                self._tray.showMessage(
                    title, message, QSystemTrayIcon.MessageIcon.Information, duration_ms
                )
            except RuntimeError:
                self._tray = None

    def update_recent_games(self, games: list[tuple[str, int]]):
        """Store recent games. The submenu rebuilds itself on next open."""
        self._recent_games = list(games or [])

    @property
    def minimize_to_tray(self):
        return self._minimize_to_tray

    @minimize_to_tray.setter
    def minimize_to_tray(self, value):
        self._minimize_to_tray = value

    def hide(self):
        if self._tray is not None:
            try:
                self._tray.hide()
            except RuntimeError:
                self._tray = None

    def show(self):
        if self._tray is not None:
            try:
                self._tray.show()
            except RuntimeError:
                self._tray = None
