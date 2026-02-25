"""SmokeAPI DLC unlocker implementation"""

import json
import logging
import shutil
from pathlib import Path
from typing import NamedTuple, Optional

from sff.dlc_unlockers.base import UnlockerBase, UnlockerType, Platform
from sff.dlc_unlockers.steam_dll_utils import (
    detect_steam_architecture,
    find_all_steam_api_locations,
)
from sff.dlc_unlockers.validation import (
    validate_game_directory,
    validate_write_permissions,
    validate_app_id,
    validate_dlc_ids,
    check_disk_space,
)

logger = logging.getLogger(__name__)


class InstallLocation(NamedTuple):
    path: Path
    dll_name: str
    architecture: str


class SmokeAPIUnlocker(UnlockerBase):
    """SmokeAPI DLC unlocker for Steam games
    
    SmokeAPI works by replacing the original steam_api.dll with its own version
    that intercepts DLC checks and reports all DLCs as owned.
    """
    
    CONFIG_FILENAME = "SmokeAPI.config.json"
    DLL_32_NAME = "steam_api.dll"
    DLL_64_NAME = "steam_api64.dll"
    BACKUP_SUFFIX = "_o"
    
    # DLL names in the SmokeAPI release package
    SMOKEAPI_32_DLL = "smoke_api32.dll"
    SMOKEAPI_64_DLL = "smoke_api64.dll"
    
    @property
    def unlocker_type(self) -> UnlockerType:
        return UnlockerType.SMOKEAPI
    
    @property
    def supported_platforms(self) -> list[Platform]:
        return [Platform.STEAM]
    
    @property
    def display_name(self) -> str:
        return "SmokeAPI"
    
    def is_installed(self, game_dir: Path) -> bool:
        # Search for backup files recursively
        for backup_path in game_dir.rglob(f"*{self.BACKUP_SUFFIX}.dll"):
            # Check if this is a steam_api backup
            backup_name = backup_path.name
            if backup_name.startswith("steam_api64") or backup_name.startswith("steam_api"):
                logger.debug(f"Found SmokeAPI backup: {backup_path.relative_to(game_dir)}")
                return True
        
        return False
    
    def _detect_architecture(self, game_dir: Path) -> Optional[str]:
        return detect_steam_architecture(game_dir, self.BACKUP_SUFFIX)

    def _find_all_installation_locations(self, game_dir: Path) -> list[InstallLocation]:
        raw = find_all_steam_api_locations(game_dir, self.BACKUP_SUFFIX)
        return [InstallLocation(path=p, dll_name=name, architecture=arch) for p, name, arch in raw]
    
    def _install_to_location(
        self, 
        location: InstallLocation, 
        smokeapi_dll_path: Path,
        config: Optional[dict],
        game_dir: Path
    ) -> bool:
        try:
            # Construct paths
            original_dll_path = location.path / location.dll_name
            backup_dll_path = location.path / f"{location.dll_name.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            
            # Get relative path for logging
            try:
                relative_path = location.path.relative_to(game_dir)
                relative_path_str = str(relative_path) if str(relative_path) != '.' else "(root)"
            except (ValueError, AttributeError):
                relative_path_str = str(location.path)
            
            # Step 0: Delete old CreamAPI config if present (CreamInstaller behavior)
            creamapi_config = location.path / "cream_api.ini"
            if creamapi_config.exists():
                logger.info(f"Deleted old CreamAPI configuration: {creamapi_config.name}")
                creamapi_config.unlink()
            
            # Step 1: Create backup of original DLL if not exists
            if not backup_dll_path.exists():
                if original_dll_path.exists():
                    logger.info(f"Creating backup at {relative_path_str}: {location.dll_name} -> {backup_dll_path.name}")
                    shutil.copy2(original_dll_path, backup_dll_path)
                else:
                    logger.error(f"Original DLL not found at {relative_path_str}: {original_dll_path}")
                    return False
            else:
                logger.info(f"Backup already exists at {relative_path_str}: {backup_dll_path.name}")
            
            # Step 2: Copy SmokeAPI DLL to location
            if not smokeapi_dll_path.exists():
                logger.error(f"SmokeAPI DLL not found: {smokeapi_dll_path}")
                return False
            
            logger.info(f"Installing SmokeAPI to {relative_path_str}: {smokeapi_dll_path.name} -> {location.dll_name}")
            shutil.copy2(smokeapi_dll_path, original_dll_path)
            
            # Step 3: Write config file if config dict is provided
            if config is not None:
                config_path = location.path / self.CONFIG_FILENAME
                logger.info(f"Writing configuration to {relative_path_str}: {self.CONFIG_FILENAME}")
                with config_path.open("w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
            else:
                # Delete existing config file if config is not needed
                config_path = location.path / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Deleted unnecessary configuration: {self.CONFIG_FILENAME}")
                    config_path.unlink()
            
            logger.info(f"Successfully installed SmokeAPI to {relative_path_str}")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied at {relative_path_str}: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Failed to install to {relative_path_str}: {e}")
            return False
    
    def _uninstall_from_location(self, location: InstallLocation, game_dir: Path) -> bool:
        try:
            # Construct paths
            original_dll_path = location.path / location.dll_name
            backup_dll_path = location.path / f"{location.dll_name.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            config_path = location.path / self.CONFIG_FILENAME
            
            # Get relative path for logging
            try:
                relative_path = location.path.relative_to(game_dir)
                relative_path_str = str(relative_path) if str(relative_path) != '.' else "(root)"
            except (ValueError, AttributeError):
                relative_path_str = str(location.path)
            
            # Step 1: Check for backup file
            if not backup_dll_path.exists():
                logger.warning(f"No backup found at {relative_path_str}: {backup_dll_path.name}")
                return False
            
            # Step 2: Restore backup to original DLL name
            logger.info(f"Restoring backup at {relative_path_str}: {backup_dll_path.name} -> {location.dll_name}")
            
            # Remove the current DLL if it exists
            if original_dll_path.exists():
                original_dll_path.unlink()
            
            # Restore the backup
            shutil.copy2(backup_dll_path, original_dll_path)
            
            # Step 3: Delete backup file after restoration
            logger.info(f"Deleting backup at {relative_path_str}: {backup_dll_path.name}")
            backup_dll_path.unlink()
            
            # Step 4: Delete config file if exists
            if config_path.exists():
                logger.info(f"Deleting config at {relative_path_str}: {self.CONFIG_FILENAME}")
                config_path.unlink()
            
            logger.info(f"Successfully uninstalled SmokeAPI from {relative_path_str}")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied at {relative_path_str}: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Failed to uninstall from {relative_path_str}: {e}")
            return False
    
    def _find_steam_api_dll(self, game_dir: Path, dll_name: str) -> Optional[Path]:
        # Check root directory first
        dll_path = game_dir / dll_name
        if dll_path.exists():
            return dll_path
        
        # Search in subdirectories
        for found_dll in game_dir.rglob(dll_name):
            logger.info(f"Found {dll_name} in subdirectory: {found_dll.relative_to(game_dir)}")
            return found_dll
        
        return None

    def install(self, game_dir: Path, dlc_ids: list[int], app_id: int, 
                smokeapi_dir: Optional[Path] = None) -> bool:
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
        
        valid, error = check_disk_space(game_dir, required_bytes=10 * 1024 * 1024)  # 10MB
        if not valid:
            logger.error(f"Disk space check failed: {error}")
            return False
        
        try:
            # Step 1: Detect proxy mode installations
            proxy_files = self.detect_proxy_mode(game_dir)
            if proxy_files:
                logger.info(f"Uninstalling SmokeAPI in proxy mode from {game_dir.name}")
                # Step 2: If proxy mode found, uninstall it first
                if not self.uninstall(game_dir):
                    logger.error("Failed to uninstall proxy mode installation")
                    logger.error("Aborting direct mode installation")
                    return False
                logger.info("Proxy mode cleanup completed")
            
            # Step 3: Find all installation locations
            locations = self._find_all_installation_locations(game_dir)
            if not locations:
                logger.error(f"Could not find any steam_api DLL files in {game_dir}")
                logger.error("No steam_api.dll or steam_api64.dll found")
                return False
            
            logger.info(f"Found {len(locations)} installation location(s)")
            
            # Log architecture information
            architectures = set(loc.architecture for loc in locations)
            if len(architectures) > 1:
                logger.info("Installing both 32-bit and 64-bit versions")
            
            # Step 4: Generate config (CreamInstaller always creates SmokeAPI.config.json)
            config = self.generate_config(dlc_ids, app_id)
            
            # Step 5: Install to all locations
            successes = []
            failures = []
            
            for location in locations:
                # Determine which SmokeAPI DLL to use
                if location.architecture == "32":
                    smokeapi_dll_name = self.SMOKEAPI_32_DLL
                else:
                    smokeapi_dll_name = self.SMOKEAPI_64_DLL
                
                # Find the SmokeAPI DLL
                if smokeapi_dir:
                    # Try both naming conventions:
                    # 1. CreamInstaller format: steam_api.dll / steam_api64.dll (already renamed)
                    # 2. GitHub release format: smoke_api32.dll / smoke_api64.dll (needs renaming)
                    
                    # Check for CreamInstaller format first
                    creaminstaller_dll = smokeapi_dir / location.dll_name
                    if creaminstaller_dll.exists():
                        smokeapi_dll_path = creaminstaller_dll
                    else:
                        # Try GitHub release format
                        smokeapi_dll_path = smokeapi_dir / smokeapi_dll_name
                        if not smokeapi_dll_path.exists():
                            logger.error(f"SmokeAPI DLL not found in {smokeapi_dir}")
                            logger.error(f"Looked for: {location.dll_name} and {smokeapi_dll_name}")
                            failures.append(location)
                            continue
                else:
                    # In production, this would come from the downloader
                    smokeapi_dll_path = location.path / smokeapi_dll_name
                    if not smokeapi_dll_path.exists():
                        logger.error(f"SmokeAPI DLL not found: {smokeapi_dll_path}")
                        logger.error("Please download SmokeAPI first using the downloader")
                        failures.append(location)
                        continue
                
                # Install to this location
                if self._install_to_location(location, smokeapi_dll_path, config, game_dir):
                    successes.append(location)
                else:
                    failures.append(location)
            
            # Step 6: Log summary of installations
            logger.info(f"Installation summary: {len(successes)} succeeded, {len(failures)} failed")
            
            if failures:
                logger.error(f"Failed to install to {len(failures)} location(s)")
                for location in failures:
                    try:
                        relative_path = location.path.relative_to(game_dir)
                        logger.error(f"  - {relative_path}")
                    except ValueError:
                        logger.error(f"  - {location.path}")
            
            # Step 7: Return True if all succeeded, False if any failed
            return len(failures) == 0
            
        except PermissionError as e:
            logger.error(f"Permission denied during installation: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during installation: {e}")
            return False
    
    def uninstall(self, game_dir: Path) -> bool:
        try:
            # Step 1: Find all installation locations by searching for backup files
            locations = []
            
            # Search for all backup files recursively
            for backup_path in game_dir.rglob(f"*{self.BACKUP_SUFFIX}.dll"):
                # Determine which DLL this is a backup of
                backup_name = backup_path.name
                if backup_name.startswith("steam_api64"):
                    dll_name = self.DLL_64_NAME
                    architecture = "64"
                elif backup_name.startswith("steam_api"):
                    dll_name = self.DLL_32_NAME
                    architecture = "32"
                else:
                    # Not a steam_api backup, skip
                    continue
                
                # Create InstallLocation for this backup
                location = InstallLocation(
                    path=backup_path.parent,
                    dll_name=dll_name,
                    architecture=architecture
                )
                locations.append(location)
            
            if not locations:
                logger.info("No SmokeAPI installations found to uninstall")
                # Still clean up any orphaned config files
                for config_path in game_dir.rglob(self.CONFIG_FILENAME):
                    try:
                        logger.info(f"Removing orphaned config: {config_path.relative_to(game_dir)}")
                        config_path.unlink()
                    except Exception as e:
                        logger.warning(f"Could not remove config file: {e}")
                return True
            
            logger.info(f"Found {len(locations)} installation location(s) to uninstall")
            
            # Step 2: Uninstall from all locations
            successes = []
            failures = []
            
            for location in locations:
                if self._uninstall_from_location(location, game_dir):
                    successes.append(location)
                else:
                    failures.append(location)
            
            # Also remove any SmokeAPI DLL files if they exist
            for smokeapi_dll in [self.SMOKEAPI_32_DLL, self.SMOKEAPI_64_DLL]:
                for dll_path in game_dir.rglob(smokeapi_dll):
                    try:
                        logger.info(f"Removing {smokeapi_dll}: {dll_path.relative_to(game_dir)}")
                        dll_path.unlink()
                    except Exception as e:
                        logger.warning(f"Could not remove {smokeapi_dll}: {e}")
            
            # Step 3: Log summary of uninstallations
            logger.info(f"Uninstallation summary: {len(successes)} succeeded, {len(failures)} failed")
            
            if failures:
                logger.error(f"Failed to uninstall from {len(failures)} location(s)")
                for location in failures:
                    try:
                        relative_path = location.path.relative_to(game_dir)
                        logger.error(f"  - {relative_path}")
                    except ValueError:
                        logger.error(f"  - {location.path}")
            
            # Step 4: Return True if all succeeded, False if any failed
            return len(failures) == 0
            
        except PermissionError as e:
            logger.error(f"Permission denied during uninstallation: {e}")
            logger.error("Try running with administrator privileges")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during uninstallation: {e}")
            return False
    
    def generate_config(self, dlc_ids: list[int], app_id: int) -> dict:
        # Include all DLCs in extra_dlcs so they show as available (avoids hiding LUA/GreenLuma DLCs)
        extra_dlcs = {str(dlc_id): {} for dlc_id in dlc_ids} if dlc_ids else {}
        return {
            "$version": 4,
            "logging": False,
            "log_steam_http": False,
            "default_app_status": "unlocked",
            "override_app_status": {},
            "override_dlc_status": {},
            "auto_inject_inventory": True,
            "extra_inventory_items": [],
            "extra_dlcs": extra_dlcs
        }
    
    def has_locked_dlcs(self, dlc_ids: list[int]) -> bool:
        return len(dlc_ids) > 0

    def detect_proxy_mode(self, game_dir: Path) -> list[Path]:
        proxy_files = []
        
        # Koaloader configuration file names to check
        koaloader_configs = [
            "koaloader_config.json",
            "Koaloader.config.json",
            "koaloader.json"
        ]
        
        # Common proxy DLL names
        proxy_dlls = [
            "version.dll",
            "winmm.dll",
            "winhttp.dll",
            "dsound.dll"
        ]
        
        # Check for Koaloader config files
        for config_name in koaloader_configs:
            config_path = game_dir / config_name
            if config_path.exists():
                # Verify it references SmokeAPI
                try:
                    with config_path.open("r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        
                    # Check if config references SmokeAPI
                    if "modules" in config_data:
                        for module in config_data["modules"]:
                            if isinstance(module, dict) and "path" in module:
                                module_path = module["path"].lower()
                                if "smokeapi" in module_path:
                                    proxy_files.append(config_path)
                                    logger.info(f"Found Koaloader config referencing SmokeAPI: {config_name}")
                                    break
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Could not parse Koaloader config {config_name}: {e}")
                    # Still add it as a potential proxy file if it exists
                    proxy_files.append(config_path)
        
        # Check for common proxy DLL files
        for dll_name in proxy_dlls:
            dll_path = game_dir / dll_name
            if dll_path.exists():
                proxy_files.append(dll_path)
                logger.info(f"Found proxy DLL: {dll_name}")
        
        # Also search in subdirectories for proxy files
        for config_name in koaloader_configs:
            for config_path in game_dir.rglob(config_name):
                if config_path not in proxy_files:
                    # Verify it references SmokeAPI
                    try:
                        with config_path.open("r", encoding="utf-8") as f:
                            config_data = json.load(f)
                            
                        # Check if config references SmokeAPI
                        if "modules" in config_data:
                            for module in config_data["modules"]:
                                if isinstance(module, dict) and "path" in module:
                                    module_path = module["path"].lower()
                                    if "smokeapi" in module_path:
                                        proxy_files.append(config_path)
                                        logger.info(f"Found Koaloader config in subdirectory: {config_path.relative_to(game_dir)}")
                                        break
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.warning(f"Could not parse Koaloader config {config_path.relative_to(game_dir)}: {e}")
                        # Still add it as a potential proxy file if it exists
                        proxy_files.append(config_path)
        
        for dll_name in proxy_dlls:
            for dll_path in game_dir.rglob(dll_name):
                if dll_path not in proxy_files:
                    proxy_files.append(dll_path)
                    logger.info(f"Found proxy DLL in subdirectory: {dll_path.relative_to(game_dir)}")
        
        return proxy_files


