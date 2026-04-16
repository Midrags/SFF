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

"""Fix Game tab — automated pipeline for making games playable."""

import logging
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QComboBox, QCheckBox, QFileDialog,
    QMessageBox, QTextEdit, QRadioButton, QButtonGroup,
)

from sff.fix_game.service import FixGameService, EmuMode

logger = logging.getLogger(__name__)

_DEFAULT_STEAM_ID = "76561198001737783"


def _scan_installed_games(steam_path: Optional[Path] = None) -> list[tuple[str, str, Path]]:
    """Scan all Steam libraries and return list of (name, app_id, game_path)."""
    results: list[tuple[str, str, Path]] = []
    seen: set[str] = set()

    candidates: list[Path] = []
    if steam_path and steam_path.exists():
        candidates.append(steam_path)

    # Auto-detect from registry if not given
    if not candidates:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\WOW6432Node\Valve\Steam")
            val, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            candidates.append(Path(val))
        except Exception:
            pass

    # Extend with all drives
    if os.name == "nt":
        from string import ascii_uppercase
        for dl in ascii_uppercase:
            for sub in ("SteamLibrary", "Steam", "Games/Steam"):
                p = Path(f"{dl}:/{sub}")
                if p.exists() and p not in candidates:
                    candidates.append(p)

    # Read libraryfolders.vdf from each root
    try:
        from sff.storage.vdf import get_steam_libs
        if candidates:
            for root in list(candidates):
                for lib in get_steam_libs(root):
                    if lib not in candidates:
                        candidates.append(lib)
    except Exception:
        pass

    for lib in candidates:
        steamapps = lib / "steamapps"
        if not steamapps.exists():
            continue
        for acf in steamapps.glob("appmanifest_*.acf"):
            try:
                from sff.storage.vdf import vdf_load
                data = vdf_load(acf).get("AppState", {})
                app_id = data.get("appid", "")
                name = data.get("name", "")
                installdir = data.get("installdir", "")
                if not app_id or not installdir or app_id in seen:
                    continue
                game_path = steamapps / "common" / installdir
                if game_path.exists():
                    seen.add(app_id)
                    results.append((name or f"App {app_id}", app_id, game_path))
            except Exception:
                pass

    results.sort(key=lambda t: t[0].lower())
    return results


class _FixWorker(QObject):
    finished = pyqtSignal(bool, str)
    log_msg = pyqtSignal(str)

    def __init__(self, game_path: Path, app_id: str, emu_mode: EmuMode,
                 unpack_steamstub: bool, generate_config: bool, create_launch_bat: bool,
                 goldberg_update: bool, player_name: str, steam_id: str,
                 avatar_path: str, simple_settings: bool,
                 gse_auth_mode: str = "anonymous",
                 gse_username: str = "",
                 gse_password: str = ""):
        super().__init__()
        self.game_path = game_path
        self.app_id = app_id
        self.emu_mode = emu_mode
        self.unpack_steamstub = unpack_steamstub
        self.generate_config = generate_config
        self.create_launch_bat = create_launch_bat
        self.goldberg_update = goldberg_update
        self.player_name = player_name
        self.steam_id = steam_id
        self.avatar_path = avatar_path or None
        self.simple_settings = simple_settings
        self.gse_auth_mode = gse_auth_mode
        self.gse_username = gse_username
        self.gse_password = gse_password

    def run(self):
        try:
            self.log_msg.emit(f"Starting Fix Game pipeline for {self.game_path.name} ({self.app_id})")

            svc = FixGameService()
            success = svc.fix_game(
                app_id=int(self.app_id),
                game_dir=str(self.game_path),
                emu_mode=self.emu_mode.value,
                skip_steamstub=not self.unpack_steamstub,
                skip_goldberg_update=not self.goldberg_update,
                log_func=self.log_msg.emit,
                player_name=self.player_name or "Player",
                steam_id=self.steam_id or _DEFAULT_STEAM_ID,
                avatar_path=self.avatar_path,
                simple_settings=self.simple_settings,
                gse_auth_mode=self.gse_auth_mode,
                gse_username=self.gse_username,
                gse_password=self.gse_password,
            )

            if success:
                self.log_msg.emit("Fix Game pipeline completed successfully!")
                self.finished.emit(True, "Success")
            else:
                self.log_msg.emit("Fix Game pipeline failed.")
                self.finished.emit(False, "Failed to apply fix.")
        except Exception as e:
            self.log_msg.emit(f"Error: {e}")
            self.finished.emit(False, str(e))


