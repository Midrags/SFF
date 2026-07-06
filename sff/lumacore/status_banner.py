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
import json
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_REQUIRED_KEYS = {"build_id", "toml_found", "hooks_installed", "hooks_missed", "steamclient_sha", "steamui_sha"}
_TOML_KEYS = {"steamclient", "steamui"}
logger = logging.getLogger(__name__)


class StatusBannerPoller(QObject):
    unavailable = pyqtSignal(str)
    cleared = pyqtSignal()

    def __init__(self, steam_path: Path, parent=None):
        super().__init__(parent)
        self._status_path = steam_path / "lumacore" / "status.json"
        self._last_good = None

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        try:
            raw = self._status_path.read_bytes()
            payload = json.loads(raw)
        except Exception:
            return

        if not self._validate(payload):
            return

        if self._last_good == payload:
            return

        self._last_good = payload

        toml_ok = (
            payload.get("toml_found", {}).get("steamclient", False)
            and payload.get("toml_found", {}).get("steamui", False)
        )

        if toml_ok:
            self.cleared.emit()
        else:
            self.unavailable.emit(self._compose(payload))

    def _validate(self, payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        if not _REQUIRED_KEYS.issubset(payload.keys()):
            return False
        toml = payload.get("toml_found")
        if not isinstance(toml, dict):
            return False
        if not _TOML_KEYS.issubset(toml.keys()):
            return False
        for v in toml.values():
            if not isinstance(v, bool):
                return False
        for key in ("hooks_installed",):
            v = payload.get(key)
            if not isinstance(v, int):
                return False
        for key in ("steamclient_sha", "steamui_sha"):
            v = payload.get(key, "")
            if not isinstance(v, str):
                return False
        return True

    @staticmethod
    def _compose(payload: dict) -> str:
        build_id = payload.get("build_id", "?")
        sc_sha = payload.get("steamclient_sha", "")[:12]
        sui_sha = payload.get("steamui_sha", "")[:12]
        reason = payload.get("diagnostic_reason", "")
        pattern_status = payload.get("pattern_status", {})
        parts = [f"Steam build {build_id}"]
        if sc_sha:
            parts.append(f"steamclient: {sc_sha}")
        if sui_sha:
            parts.append(f"steamui: {sui_sha}")

        no_cache = reason == "pattern-missing-no-cache"
        if isinstance(pattern_status, dict):
            for module in ("steamclient", "steamui"):
                status = pattern_status.get(module, {})
                if not isinstance(status, dict):
                    continue
                source = status.get("source", "")
                if source in ("", "none"):
                    no_cache = True

        if no_cache:
            parts.append(
                "No cached LumaCore support data for this Steam build. "
                "Start Steam once with internet, downgrade Steam if possible, "
                "or report this build."
            )
        else:
            parts.append(
                "LumaCore support data is still loading. Restart Steam after "
                "the fetch finishes, or report this build if it keeps happening."
            )
        return " | ".join(parts)
