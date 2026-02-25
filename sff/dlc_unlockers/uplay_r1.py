"""Uplay R1 DLC unlocker implementation"""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from sff.dlc_unlockers.base import UnlockerBase, UnlockerType, Platform

logger = logging.getLogger(__name__)


class UplayR1Unlocker(UnlockerBase):
    """Uplay R1 DLC unlocker for older Ubisoft Connect games
    
    Uplay R1 works by replacing the original uplay_r1_loader.dll with its own version
    that intercepts DLC checks and reports all DLCs as owned.
    """
    
    CONFIG_FILENAME = "UplayR1Unlocker.jsonc"
    TARGET_DLL = "uplay_r1_loader.dll"
    BACKUP_SUFFIX = "_o"
    
    # DLL name in the Uplay R1 Unlocker release package
    UPLAY_R1_UNLOCKER_DLL = "uplay_r1_loader.dll"
    
    @property
    def unlocker_type(self) -> UnlockerType:
        """Returns the type of this unlocker"""
        return UnlockerType.UPLAY_R1
    
    @property
    def supported_platforms(self) -> list[Platform]:
        """Returns platforms this unlocker supports"""
        return [Platform.UBISOFT]
    
    @property
    def display_name(self) -> str:
        """Human-readable name for UI"""
        return "Uplay R1 Unlocker"
    
    def is_installed(self, game_dir: Path) -> bool:
        """Check if Uplay R1 Unlocker is currently installed
        
        Args:
            game_dir: Game installation directory
            
        Returns:
            True if Uplay R1 Unlocker DLL and config are present
        """
        has_config = (game_dir / self.CONFIG_FILENAME).exists()
        
        # Check for backup file as an indicator of installation
        has_backup = (game_dir / f"{self.TARGET_DLL.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll").exists()
        
        return has_config and has_backup
    
    def install(self, game_dir: Path, dlc_ids: list[int], app_id: int,
                unlocker_dir: Optional[Path] = None) -> bool:
        """Install Uplay R1 Unlocker to game directory
        
        Args:
            game_dir: Game installation directory
            dlc_ids: List of DLC IDs to unlock (not used by Uplay R1, unlocks all)
            app_id: Ubisoft App ID of the game
            unlocker_dir: Directory containing Uplay R1 Unlocker DLL (optional, for testing)
            
        Returns:
            True if installation succeeded, False otherwise
        """
        try:
            original_dll_path = game_dir / self.TARGET_DLL
            backup_dll_path = game_dir / f"{self.TARGET_DLL.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            
            # Check if original DLL exists
            if not original_dll_path.exists():
                logger.error(f"Original DLL not found: {original_dll_path}")
                logger.error("This game may not be a Uplay R1 game")
                return False
            
            # Backup original DLL if not already backed up
            if not backup_dll_path.exists():
                logger.info(f"Backing up original {self.TARGET_DLL} to {backup_dll_path.name}")
                shutil.copy2(original_dll_path, backup_dll_path)
            else:
                logger.info(f"Backup already exists: {backup_dll_path.name}")
            
            # Copy Uplay R1 Unlocker DLL
            if unlocker_dir:
                # Use provided directory (for testing or manual installation)
                unlocker_dll_path = unlocker_dir / self.UPLAY_R1_UNLOCKER_DLL
            else:
                # In production, this would come from the downloader
                # For now, we'll just check if it exists in the game directory
                unlocker_dll_path = game_dir / self.UPLAY_R1_UNLOCKER_DLL
            
            if not unlocker_dll_path.exists():
                logger.error(f"Uplay R1 Unlocker DLL not found: {unlocker_dll_path}")
                logger.error("Please download Uplay R1 Unlocker first using the downloader")
                return False
            
            logger.info(f"Copying {self.UPLAY_R1_UNLOCKER_DLL} as {self.TARGET_DLL}")
            shutil.copy2(unlocker_dll_path, original_dll_path)
            
            # Generate and write config file
            config = self.generate_config(dlc_ids, app_id)
            config_path = game_dir / self.CONFIG_FILENAME
            
            logger.info(f"Writing config to {config_path}")
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
            logger.info("Uplay R1 Unlocker installation completed successfully")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied during installation: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during installation: {e}")
            return False
    
    def uninstall(self, game_dir: Path) -> bool:
        """Remove Uplay R1 Unlocker and restore backups
        
        Args:
            game_dir: Game installation directory
            
        Returns:
            True if uninstallation succeeded, False otherwise
        """
        try:
            # Remove config file
            config_path = game_dir / self.CONFIG_FILENAME
            if config_path.exists():
                logger.info(f"Removing {self.CONFIG_FILENAME}")
                config_path.unlink()
            
            # Restore backup
            backup_path = game_dir / f"{self.TARGET_DLL.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            original_path = game_dir / self.TARGET_DLL
            
            if backup_path.exists():
                logger.info(f"Restoring backup: {backup_path.name} -> {self.TARGET_DLL}")
                
                # Remove the Uplay R1 Unlocker DLL
                if original_path.exists():
                    original_path.unlink()
                
                # Restore the backup
                shutil.copy2(backup_path, original_path)
                
                # Remove the backup file
                backup_path.unlink()
                logger.info(f"Restored {self.TARGET_DLL} from backup")
            elif original_path.exists():
                # DLL exists but no backup - warn user
                logger.warning(f"No backup found for {self.TARGET_DLL}, leaving file in place")
                logger.warning("Manual verification recommended")
            
            logger.info("Uplay R1 Unlocker uninstallation completed")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied during uninstallation: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during uninstallation: {e}")
            return False
    
    def generate_config(self, dlc_ids: list[int], app_id: int) -> dict:
        """Generate Uplay R1 Unlocker configuration
        
        Args:
            dlc_ids: List of DLC IDs (not used, Uplay R1 unlocks all by default)
            app_id: Ubisoft App ID of the game
            
        Returns:
            Configuration dictionary for Uplay R1 Unlocker
        """
        return {
            "logging": False,
            "lang": "default",
            "blacklist": []  # Empty = unlock all DLCs
        }
