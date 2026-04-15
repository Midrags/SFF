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
