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
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QComboBox, QCheckBox, QFileDialog,
    QMessageBox, QTextEdit,
)

from sff.fix_game.service import FixGameService, EmuMode

logger = logging.getLogger(__name__)


class _FixWorker(QObject):
    finished = pyqtSignal(bool, str)
    log_msg = pyqtSignal(str)

    def __init__(self, game_path: Path, app_id: str, emu_mode: EmuMode,
                 unpack_steamstub: bool, generate_config: bool, create_launch_bat: bool,
                 goldberg_update: bool):
        super().__init__()
        self.game_path = game_path
        self.app_id = app_id
        self.emu_mode = emu_mode
        self.unpack_steamstub = unpack_steamstub
        self.generate_config = generate_config
        self.create_launch_bat = create_launch_bat
        self.goldberg_update = goldberg_update

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
                log_func=self.log_msg.emit
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


class FixGameTab(QWidget):
    """Orchestrates the Fix Game pipeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # target config
        target_group = QGroupBox("Target Game")
        target_layout = QVBoxLayout(target_group)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Game Folder:"))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select the game's root directory...")
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

        # options
        opt_group = QGroupBox("Fix Options")
        opt_layout = QVBoxLayout(opt_group)
        
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Emulator Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Regular Goldberg (steam_api64.dll)", EmuMode.REGULAR)
        self._mode_combo.addItem("ColdClient Loader (exe wrapper)", EmuMode.COLDCLIENT_LOADER)
        self._mode_combo.addItem("ColdLoader DLL (proxy dll)", EmuMode.COLDLOADER_DLL)
        mode_layout.addWidget(self._mode_combo)
        mode_layout.addStretch()
        opt_layout.addLayout(mode_layout)

        self._chk_goldberg_update = QCheckBox("Check for Goldberg updates (downloads latest from GitHub)")
        self._chk_goldberg_update.setChecked(False)
        opt_layout.addWidget(self._chk_goldberg_update)

        self._chk_steamstub = QCheckBox("Auto-unpack SteamStub DRM (Steamless)")
        self._chk_steamstub.setChecked(True)
        opt_layout.addWidget(self._chk_steamstub)

        self._chk_config = QCheckBox("Generate steam_settings (Interfaces, DLCs, stats)")
        self._chk_config.setChecked(True)
        opt_layout.addWidget(self._chk_config)

        self._chk_launchbat = QCheckBox("Create Launch.bat (For ColdClient)")
        self._chk_launchbat.setChecked(False)
        opt_layout.addWidget(self._chk_launchbat)
        
        layout.addWidget(opt_group)

        # Run button
        self._run_btn = QPushButton("Run Fix Game Pipeline")
        self._run_btn.setFixedHeight(40)
        self._run_btn.clicked.connect(self._run_fix)
        layout.addWidget(self._run_btn)

        # Log output
        log_group = QGroupBox("Status Output")
        log_layout = QVBoxLayout(log_group)
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        log_layout.addWidget(self._log_area)
        layout.addWidget(log_group)

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
        # game is usually at: <library>/steamapps/common/<GameName>
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
        self._log_area.clear()
        self._log_area.append("Starting Fix Game pipeline...")

        # Run in thread
        self._thread = QThread()
        self._worker = _FixWorker(
            game_path,
            app_id,
            self._mode_combo.currentData(),
            self._chk_steamstub.isChecked(),
            self._chk_config.isChecked(),
            self._chk_launchbat.isChecked(),
            self._chk_goldberg_update.isChecked(),
        )
        self._worker.moveToThread(self._thread)
        
        self._worker.log_msg.connect(self._log_area.append)
        self._worker.finished.connect(self._on_finished)
        
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_finished(self, success: bool, msg: str):
        self._run_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            
        if success:
            QMessageBox.information(self, "Success", "Game fixed successfully!")
        else:
            QMessageBox.critical(self, "Error", f"Failed to fix game:\n{msg}")
