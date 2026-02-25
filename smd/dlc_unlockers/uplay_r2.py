"""Uplay R2 DLC unlocker implementation"""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from smd.dlc_unlockers.base import UnlockerBase, UnlockerType, Platform

logger = logging.getLogger(__name__)


class UplayR2Unlocker(UnlockerBase):
    """Uplay R2 DLC unlocker for newer Ubisoft Connect games
    
    Uplay R2 works by replacing the original upc_r2_loader.dll with its own version
    that intercepts DLC checks and reports all DLCs as owned.
    """
    
    CONFIG_FILENAME = "UplayR2Unlocker.jsonc"
    TARGET_DLL = "upc_r2_loader.dll"
    BACKUP_SUFFIX = "_o"
    
    # DLL name in the Uplay R2 Unlocker release package
    UNLOCKER_DLL = "UplayR2Unlocker.dll"
    
    @property
    def unlocker_type(self) -> UnlockerType:
        return UnlockerType.UPLAY_R2
    
    @property
    def supported_platforms(self) -> list[Platform]:
        return [Platform.UBISOFT]
    
    @property
    def display_name(self) -> str:
        return "Uplay R2 Unlocker"
    
    def is_installed(self, game_dir: Path) -> bool:
        has_config = (game_dir / self.CONFIG_FILENAME).exists()
        
        # Check for backup file as an indicator of installation
        has_backup = (game_dir / f"{self.TARGET_DLL.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll").exists()
        
        return has_config and has_backup
    
    def install(self, game_dir: Path, dlc_ids: list[int], app_id: int,
                unlocker_dir: Optional[Path] = None) -> bool:
        try:
            target_dll_path = game_dir / self.TARGET_DLL
            backup_dll_path = game_dir / f"{self.TARGET_DLL.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            
            # Check if target DLL exists
            if not target_dll_path.exists() and not backup_dll_path.exists():
                logger.error(f"Target DLL not found: {target_dll_path}")
                logger.error("This game may not be compatible with Uplay R2 Unlocker")
                return False
            
            # Backup original DLL if not already backed up
            if not backup_dll_path.exists():
                if target_dll_path.exists():
                    logger.info(f"Backing up original {self.TARGET_DLL} to {backup_dll_path.name}")
                    shutil.copy2(target_dll_path, backup_dll_path)
                else:
                    logger.error(f"Original DLL not found: {target_dll_path}")
                    return False
            else:
                logger.info(f"Backup already exists: {backup_dll_path.name}")
            
            # Copy Uplay R2 Unlocker DLL
            if unlocker_dir:
                # Use provided directory (for testing or manual installation)
                unlocker_dll_path = unlocker_dir / self.UNLOCKER_DLL
            else:
                # In production, this would come from the downloader
                # For now, we'll just check if it exists in the game directory
                unlocker_dll_path = game_dir / self.UNLOCKER_DLL
            
            if not unlocker_dll_path.exists():
                logger.error(f"Uplay R2 Unlocker DLL not found: {unlocker_dll_path}")
                logger.error("Please download Uplay R2 Unlocker first using the downloader")
                return False
            
            logger.info(f"Copying {self.UNLOCKER_DLL} as {self.TARGET_DLL}")
            shutil.copy2(unlocker_dll_path, target_dll_path)
            
            # Generate and write config file
            config = self.generate_config(dlc_ids, app_id)
            config_path = game_dir / self.CONFIG_FILENAME
            
            logger.info(f"Writing config to {config_path}")
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
            logger.info("Uplay R2 Unlocker installation completed successfully")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied during installation: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during installation: {e}")
            return False
    
    def uninstall(self, game_dir: Path) -> bool:
        try:
            # Remove config file
            config_path = game_dir / self.CONFIG_FILENAME
            if config_path.exists():
                logger.info(f"Removing {self.CONFIG_FILENAME}")
                config_path.unlink()
            
            # Restore backup
            backup_path = game_dir / f"{self.TARGET_DLL.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            target_path = game_dir / self.TARGET_DLL
            
            if backup_path.exists():
                logger.info(f"Restoring backup: {backup_path.name} -> {self.TARGET_DLL}")
                
                # Remove the Uplay R2 Unlocker DLL
                if target_path.exists():
                    target_path.unlink()
                
                # Restore the backup
                shutil.copy2(backup_path, target_path)
                
                # Remove the backup file
                backup_path.unlink()
                logger.info(f"Restored {self.TARGET_DLL} from backup")
            elif target_path.exists():
                # DLL exists but no backup - warn user
                logger.warning(f"No backup found for {self.TARGET_DLL}, leaving file in place")
                logger.warning("Manual verification recommended")
            
            # Remove Uplay R2 Unlocker DLL if it exists in the directory
            unlocker_path = game_dir / self.UNLOCKER_DLL
            if unlocker_path.exists():
                logger.info(f"Removing {self.UNLOCKER_DLL}")
                unlocker_path.unlink()
            
            logger.info("Uplay R2 Unlocker uninstallation completed")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied during uninstallation: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during uninstallation: {e}")
            return False
    
    def generate_config(self, dlc_ids: list[int], app_id: int) -> dict:
        return {
            "logging": False,
            "lang": "default",
            "blacklist": []  # Empty = unlock all DLCs
        }
