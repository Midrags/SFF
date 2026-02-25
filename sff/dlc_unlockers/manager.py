"""Unlocker manager for orchestrating DLC unlocker operations"""

import logging
from pathlib import Path
from typing import Optional

from sff.dlc_unlockers.base import UnlockerBase, UnlockerType, Platform
from sff.dlc_unlockers.smokeapi import SmokeAPIUnlocker
from sff.dlc_unlockers.creamapi import CreamAPIUnlocker
from sff.dlc_unlockers.koaloader import KoaloaderUnlocker
from sff.dlc_unlockers.uplay_r1 import UplayR1Unlocker
from sff.dlc_unlockers.uplay_r2 import UplayR2Unlocker
from sff.storage.settings import load_all_settings, set_setting
from sff.structs import Settings

logger = logging.getLogger(__name__)


class UnlockerManager:
    def __init__(self, steam_path: Optional[Path] = None):
        self.steam_path = steam_path
        self.unlockers: list[UnlockerBase] = [
            SmokeAPIUnlocker(),
            CreamAPIUnlocker(),
            KoaloaderUnlocker(),
            UplayR1Unlocker(),
            UplayR2Unlocker()
        ]
    
    def detect_platform(self, game_dir: Path) -> Platform:
        # Check for Steam DLLs
        if (game_dir / "steam_api.dll").exists() or (game_dir / "steam_api64.dll").exists():
            logger.info(f"Detected Steam platform in {game_dir}")
            return Platform.STEAM
        
        # Check for Ubisoft Connect R1 DLL
        if (game_dir / "uplay_r1_loader.dll").exists():
            logger.info(f"Detected Ubisoft Connect (R1) platform in {game_dir}")
            return Platform.UBISOFT
        
        # Check for Ubisoft Connect R2 DLL
        if (game_dir / "upc_r2_loader.dll").exists():
            logger.info(f"Detected Ubisoft Connect (R2) platform in {game_dir}")
            return Platform.UBISOFT
        
        # Default to Steam if no platform-specific DLLs found
        logger.warning(f"No platform-specific DLLs found in {game_dir}, defaulting to Steam")
        return Platform.STEAM
    
    def get_compatible_unlockers(self, platform: Platform) -> list[UnlockerBase]:
        compatible = [u for u in self.unlockers if platform in u.supported_platforms]
        logger.info(f"Found {len(compatible)} compatible unlockers for {platform.value}")
        return compatible
    
    def get_active_unlocker(self, app_id: int) -> Optional[UnlockerType]:
        settings = load_all_settings()
        unlocker_map = settings.get(Settings.ACTIVE_UNLOCKER_PER_GAME.key_name, {})
        
        unlocker_value = unlocker_map.get(str(app_id))
        if unlocker_value:
            try:
                return UnlockerType(unlocker_value)
            except ValueError:
                logger.warning(f"Invalid unlocker type '{unlocker_value}' for app {app_id}")
                return None
        
        return None
    
    def set_active_unlocker(self, app_id: int, unlocker_type: UnlockerType) -> None:
        settings = load_all_settings()
        unlocker_map = settings.get(Settings.ACTIVE_UNLOCKER_PER_GAME.key_name, {})
        
        # Update the map
        unlocker_map[str(app_id)] = unlocker_type.value
        
        # Save back to settings
        # Note: set_setting expects str or bool, but ACTIVE_UNLOCKER_PER_GAME is a dict
        # We need to save it directly
        settings[Settings.ACTIVE_UNLOCKER_PER_GAME.key_name] = unlocker_map
        
        # Write to file
        import msgpack
        from sff.storage.settings import SETTINGS_FILE
        with SETTINGS_FILE.open("wb") as f:
            f.write(msgpack.packb(settings))
        
        logger.info(f"Set active unlocker for app {app_id} to {unlocker_type.value}")
    
    def get_unlocker_by_type(self, unlocker_type: UnlockerType) -> Optional[UnlockerBase]:
        for unlocker in self.unlockers:
            if unlocker.unlocker_type == unlocker_type:
                return unlocker
        
        logger.warning(f"No unlocker found for type {unlocker_type.value}")
        return None
