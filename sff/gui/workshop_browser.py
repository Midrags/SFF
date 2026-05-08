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

"""Embedded Workshop browser with persistent Steam session."""

from pathlib import Path

from PyQt6.QtCore import QThread, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEnginePage,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from sff.utils import root_folder


_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _get_workshop_profile():
    profile = QWebEngineProfile("SteaMidraWorkshop")
    base_path = root_folder(outside_internal=True) / "webengine_profile"
    storage_path = base_path / "storage"
    cache_path = base_path / "cache"
    storage_path.mkdir(parents=True, exist_ok=True)
    cache_path.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(storage_path))
    profile.setCachePath(str(cache_path))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    profile.setHttpUserAgent(_CHROME_UA)
    return profile


def open_workshop_browser(app_id, parent=None):
    profile = _get_workshop_profile()
    page = QWebEnginePage(profile)
    view = QWebEngineView()
    view.setPage(page)

    workshop_url = f"https://steamcommunity.com/app/{app_id}/workshop/" if app_id else "https://steamcommunity.com/workshop/"

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Steam Workshop – App {app_id}")
    dialog.resize(900, 700)

    layout = QVBoxLayout(dialog)

    url_bar = QLineEdit()
    url_bar.setPlaceholderText("URL")
    url_bar.setReadOnly(False)

    def update_url_bar(qurl):
        url_str = qurl.toString()
        if url_str and url_bar.text() != url_str:
            url_bar.blockSignals(True)
            url_bar.setText(url_str)
            url_bar.blockSignals(False)

    def navigate_from_bar():
        text = url_bar.text().strip()
        if text:
            if not text.startswith(("http://", "https://")):
                text = "https://" + text
            view.setUrl(QUrl(text))

    view.urlChanged.connect(update_url_bar)
    url_bar.returnPressed.connect(navigate_from_bar)
    layout.addWidget(url_bar)

    btn_layout = QHBoxLayout()
    login_btn = QPushButton("Login to Steam")
    login_btn.clicked.connect(
        lambda: view.setUrl(QUrl("https://store.steampowered.com/login/"))
    )
    workshop_btn = QPushButton("Workshop")
    workshop_btn.clicked.connect(lambda: view.setUrl(QUrl(
        f"https://steamcommunity.com/app/{app_id}/workshop/" if app_id else "https://steamcommunity.com/workshop/"
    )))
    copy_btn = QPushButton("Copy Workshop link")
    def copy_current_url():
        clipboard = QApplication.clipboard()
        url = view.url().toString()
        clipboard.setText(url if url else "")

    copy_btn.clicked.connect(copy_current_url)

    dl_btn = QPushButton("Download Item")
    dl_btn.setToolTip(
        "Download the currently viewed workshop item (tries SteamWebAPI, GGNetwork, SteamCMD)"
    )

    status_label = QLabel("")
    status_label.setStyleSheet("font-size:11px;opacity:0.7;")

    _dl_thread = [None]

    class _DlWorker(QThread):
        log_msg = pyqtSignal(str)
        finished = pyqtSignal(bool, str)

        def __init__(self, item_id, game_id, out_dir):
            super().__init__()
            self._item_id = item_id
            self._game_id = game_id
            self._out_dir = out_dir

        def run(self):
            from sff.manifest.workshop_dl import download_workshop_item
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            user = get_setting(Settings.STEAM_USER) or "anonymous"
            pwd = get_setting(Settings.STEAM_PASS) or ""
            result = download_workshop_item(
                self._item_id,
                self._game_id,
                self._out_dir,
                steam_username=user,
                steam_password=pwd,
                log=self.log_msg.emit,
            )
            self.finished.emit(result["success"], result.get("path") or result.get("error") or "")

    def start_download():
        from sff.manifest.workshop_dl import parse_workshop_item_id
        current_url = url_bar.text().strip()
        item_id = parse_workshop_item_id(current_url)
        if not item_id:
            status_label.setText("No item ID found in the current URL")
            return
        out_dir = Path.cwd() / "downloaded_files" / "workshop" / item_id
        status_label.setText(f"Downloading item {item_id}...")
        dl_btn.setEnabled(False)
        worker = _DlWorker(item_id, str(app_id) if app_id else "0", out_dir)
        _dl_thread[0] = worker

        def on_log(msg):
            status_label.setText(msg[:120])

        def on_done(success, path_or_err):
            dl_btn.setEnabled(True)
            if success:
                status_label.setText(f"[OK] Saved to: {path_or_err}")
            else:
                status_label.setText(f"[!] {path_or_err}")

        worker.log_msg.connect(on_log)
        worker.finished.connect(on_done)
        worker.start()

    dl_btn.clicked.connect(start_download)

    btn_layout.addWidget(login_btn)
    btn_layout.addWidget(workshop_btn)
    btn_layout.addWidget(copy_btn)
    btn_layout.addWidget(dl_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)
    layout.addWidget(status_label)
    layout.addWidget(view)

    view.setUrl(QUrl(workshop_url))
    dialog.exec()
