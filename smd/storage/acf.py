import logging
from enum import IntFlag
from pathlib import Path
from typing import Optional

from smd.storage.vdf import get_steam_libs, vdf_load
from smd.utils import enter_path

logger = logging.getLogger(__name__)


class AppState(IntFlag):
    StateInvalid = 0
    StateUninstalled = 1
    StateUpdateRequired = 2
    StateFullyInstalled = 4
    StateEncrypted = 8
    StateLocked = 16
    StateFilesMissing = 32
    StateAppRunning = 64
    StateFilesCorrupt = 128
    StateUpdateRunning = 256
    StateUpdatePaused = 512
    StateUpdateStarted = 1024
    StateUninstalling = 2048
    StateBackupRunning = 4096
    StateReconfiguring = 65536
    StateValidating = 131072
    StateAddingFiles = 262144
    StatePreallocating = 524288
    StateDownloading = 1048576
    StateStaging = 2097152
    StateCommitting = 4194304
    StateUpdateStopping = 8388608


class ACFParser:
    def __init__(self, acf: Path):
        self.data = vdf_load(acf)
        self._name: Optional[str] = None
        self._id: Optional[int] = None
        self._state: Optional[AppState] = None

    @property
    def name(self):
        if self._name is None:
            raw_name: Optional[str] = enter_path(
                self.data, "AppState", "name", default=None
            )
            self._name = raw_name
        return self._name

    @property
    def id(self):
        if self._id is None:
            raw_id: Optional[str] = enter_path(
                self.data, "AppState", "appid", default=None
            )
            if raw_id and raw_id.isdigit():
                self._id = int(raw_id)
        return self._id

    @property
    def state(self):
        if self._state is None:
            raw_state: Optional[str] = enter_path(
                self.data, "AppState", "StateFlags", default=None
            )
            if raw_state and raw_state.isdigit():
                self._state = AppState(int(raw_state))
        return self._state
    
    @property
    def install_dir(self):
        """Get the installation directory name"""
        raw_install_dir: Optional[str] = enter_path(
            self.data, "AppState", "installdir", default=None
        )
        return raw_install_dir if raw_install_dir else ""

    def needs_update(self):
        state = self.state
        if state and AppState.StateUpdateRequired in state:
            return True
        return False


def get_app_name_from_acf(steam_path: Path, app_id: int) -> str:
    """
    Get game name from local ACF files only (no Steam login/API).
    Used by remove-game menu so the list never blocks on "Logging in anonymously...".
    ACF first; store page is used as fallback for uninstalled games.
    """
    libs: list[Path] = []
    try:
        libs = get_steam_libs(steam_path)
    except Exception as e:
        logger.debug("get_steam_libs failed, using steam path only: %s", e)
    if not libs:
        libs = [steam_path]
    for lib in libs:
        acf_path = lib / "steamapps" / f"appmanifest_{app_id}.acf"
        if acf_path.exists():
            try:
                parser = ACFParser(acf_path)
                if parser.name:
                    return parser.name
            except Exception as e:
                logger.debug("ACF parse failed for %s: %s", acf_path, e)
    return str(app_id)
