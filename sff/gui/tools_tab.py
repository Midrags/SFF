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

"""Tools tab — GBE Token Generator and VDF Key Extractor."""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit
)

from sff.tools.gbe_token_generator import GBETokenGenerator
from sff.tools.vdf_key_extractor import VdfKeyExtractor

logger = logging.getLogger(__name__)


class ToolsTab(QWidget):

    def __init__(self, steam_path: Path, parent=None):
        super().__init__(parent)
        self.steam_path = steam_path
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        from sff.gui.help_buttons import add_help_button
        add_help_button(
            layout,
            "Tools",
            "Tools — Extra Utilities\n\n"
            "GBE Token Generator:\n"
            "  Generate Goldberg Emulator configuration files (user_steam_id,\n"
            "  account_name, etc.) for games you own on your Steam account.\n"
            "  Requires a Steam Web API key and the game to be owned by your\n"
            "  logged-in Steam account.\n"
            "  Get your API key: steamcommunity.com/dev/apikey\n\n"
            "VDF Depot Key Extractor:\n"
            "  Read decryption keys from your Steam config.vdf file. These\n"
            "  keys are used to decrypt game manifests and are needed for\n"
            "  downloading older game versions. The extracted keys are shown\n"
            "  in a table you can copy from.",
            parent_widget=self,
        )
        # GBE Token Generator
        gbe_group = QGroupBox("GBE Token Generator")
        gbe_layout = QVBoxLayout(gbe_group)
        gbe_desc = QLabel(
            "Generate Goldberg Emulator configuration files for games. "
            "This requires Steam to be running and the game to be owned by the logged-in account."
        )
        gbe_desc.setWordWrap(True)
        gbe_layout.addWidget(gbe_desc)
        # Steam Web API Key
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("Steam Web API Key:"))
        self._gbe_api_key = QLineEdit()
        self._gbe_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._gbe_api_key.setPlaceholderText("Enter your Steam Web API key")
        key_layout.addWidget(self._gbe_api_key)
        try:
            from sff.storage.settings import get_setting
            from sff.structs import Settings
            from sff.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
            _pre = get_setting(Settings.STEAM_WEB_API_KEY) or _DEFAULT_KEY
            if _pre:
                self._gbe_api_key.setText(_pre)
        except Exception:
            pass
        gbe_layout.addLayout(key_layout)
        key_hint = QLabel("Get your Steam Web API key at: https://steamcommunity.com/dev/apikey")
        key_hint.setOpenExternalLinks(False)
        gbe_layout.addWidget(key_hint)
        # App ID
        appid_layout = QHBoxLayout()
        appid_layout.addWidget(QLabel("Steam App ID:"))
        self._gbe_app_id = QLineEdit()
        self._gbe_app_id.setPlaceholderText("Enter App ID")
        appid_layout.addWidget(self._gbe_app_id)
        gbe_layout.addLayout(appid_layout)
        # Output Directory
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("Output Directory:"))
        self._gbe_out_dir = QLineEdit()
        self._gbe_out_dir.setPlaceholderText("Select output folder")
        out_layout.addWidget(self._gbe_out_dir)
        gbe_browse = QPushButton("Browse")
        gbe_browse.clicked.connect(self._browse_gbe_dir)
        out_layout.addWidget(gbe_browse)
        gbe_layout.addLayout(out_layout)
        gbe_btn = QPushButton("Generate Token")
        gbe_btn.clicked.connect(self._gen_gbe_token)
        gbe_layout.addWidget(gbe_btn)
        # Log Output
        self._gbe_log = QTextEdit()
        self._gbe_log.setReadOnly(True)
        self._gbe_log.setMaximumHeight(180)
        self._gbe_log.setPlaceholderText("Ready to generate tokens. Make sure Steam is running and you own the game.")
        gbe_layout.addWidget(QLabel("Log Output"))
        gbe_layout.addWidget(self._gbe_log)
        # Credits
        credits_label = QLabel(
            "GBE Token Generator developed by:\n"
            "  - Detanup01\n"
            "  - NickAntaris\n"
            "  - Oureveryday"
        )
        gbe_layout.addWidget(credits_label)
        layout.addWidget(gbe_group)
        # VDF Key Extractor
        vdf_group = QGroupBox("VDF Depot Key Extractor")
        vdf_layout = QVBoxLayout(vdf_group)
        vdf_in_layout = QHBoxLayout()
        vdf_in_layout.addWidget(QLabel("config.vdf path:"))
        self._vdf_path = QLineEdit()
        default_vdf = self.steam_path / "config" / "config.vdf"
        if default_vdf.exists():
            self._vdf_path.setText(str(default_vdf))
        vdf_in_layout.addWidget(self._vdf_path)
        vdf_browse = QPushButton("Browse")
        vdf_browse.clicked.connect(self._browse_vdf)
        vdf_in_layout.addWidget(vdf_browse)
        vdf_layout.addLayout(vdf_in_layout)
        vdf_btn = QPushButton("Extract Keys")
        vdf_btn.clicked.connect(self._extract_vdf_keys)
        vdf_layout.addWidget(vdf_btn)
        self._vdf_table = QTableWidget()
        self._vdf_table.setColumnCount(3)
        self._vdf_table.setHorizontalHeaderLabels(["App ID", "Depot ID", "Decryption Key"])
        self._vdf_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._vdf_table.setMinimumHeight(150)
        vdf_layout.addWidget(self._vdf_table)
        layout.addWidget(vdf_group)
        layout.addStretch()

    def _browse_gbe_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Output Directory")
        if path:
            self._gbe_out_dir.setText(path)

    def _gen_gbe_token(self):
        api_key = self._gbe_api_key.text().strip()
        if not api_key:
            from sff.strings import STEAM_WEB_API_KEY as _DEFAULT_KEY
            api_key = _DEFAULT_KEY
        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "No Steam Web API key available.")
            return
        app_id_str = self._gbe_app_id.text().strip()
        if not app_id_str.isdigit():
            QMessageBox.warning(self, "Invalid Input", "App ID must be a number.")
            return
        out_dir_str = self._gbe_out_dir.text().strip()
        if not out_dir_str:
            QMessageBox.warning(self, "Invalid Input", "Please select an output directory.")
            return
        self._gbe_log.clear()
        gen = GBETokenGenerator(steam_web_api_key=api_key)
        try:
            success = gen.generate(
                int(app_id_str), out_dir_str,
                log_func=lambda msg: self._gbe_log.append(msg),
            )
            if success:
                self._gbe_log.append("\nDone! Config package generated successfully.")
                try:
                    from sff.storage.settings import set_setting
                    from sff.structs import Settings
                    set_setting(Settings.STEAM_WEB_API_KEY, api_key)
                except Exception:
                    pass
            else:
                self._gbe_log.append("\nGeneration failed. Check the log above.")
        except Exception as e:
            self._gbe_log.append(f"CRITICAL ERROR: {e}")

    def _browse_vdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select config.vdf", str(self.steam_path), "VDF files (*.vdf);;All files (*.*)")
        if path:
            self._vdf_path.setText(path)

    def _extract_vdf_keys(self):
        vdf_path = Path(self._vdf_path.text().strip())
        if not vdf_path.exists() or not vdf_path.is_file():
            QMessageBox.warning(self, "Invalid Path", "config.vdf path is invalid.")
            return
        ext = VdfKeyExtractor()
        try:
            keys = ext.extract_keys(vdf_path)
            self._vdf_table.setRowCount(len(keys))
            for i, key_data in enumerate(keys):
                self._vdf_table.setItem(i, 0, QTableWidgetItem(str(key_data.get('app_id', ''))))
                self._vdf_table.setItem(i, 1, QTableWidgetItem(str(key_data.get('depot_id', ''))))
                self._vdf_table.setItem(i, 2, QTableWidgetItem(str(key_data.get('key', ''))))
            QMessageBox.information(self, "Success", f"Extracted {len(keys)} keys.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
