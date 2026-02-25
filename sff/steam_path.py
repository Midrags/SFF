import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from colorama import Fore, Style

from sff.prompts import prompt_dir
from sff.storage.settings import get_setting, set_setting
from sff.structs import OSType, Settings

if sys.platform == "win32":
    from sff.registry_access import find_steam_path_from_registry
else:
    find_steam_path_from_registry = lambda: None  # noqa: E731

logger = logging.getLogger(__name__)


def validate_steam_path(path: Optional[Path]) -> bool:
    return path is not None and (path / "steamapps").exists()


class PathFinderStrategy(ABC):
    @abstractmethod
    def find(self) -> Optional[Path]:
        pass


class RegistryFinder(PathFinderStrategy):
    def find(self) -> Optional[Path]:
        path = find_steam_path_from_registry()

        if validate_steam_path(path):
            return path
        return None


class LinuxFinder(PathFinderStrategy):
    def find(self) -> Optional[Path]:
        steam_dir = (Path.home() / ".steam/root").resolve()
        if steam_dir.exists():
            return steam_dir


class UserInputFinder(PathFinderStrategy):
    def __init__(self, validator: Callable[[Path], bool]):
        self.validator = validator

    def find(self) -> Path:
        print("Couldn't find your Steam path.")
        return prompt_dir(
            msg="Paste the path here (The folder that has steam.exe)",
            custom_check=self.validator,
            custom_msg="Make sure the folder has steam.exe in it"
        )


class SettingsFinder(PathFinderStrategy):
    def __init__(self):
        self.raw_path: Optional[str] = None
        "populated after find() is ran"

    def find(self) -> Optional[Path]:
        self.raw_path = get_setting(Settings.STEAM_PATH)
        if self.raw_path is not None:
            path = Path(self.raw_path)
            if validate_steam_path(path):
                return path


class SteamPathService:
    def __init__(self, finders: list[PathFinderStrategy]):
        self.finders = finders

    def get_path(self) -> Path:
        for finder in self.finders:
            path = finder.find()
            if path:
                self._log_success(path)
                return path

        raise FileNotFoundError("Steam path could not be resolved.")

    def _log_success(self, path: Path):
        colorized = Fore.YELLOW + str(path.resolve()) + Style.RESET_ALL
        print(f"Your Steam path is {colorized}")


def init_steam_path(os_type: OSType):
    """Finds steam path and saves it to settings if it's new"""
    settings_strat = SettingsFinder()
    os_specific_finder: list[PathFinderStrategy] = []
    if os_type == OSType.WINDOWS:
        os_specific_finder.append(RegistryFinder())
    elif os_type == OSType.LINUX:
        os_specific_finder.append(LinuxFinder())

    strategies: list[PathFinderStrategy] = [
        settings_strat,
        *os_specific_finder,
        UserInputFinder(validator=validate_steam_path),
    ]

    service = SteamPathService(strategies)
    path = service.get_path()
    path_str = str(path.resolve())
    if path_str != settings_strat.raw_path:
        logger.debug("Updating STEAM_PATH in Settings")
        set_setting(Settings.STEAM_PATH, path_str)
    return path
