"""Base classes and enums for DLC unlockers"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path


class UnlockerType(Enum):
    GREENLUMA = "greenluma"
    SMOKEAPI = "smokeapi"
    CREAMAPI = "creamapi"
    KOALOADER = "koaloader"
    UPLAY_R1 = "uplay_r1"
    UPLAY_R2 = "uplay_r2"


class Platform(Enum):
    STEAM = "steam"
    UBISOFT = "ubisoft"


class UnlockerBase(ABC):
    
    @property
    @abstractmethod
    def unlocker_type(self) -> UnlockerType:
        pass

    @property
    @abstractmethod
    def supported_platforms(self) -> list[Platform]:
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass
    
    @abstractmethod
    def is_installed(self, game_dir: Path) -> bool:
        pass
    
    @abstractmethod
    def install(self, game_dir: Path, dlc_ids: list[int], app_id: int) -> bool:
        pass
    
    @abstractmethod
    def uninstall(self, game_dir: Path) -> bool:
        pass
    
    @abstractmethod
    def generate_config(self, dlc_ids: list[int], app_id: int) -> dict:
        pass
