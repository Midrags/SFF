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

"""
Fix Game pipeline — makes downloaded games playable.

Orchestrates: DRM detection → Goldberg update → config generation →
SteamStub unpacking → Goldberg application → Launch.bat generation.
"""

from sff.fix_game.service import FixGameService
from sff.fix_game.cache import FixGameCache
from sff.fix_game.goldberg_updater import GoldbergUpdater
from sff.fix_game.config_generator import GoldbergConfigGenerator
from sff.fix_game.steamstub_unpacker import SteamStubUnpacker
from sff.fix_game.goldberg_applier import GoldbergApplier

__all__ = [
    "FixGameService",
    "FixGameCache",
    "GoldbergUpdater",
    "GoldbergConfigGenerator",
    "SteamStubUnpacker",
    "GoldbergApplier",
]
