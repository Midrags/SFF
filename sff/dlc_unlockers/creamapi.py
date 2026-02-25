"""CreamAPI DLC unlocker implementation"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from .base import Platform, UnlockerBase, UnlockerType
from .downloader import GitHubReleaseDownloader
from .steam_dll_utils import detect_steam_architecture, find_steam_api_dll
from .validation import (
    validate_game_directory,
    validate_write_permissions,
    validate_app_id,
    validate_dlc_ids,
    check_disk_space,
)

logger = logging.getLogger(__name__)


class CreamAPIUnlocker(UnlockerBase):
    """CreamAPI DLC unlocker for Steam games
    
    CreamAPI is an alternative to SmokeAPI that also unlocks Steam DLCs
    by replacing steam_api.dll files. It uses an INI config format instead
    of JSON.
    """
    
    CONFIG_FILENAME = "cream_api.ini"
    STEAM_API_32 = "steam_api.dll"
    STEAM_API_64 = "steam_api64.dll"
    BACKUP_SUFFIX = "_o.dll"
    
    # CreamAPI DLL names (same as SmokeAPI - they replace steam_api.dll)
    CREAMAPI_32_DLL = "steam_api.dll"
    CREAMAPI_64_DLL = "steam_api64.dll"
    
    def __init__(self, downloader: Optional[GitHubReleaseDownloader] = None):
        self.downloader = downloader
    
    @property
    def unlocker_type(self) -> UnlockerType:
        return UnlockerType.CREAMAPI
    
    @property
    def supported_platforms(self) -> list[Platform]:
        return [Platform.STEAM]
    
    @property
    def display_name(self) -> str:
        return "CreamAPI"
    
    def _find_steam_api_dll(self, game_dir: Path, dll_name: str) -> Optional[Path]:
        """Search for steam_api DLL using shared steam_dll_utils."""
        exclude_backup = "_o" not in dll_name  # When searching for backups, don't exclude
        return find_steam_api_dll(game_dir, dll_name, exclude_backup=exclude_backup)

    def _detect_architecture(self, game_dir: Path) -> Optional[str]:
        """Detect if game is 32-bit or 64-bit using shared steam_dll_utils."""
        return detect_steam_architecture(game_dir, self.BACKUP_SUFFIX.replace(".dll", ""))
    
    def is_installed(self, game_dir: Path) -> bool:
        """Check if CreamAPI is installed by looking for config and backup files"""
        # Check for config file in root or subdirectories
        config_exists = (game_dir / self.CONFIG_FILENAME).exists()
        if not config_exists:
            # Search subdirectories
            for _ in game_dir.rglob(self.CONFIG_FILENAME):
                config_exists = True
                break
        
        # Check for backup files
        backup_32 = self._find_steam_api_dll(game_dir, self.STEAM_API_32 + self.BACKUP_SUFFIX)
        backup_64 = self._find_steam_api_dll(game_dir, self.STEAM_API_64 + self.BACKUP_SUFFIX)
        
        return config_exists or backup_32 is not None or backup_64 is not None
    
    def install(self, game_dir: Path, dlc_ids: list[int], app_id: int) -> bool:
        """Install CreamAPI to game directory"""
        # Pre-installation validation
        valid, error = validate_game_directory(game_dir)
        if not valid:
            logger.error(f"Invalid game directory: {error}")
            return False
        
        valid, error = validate_app_id(app_id)
        if not valid:
            logger.error(f"Invalid App ID: {error}")
            return False
        
        valid, error = validate_dlc_ids(dlc_ids)
        if not valid:
            logger.error(f"Invalid DLC IDs: {error}")
            return False
        
        valid, error = validate_write_permissions(game_dir)
        if not valid:
            logger.error(f"Write permission check failed: {error}")
            logger.error("Try running with administrator privileges")
            return False
        
        valid, error = check_disk_space(game_dir, required_bytes=10 * 1024 * 1024)
        if not valid:
            logger.error(f"Disk space check failed: {error}")
            return False
        
        try:
            # Detect architecture
            arch = self._detect_architecture(game_dir)
            if not arch:
                logger.error(f"Could not detect game architecture in {game_dir}")
                return False
            
            # Find the actual steam_api DLL location
            dll_name = self.STEAM_API_64 if arch == "64" else self.STEAM_API_32
            steam_api_path = self._find_steam_api_dll(game_dir, dll_name)
            
            if not steam_api_path:
                logger.error(f"Could not find {dll_name} in {game_dir}")
                return False
            
            # Use the directory where the DLL was found
            target_dir = steam_api_path.parent
            backup_name = dll_name.replace('.dll', self.BACKUP_SUFFIX)
            backup_path = target_dir / backup_name
            
            # Backup original steam_api DLL if not already backed up
            if not backup_path.exists():
                logger.info(f"Backing up {steam_api_path} to {backup_path}")
                shutil.copy2(steam_api_path, backup_path)
            
            # Get CreamAPI DLL from downloader or local resources
            creamapi_dll = None
            if self.downloader:
                creamapi_dll = self.downloader.get_dll(
                    UnlockerType.CREAMAPI,
                    arch
                )
            
            if not creamapi_dll or not creamapi_dll.exists():
                logger.error(f"Could not find CreamAPI DLL for architecture {arch}")
                return False
            
            # Copy CreamAPI DLL as steam_api.dll
            logger.info(f"Installing CreamAPI: {creamapi_dll} -> {steam_api_path}")
            shutil.copy2(creamapi_dll, steam_api_path)
            
            # Generate and write config file
            config_path = target_dir / self.CONFIG_FILENAME
            config_content = self._generate_ini_config(dlc_ids, app_id)
            
            logger.info(f"Writing CreamAPI config to {config_path}")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            logger.info(f"CreamAPI installed successfully to {target_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install CreamAPI: {e}")
            return False
    
    def uninstall(self, game_dir: Path) -> bool:
        """Uninstall CreamAPI and restore original files"""
        try:
            success = True
            config_removed = False
            
            # Find and restore 32-bit DLL
            steam_api_32 = self._find_steam_api_dll(game_dir, self.STEAM_API_32)
            if steam_api_32:
                target_dir = steam_api_32.parent
                backup_name_32 = self.STEAM_API_32.replace('.dll', self.BACKUP_SUFFIX)
                backup_32 = target_dir / backup_name_32
                
                if backup_32.exists():
                    logger.info(f"Restoring {backup_32} to {steam_api_32}")
                    steam_api_32.unlink(missing_ok=True)
                    shutil.move(str(backup_32), str(steam_api_32))
                
                # Remove config
                config_path = target_dir / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Removing config: {config_path}")
                    config_path.unlink()
                    config_removed = True
            
            # Find and restore 64-bit DLL
            steam_api_64 = self._find_steam_api_dll(game_dir, self.STEAM_API_64)
            if steam_api_64:
                target_dir = steam_api_64.parent
                backup_name_64 = self.STEAM_API_64.replace('.dll', self.BACKUP_SUFFIX)
                backup_64 = target_dir / backup_name_64
                
                if backup_64.exists():
                    logger.info(f"Restoring {backup_64} to {steam_api_64}")
                    steam_api_64.unlink(missing_ok=True)
                    shutil.move(str(backup_64), str(steam_api_64))
                
                # Remove config if not already removed
                config_path = target_dir / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Removing config: {config_path}")
                    config_path.unlink()
                    config_removed = True
            
            # If no DLLs were found, still try to remove config from root directory
            if not steam_api_32 and not steam_api_64 and not config_removed:
                config_path = game_dir / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Removing config from root: {config_path}")
                    config_path.unlink()
                else:
                    # Search subdirectories for config
                    for found_config in game_dir.rglob(self.CONFIG_FILENAME):
                        logger.info(f"Removing config: {found_config}")
                        found_config.unlink()
                        break
            
            logger.info("CreamAPI uninstalled successfully")
            return success
            
        except Exception as e:
            logger.error(f"Failed to uninstall CreamAPI: {e}")
            return False
    
    def generate_config(self, dlc_ids: list[int], app_id: int) -> dict:
        """Generate configuration dict for CreamAPI
        
        Note: CreamAPI uses INI format, but we return a dict for consistency
        with other unlockers. The actual INI content is generated by
        _generate_ini_config().
        """
        return {
            "app_id": app_id,
            "dlc_ids": dlc_ids,
            "unlockall": False,
            "orgapi": f"{self.STEAM_API_32}{self.BACKUP_SUFFIX}",
            "orgapi64": f"{self.STEAM_API_64}{self.BACKUP_SUFFIX}",
            "extraprotection": False,
            "forceoffline": False,
            "disableuserinterface": False
        }
    
    def _generate_ini_config(self, dlc_ids: list[int], app_id: int) -> str:
        """Generate CreamAPI INI configuration content"""
        lines = []
        
        # Header comment
        lines.append(f"; CreamAPI Configuration for App ID {app_id}")
        lines.append("")
        
        # [steam] section
        lines.append("[steam]")
        lines.append(f"appid = {app_id}")
        lines.append("unlockall = false")
        lines.append(f"orgapi = {self.STEAM_API_32}{self.BACKUP_SUFFIX}")
        lines.append(f"orgapi64 = {self.STEAM_API_64}{self.BACKUP_SUFFIX}")
        lines.append("extraprotection = false")
        lines.append("forceoffline = false")
        lines.append("")
        
        # [steam_misc] section (required in v5.3.0.0+)
        lines.append("[steam_misc]")
        lines.append("disableuserinterface = false")
        lines.append("")
        
        # [dlc] section
        lines.append("[dlc]")
        for dlc_id in dlc_ids:
            lines.append(f"{dlc_id} = DLC_{dlc_id}")
        
        return "\n".join(lines)
