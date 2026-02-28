"""Embedded Workshop browser with persistent Steam session."""

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEnginePage,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from sff.utils import root_folder


def _get_workshop_profile() -> QWebEngineProfile:
    """Create or return a persistent WebEngine profile for Steam Workshop."""
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
    return profile


def open_workshop_browser(app_id: str, parent=None) -> None:
    """Open an embedded browser dialog showing the Steam Workshop for the given app."""
    profile = _get_workshop_profile()
    page = QWebEnginePage(profile)
    view = QWebEngineView()
    view.setPage(page)

    workshop_url = "https://steamcommunity.com/workshop/"

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Steam Workshop – App {app_id}")
    dialog.resize(900, 700)

    layout = QVBoxLayout(dialog)

    url_bar = QLineEdit()
    url_bar.setPlaceholderText("URL")
    url_bar.setReadOnly(False)

    def update_url_bar(qurl: QUrl) -> None:
        url_str = qurl.toString()
        if url_str and url_bar.text() != url_str:
            url_bar.blockSignals(True)
            url_bar.setText(url_str)
            url_bar.blockSignals(False)

    def navigate_from_bar() -> None:
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
    workshop_btn.clicked.connect(lambda: view.setUrl(QUrl(workshop_url)))
    copy_btn = QPushButton("Copy Workshop link")
    def copy_current_url() -> None:
        clipboard = QApplication.clipboard()
        url = view.url().toString()
        clipboard.setText(url if url else "")

    copy_btn.clicked.connect(copy_current_url)
    btn_layout.addWidget(login_btn)
    btn_layout.addWidget(workshop_btn)
    btn_layout.addWidget(copy_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)
    layout.addWidget(view)

    view.setUrl(QUrl(workshop_url))
    dialog.exec()
