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

import threading
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class _Invoker(QObject):
    _signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._signal.connect(self._run)

    def _run(self, task):
        func, container = task
        try:
            container["value"] = func()
        except Exception as e:
            container["error"] = e
        container["done"].set()


_invoker = None


def _on_gui_thread(func):
    app = QApplication.instance()
    if not app or QThread.currentThread() == app.thread():
        return func()
    if _invoker is None:
        raise RuntimeError("gui prompt backend not installed")
    container = {"value": None, "error": None, "done": threading.Event()}
    _invoker._signal.emit((func, container))
    container["done"].wait()
    if container["error"] is not None:
        raise container["error"]
    return container["value"]


class GUIPromptBackend:
    def __init__(self, parent=None):
        self._parent = parent

    def set_parent(self, parent):
        self._parent = parent

    def prompt_select(
        self,
        msg: str,
        choices,
        default=None,
        fuzzy=False,
        cancellable=False,
        exclude=None,
        **kwargs,
    ):
        items = []
        for c in choices:
            if isinstance(c, Enum):
                if exclude and c in exclude:
                    continue
                items.append((str(c.value), c))
            elif isinstance(c, tuple) and len(c) >= 2:
                items.append((str(c[0]), c[1]))
            else:
                items.append((str(c), c))
        multiselect = kwargs.get("multiselect", False)
        parent = self._parent
        def _show():
            dlg = QDialog(parent)
            dlg.setWindowTitle("Select")
            dlg.setMinimumWidth(420)
            dlg.setMinimumHeight(300)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel(msg))
            lw = QListWidget()
            default_row = 0
            for idx, (display, value) in enumerate(items):
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, value)
                if multiselect:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                lw.addItem(item)
                if value == default:
                    default_row = idx
            if lw.count() > 0:
                lw.setCurrentRow(default_row)
            layout.addWidget(lw)
            std = QDialogButtonBox.StandardButton.Ok
            if cancellable:
                std |= QDialogButtonBox.StandardButton.Cancel
            btns = QDialogButtonBox(std)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            layout.addWidget(btns)
            if not multiselect:
                lw.itemDoubleClicked.connect(dlg.accept)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            if multiselect:
                sel = []
                for i in range(lw.count()):
                    it = lw.item(i)
                    if it and it.checkState() == Qt.CheckState.Checked:
                        sel.append(it.data(Qt.ItemDataRole.UserRole))
                return sel if sel else None
            cur = lw.currentItem()
            return cur.data(Qt.ItemDataRole.UserRole) if cur else None
        return _on_gui_thread(_show)

    def prompt_confirm(
        self,
        msg,
        true_msg=None,
        false_msg=None,
        default=True,
    ):
        parent = self._parent
        def _show():
            btn = QMessageBox.question(
                parent,
                "Confirm",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes if default else QMessageBox.StandardButton.No,
            )
            return btn == QMessageBox.StandardButton.Yes
        return _on_gui_thread(_show)

    def prompt_text(
        self,
        msg: str,
        validator=None,
        invalid_msg="Invalid input",
        instruction="",
        long_instruction="",
        filter=None,
    ):
        parent = self._parent
        def _show():
            while True:
                text, ok = QInputDialog.getText(parent, "Input", msg)
                if not ok:
                    return filter("") if filter else ""
                if validator:
                    try:
                        valid = validator(text)
                    except Exception:
                        valid = False
                    if not valid:
                        QMessageBox.warning(parent, "Invalid", invalid_msg)
                        continue
                return filter(text) if filter else text
        return _on_gui_thread(_show)

    def prompt_dir(
        self,
        msg: str,
        custom_check=None,
        custom_msg=None,
    ):
        parent = self._parent
        def _show():
            while True:
                path = QFileDialog.getExistingDirectory(parent, msg)
                if not path:
                    return Path(".")
                p = Path(path)
                if custom_check and not custom_check(p):
                    QMessageBox.warning(parent, "Invalid", custom_msg or "Invalid directory.")
                    continue
                return p
        return _on_gui_thread(_show)

    def prompt_file(self, msg, allow_blank=False):
        parent = self._parent
        def _show():
            path, _ = QFileDialog.getOpenFileName(parent, msg)
            if not path:
                return Path("") if allow_blank else Path(".")
            return Path(path)
        return _on_gui_thread(_show)

    def prompt_secret(
        self,
        msg: str,
        validator=None,
        invalid_msg="Invalid input",
        instruction="",
        long_instruction="",
    ):
        parent = self._parent
        def _show():
            while True:
                text, ok = QInputDialog.getText(
                    parent, "Secret", msg, QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return ""
                if validator:
                    try:
                        valid = validator(text)
                    except Exception:
                        valid = False
                    if not valid:
                        QMessageBox.warning(parent, "Invalid", invalid_msg)
                        continue
                return text
        return _on_gui_thread(_show)


def install(parent_widget=None):
    global _invoker
    _invoker = _Invoker()
    backend = GUIPromptBackend(parent_widget)
    from sff.prompts import set_gui_backend
    set_gui_backend(backend)


def update_parent(parent_widget):
    from sff.prompts import _gui_backend
    if _gui_backend is not None:
        _gui_backend.set_parent(parent_widget)


def uninstall():
    from sff.prompts import set_gui_backend
    set_gui_backend(None)