class _RevertWorker(QObject):
    finished = pyqtSignal(bool, str)
    log_msg = pyqtSignal(str)

    def __init__(self, game_path: Path):
        super().__init__()
        self.game_path = game_path

    def run(self):
        try:
            self.log_msg.emit(f"Reverting changes for {self.game_path.name}...")
            svc = FixGameService()
            success, msg = svc.restore_game(str(self.game_path), log_func=self.log_msg.emit)
            self.finished.emit(success, msg)
        except Exception as e:
            self.log_msg.emit(f"Error: {e}")
            self.finished.emit(False, str(e))


class FixGameTab(QWidget):
    """Orchestrates the Fix Game pipeline."""

    def __init__(self, steam_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._steam_path = steam_path
        self._thread = None
        self._worker = None
        self._game_entries: list[tuple[str, str, Path]] = []
        self._setup_ui()
        self._load_gse_identity()

    def _load_gse_identity(self):
        """Pre-fill username and Steam64 ID from the global GSE Saves settings folder."""
        import configparser
        try:
            appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            user_ini = Path(appdata) / "GSE Saves" / "settings" / "configs.user.ini"
            if not user_ini.exists():
                return
            cfg = configparser.ConfigParser()
            cfg.read(str(user_ini), encoding="utf-8")
            name = cfg.get("user::general", "account_name", fallback="").strip()
            sid = cfg.get("user::general", "account_steamid", fallback="").strip()
            if name and not self._name_edit.text():
                self._name_edit.setText(name)
            if sid and not self._steamid_edit.text():
                self._steamid_edit.setText(sid)
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Target Game ---
        target_group = QGroupBox("Target Game")
        target_layout = QVBoxLayout(target_group)

        # Installed Steam games dropdown
        dropdown_row = QHBoxLayout()
        dropdown_row.addWidget(QLabel("Steam Game:"))
        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(260)
        self._game_combo.addItem("— select installed game —", None)
        self._game_combo.currentIndexChanged.connect(self._on_game_selected)
        dropdown_row.addWidget(self._game_combo)
        self._refresh_games_btn = QPushButton("↻")
        self._refresh_games_btn.setFixedWidth(30)
        self._refresh_games_btn.setToolTip("Refresh installed game list")
        self._refresh_games_btn.clicked.connect(self._refresh_game_list)
        dropdown_row.addWidget(self._refresh_games_btn)
        dropdown_row.addStretch()
        target_layout.addLayout(dropdown_row)

        # Manual path row (optional override / cs.rin games)
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Game Folder:"))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Or browse manually (for games from cs.rin/RAR)...")
        path_layout.addWidget(self._path_edit)
        self._browse_btn = QPushButton("Browse")
        self._browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self._browse_btn)
        target_layout.addLayout(path_layout)

        id_layout = QHBoxLayout()
        id_layout.addWidget(QLabel("App ID:"))
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("Leave blank to auto-detect")
        id_layout.addWidget(self._id_edit)
        target_layout.addLayout(id_layout)
        layout.addWidget(target_group)

        # Populate game list now (fast, no network)
        self._refresh_game_list()

        # --- User Identity ---
        identity_group = QGroupBox("User Identity (applies to all emulator modes)")
        identity_layout = QVBoxLayout(identity_group)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Username:      "))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Player")
        name_layout.addWidget(self._name_edit)
        identity_layout.addLayout(name_layout)

        steamid_layout = QHBoxLayout()
        steamid_layout.addWidget(QLabel("Steam64 ID:   "))
        self._steamid_edit = QLineEdit()
        self._steamid_edit.setPlaceholderText(f"Leave blank for default  ({_DEFAULT_STEAM_ID})")
        steamid_layout.addWidget(self._steamid_edit)
        identity_layout.addLayout(steamid_layout)
        id_hint = QLabel("(i)  Leave Steam64 ID blank unless you know what you're changing.")
        id_hint.setStyleSheet("color: #888; font-size: 10px; padding: 0px 0px 2px 0px;")
        identity_layout.addWidget(id_hint)

        avatar_layout = QHBoxLayout()
        avatar_layout.addWidget(QLabel("Avatar Image:  "))
        self._avatar_edit = QLineEdit()
        self._avatar_edit.setPlaceholderText("Optional — .png / .jpg / .jpeg")
        avatar_layout.addWidget(self._avatar_edit)
        self._avatar_btn = QPushButton("Browse")
        self._avatar_btn.clicked.connect(self._browse_avatar)
        avatar_layout.addWidget(self._avatar_btn)
        identity_layout.addLayout(avatar_layout)

        layout.addWidget(identity_group)

        # --- Fix Options ---
        opt_group = QGroupBox("Fix Options")
        opt_layout = QVBoxLayout(opt_group)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Emulator Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Regular Goldberg (steam_api64.dll)", EmuMode.REGULAR)
        self._mode_combo.addItem("ColdClient (Simple — no password)", EmuMode.COLDCLIENT_SIMPLE)
        self._mode_combo.addItem("ColdClient (Advanced — GSE Fork tool)", EmuMode.COLDCLIENT_ADVANCED)
        self._mode_combo.addItem("ColdLoader DLL (proxy dll)", EmuMode.COLDLOADER_DLL)
        mode_layout.addWidget(self._mode_combo)
        mode_layout.addStretch()
        opt_layout.addLayout(mode_layout)

        mode_tip = QLabel(
            "💡 Tip: Many games don't work with Regular mode — if the game doesn't launch "
            "or Steam features are broken, switch to <b>ColdClient (Simple)</b>."
        )
        mode_tip.setWordWrap(True)
        mode_tip.setStyleSheet("color: #a0a0a0; font-size: 11px; padding: 2px 0px 4px 0px;")
        opt_layout.addWidget(mode_tip)

        # GSE Fork options panel — only visible when ColdClient Advanced is selected
        self._gse_group = QGroupBox("GSE Fork Options")
        gse_layout = QVBoxLayout(self._gse_group)

        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("Auth:"))
        self._gse_anon_radio = QRadioButton("Anonymous (no credentials)")
        self._gse_login_radio = QRadioButton("Login with Steam credentials")
        self._gse_anon_radio.setChecked(True)
        self._gse_auth_group = QButtonGroup(self)
        self._gse_auth_group.addButton(self._gse_anon_radio)
        self._gse_auth_group.addButton(self._gse_login_radio)
        auth_row.addWidget(self._gse_anon_radio)
        auth_row.addWidget(self._gse_login_radio)
        auth_row.addStretch()
        gse_layout.addLayout(auth_row)

        self._gse_creds_widget = QWidget()
        creds_layout = QVBoxLayout(self._gse_creds_widget)
        creds_layout.setContentsMargins(0, 0, 0, 0)
        user_row = QHBoxLayout()
        user_row.addWidget(QLabel("Steam Account:"))
        self._gse_user_edit = QLineEdit()
        self._gse_user_edit.setPlaceholderText("Steam account username")
        user_row.addWidget(self._gse_user_edit)
        creds_layout.addLayout(user_row)
        pass_row = QHBoxLayout()
        pass_row.addWidget(QLabel("Password:           "))
        self._gse_pass_edit = QLineEdit()
        self._gse_pass_edit.setPlaceholderText("Steam account password")
        self._gse_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_row.addWidget(self._gse_pass_edit)
        creds_layout.addLayout(pass_row)
        gse_layout.addWidget(self._gse_creds_widget)
        self._gse_creds_widget.hide()
        opt_layout.addWidget(self._gse_group)
        self._gse_group.hide()

        # pre-fill saved credentials
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            sv = get_setting(Settings.STEAM_USER)
            if sv:
                self._gse_user_edit.setText(str(sv))
            sp = get_setting(Settings.STEAM_PASS)
            if sp:
                self._gse_pass_edit.setText(str(sp))
        except Exception:
            pass

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._gse_login_radio.toggled.connect(self._on_gse_auth_changed)

        self._chk_goldberg_update = QCheckBox("Check for Goldberg updates (downloads latest from GitHub)")
        self._chk_goldberg_update.setChecked(False)
        opt_layout.addWidget(self._chk_goldberg_update)

        self._chk_steamstub = QCheckBox("Auto-unpack SteamStub DRM (Steamless)")
        self._chk_steamstub.setChecked(True)
        opt_layout.addWidget(self._chk_steamstub)

        # steam_settings generation mode
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("steam_settings:"))
        self._radio_simple = QRadioButton("Simple (fast — DLC fetched, no achievements/depot data)")
        self._radio_advanced = QRadioButton("Advanced (fetches DLCs, languages, depots)")
        self._radio_advanced.setChecked(True)
        self._settings_mode_group = QButtonGroup(self)
        self._settings_mode_group.addButton(self._radio_simple)
        self._settings_mode_group.addButton(self._radio_advanced)
        config_layout.addWidget(self._radio_simple)
        config_layout.addWidget(self._radio_advanced)
        config_layout.addStretch()
        opt_layout.addLayout(config_layout)

        self._chk_launchbat = QCheckBox("Create Launch.bat (For ColdClient)")
        self._chk_launchbat.setChecked(False)
        opt_layout.addWidget(self._chk_launchbat)

        layout.addWidget(opt_group)

        # --- Action buttons ---
        btn_layout = QHBoxLayout()
        self._run_btn = QPushButton("Run Fix Game Pipeline")
        self._run_btn.setFixedHeight(40)
        self._run_btn.clicked.connect(self._run_fix)
        btn_layout.addWidget(self._run_btn)

        self._revert_btn = QPushButton("Revert Changes")
        self._revert_btn.setFixedHeight(40)
        self._revert_btn.clicked.connect(self._run_revert)
        btn_layout.addWidget(self._revert_btn)
        layout.addLayout(btn_layout)

        # --- Log output ---
        log_group = QGroupBox("Status Output")
        log_layout = QVBoxLayout(log_group)
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        log_layout.addWidget(self._log_area)
        layout.addWidget(log_group)

    def _refresh_game_list(self) -> None:
        """Scan installed Steam games and populate the dropdown."""
        self._game_combo.blockSignals(True)
        self._game_combo.clear()
        self._game_combo.addItem("— select installed game —", None)
        try:
            self._game_entries = _scan_installed_games(self._steam_path)
            for name, app_id, path in self._game_entries:
                self._game_combo.addItem(f"{name}  ({app_id})", (app_id, path))
        except Exception as e:
            logger.debug(f"Game scan failed: {e}")
        self._game_combo.blockSignals(False)

    def _on_game_selected(self, index: int) -> None:
        """Auto-fill path and App ID when user picks a game from dropdown."""
        data = self._game_combo.itemData(index)
        if data is None:
            return
        app_id, game_path = data
        self._path_edit.setText(str(game_path))
        self._id_edit.setText(app_id)

    @staticmethod
    def _detect_app_id(game_path: Path) -> str:
        """Try to detect App ID from the game folder using multiple sources."""
        import re
        candidates = [
            game_path / "steam_appid.txt",
            game_path / "steam_settings" / "steam_appid.txt",
        ]
        for f in candidates:
            try:
                val = f.read_text(encoding="utf-8", errors="ignore").strip()
                if val.isdigit():
                    return val
            except Exception:
                pass

        # ColdClientLoader.ini AppId= line
        ini = game_path / "ColdClientLoader.ini"
        try:
            for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r'(?i)^AppId\s*=\s*(\d+)', line)
                if m:
                    return m.group(1)
        except Exception:
            pass

        # appmanifest_*.acf in the parent steamapps/ directory
        try:
            steamapps = game_path.parent.parent
            game_name = game_path.name.lower()
            for acf in steamapps.glob("appmanifest_*.acf"):
                try:
                    text = acf.read_text(encoding="utf-8", errors="ignore")
                    dir_m = re.search(r'"installdir"\s*"([^"]+)"', text)
                    if dir_m and dir_m.group(1).lower() == game_name:
                        id_m = re.search(r'"appid"\s*"(\d+)"', text)
                        if id_m:
                            return id_m.group(1)
                except Exception:
                    pass
        except Exception:
            pass

        return ""

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Game Folder")
        if path:
            self._path_edit.setText(path)
            if not self._id_edit.text():
                detected = self._detect_app_id(Path(path))
                if detected:
                    self._id_edit.setText(detected)

    def _browse_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Avatar Image", "",
            "Image Files (*.png *.jpg *.jpeg)"
        )
        if path:
            self._avatar_edit.setText(path)

    def _on_mode_changed(self, _index: int) -> None:
        """Show/hide GSE Fork options when ColdClient Advanced is selected."""
        mode = self._mode_combo.currentData()
        self._gse_group.setVisible(mode == EmuMode.COLDCLIENT_ADVANCED)

    def _on_gse_auth_changed(self) -> None:
        """Show/hide credential fields based on auth radio selection."""
        self._gse_creds_widget.setVisible(self._gse_login_radio.isChecked())

    def prefill(self, game_path: str, app_id: str, emu_mode: EmuMode = EmuMode.COLDCLIENT_SIMPLE):
        """Pre-fill fields from external callers (e.g. Quick ColdClient button)."""
        self._path_edit.setText(game_path)
        if app_id:
            self._id_edit.setText(app_id)
        # Try to match the dropdown to the given app_id
        matched = False
        if app_id:
            for i in range(1, self._game_combo.count()):
                data = self._game_combo.itemData(i)
                if data and str(data[0]) == str(app_id):
                    self._game_combo.blockSignals(True)
                    self._game_combo.setCurrentIndex(i)
                    self._game_combo.blockSignals(False)
                    matched = True
                    break
        if not matched:
            self._game_combo.blockSignals(True)
            self._game_combo.setCurrentIndex(0)
            self._game_combo.blockSignals(False)
        idx = self._mode_combo.findData(emu_mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

    def _run_fix(self):
        game_path_str = self._path_edit.text().strip()
        if not game_path_str:
            QMessageBox.warning(self, "Missing Input", "Please select a game folder.")
            return

        game_path = Path(game_path_str)
        if not game_path.exists() or not game_path.is_dir():
            QMessageBox.warning(self, "Invalid Path", "The selected game folder does not exist.")
            return

        app_id = self._id_edit.text().strip()
        if not app_id:
            app_id = self._detect_app_id(game_path)
            if app_id:
                self._id_edit.setText(app_id)
                self._log_area.append(f"Auto-detected App ID: {app_id}")
            else:
                QMessageBox.warning(self, "Missing Input",
                    "Could not auto-detect App ID.\nPlease enter it manually.")
                return

        self._run_btn.setEnabled(False)
        self._revert_btn.setEnabled(False)
        self._log_area.clear()
        self._log_area.append("Starting Fix Game pipeline...")

        gse_auth = "login" if self._gse_login_radio.isChecked() else "anonymous"
        gse_user = self._gse_user_edit.text().strip()
        gse_pass = self._gse_pass_edit.text()

        self._thread = QThread()
        self._worker = _FixWorker(
            game_path,
            app_id,
            self._mode_combo.currentData(),
            self._chk_steamstub.isChecked(),
            True,
            self._chk_launchbat.isChecked(),
            self._chk_goldberg_update.isChecked(),
            self._name_edit.text().strip(),
            self._steamid_edit.text().strip(),
            self._avatar_edit.text().strip(),
            self._radio_simple.isChecked(),
            gse_auth,
            gse_user,
            gse_pass,
        )
        self._worker.moveToThread(self._thread)
        self._worker.log_msg.connect(self._log_area.append)
        self._worker.finished.connect(self._on_fix_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _run_revert(self):
        game_path_str = self._path_edit.text().strip()
        if not game_path_str:
            QMessageBox.warning(self, "Missing Input", "Please select a game folder first.")
            return

        game_path = Path(game_path_str)
        if not game_path.exists() or not game_path.is_dir():
            QMessageBox.warning(self, "Invalid Path", "The selected game folder does not exist.")
            return

        reply = QMessageBox.question(
            self, "Confirm Revert",
            f"Revert all Fix Game changes in:\n{game_path}\n\nThis will restore original DLLs and delete steam_settings/.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._run_btn.setEnabled(False)
        self._revert_btn.setEnabled(False)
        self._log_area.clear()
        self._log_area.append("Reverting Fix Game changes...")

        self._thread = QThread()
        self._worker = _RevertWorker(game_path)
        self._worker.moveToThread(self._thread)
        self._worker.log_msg.connect(self._log_area.append)
        self._worker.finished.connect(self._on_revert_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_fix_finished(self, success: bool, msg: str):
        self._run_btn.setEnabled(True)
        self._revert_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        if success:
            QMessageBox.information(self, "Success", "Game fixed successfully!")
        else:
            QMessageBox.critical(self, "Error", f"Failed to fix game:\n{msg}")

    def _on_revert_finished(self, success: bool, msg: str):
        self._run_btn.setEnabled(True)
        self._revert_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        if success:
            QMessageBox.information(self, "Reverted", "Changes reverted successfully.")
        else:
            QMessageBox.critical(self, "Error", f"Revert failed:\n{msg}")
