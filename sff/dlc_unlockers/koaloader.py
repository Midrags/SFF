"""Koaloader DLC unlocker implementation"""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from sff.dlc_unlockers.base import UnlockerBase, UnlockerType, Platform

logger = logging.getLogger(__name__)


class KoaloaderUnlocker(UnlockerBase):
    """Koaloader proxy DLL loader for Steam games
    
    Koaloader works by acting as a proxy DLL (winmm.dll, winhttp.dll, or version.dll)
    that loads SmokeAPI to unlock DLCs.
    """
    
    CONFIG_FILENAME = "Koaloader.config.json"
    # All available proxy DLLs from Koaloader v3.0.4+
    PROXY_OPTIONS = [
        "winmm.dll", "winhttp.dll", "version.dll",  # Original 3
        "audioses.dll", "d3d9.dll", "d3d10.dll", "d3d11.dll",  # DirectX
        "dinput8.dll", "dwmapi.dll", "dxgi.dll",  # Input/Graphics
        "glu32.dll", "hid.dll", "iphlpapi.dll",  # OpenGL/Network
        "msasn1.dll", "msimg32.dll", "mswsock.dll",  # System
        "opengl32.dll", "profapi.dll", "propsys.dll",  # OpenGL/System
        "textshaping.dll", "wldp.dll", "xinput9_1_0.dll"  # Misc
    ]
    BACKUP_SUFFIX = "_o"
    
    # Koaloader v3.0.4+ has a new structure with separate folders for each proxy
    # Format: {proxy_name}-{arch}/{proxy_name}.dll
    # Example: winmm-64/winmm.dll
    
    @property
    def unlocker_type(self) -> UnlockerType:
        return UnlockerType.KOALOADER
    
    @property
    def supported_platforms(self) -> list[Platform]:
        return [Platform.STEAM]
    
    @property
    def display_name(self) -> str:
        return "Koaloader"
    
    def is_installed(self, game_dir: Path) -> bool:
        has_config = (game_dir / self.CONFIG_FILENAME).exists()
        
        # Check for any proxy DLL with backup (indicator of installation)
        has_proxy_backup = any(
            (game_dir / f"{proxy.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll").exists()
            for proxy in self.PROXY_OPTIONS
        )
        
        return has_config and has_proxy_backup
    
    def _select_proxy_dll(self, game_dir: Path, koaloader_dir: Optional[Path] = None, arch: Optional[str] = None) -> Optional[str]:
        # Check which proxy DLLs already exist in the game directory
        existing_proxies = [
            proxy for proxy in self.PROXY_OPTIONS
            if (game_dir / proxy).exists()
        ]
        
        # If a proxy already exists, use the first one found
        if existing_proxies:
            logger.info(f"Found existing proxy DLL: {existing_proxies[0]}")
            return existing_proxies[0]
        
        # If we have koaloader_dir and arch, check which proxies are actually available
        if koaloader_dir and arch:
            available_proxies = []
            for proxy in self.PROXY_OPTIONS:
                proxy_name = proxy.replace('.dll', '')
                koaloader_subdir = f"{proxy_name}-{arch}"
                koaloader_dll_path = koaloader_dir / koaloader_subdir / proxy
                if koaloader_dll_path.exists():
                    available_proxies.append(proxy)
            
            if available_proxies:
                # Prefer d3d9, dinput8, d3d11 if available (winmm/winhttp/version don't have DLLs)
                for preferred in ["d3d9.dll", "dinput8.dll", "d3d11.dll", "dxgi.dll"]:
                    if preferred in available_proxies:
                        logger.info(f"Selected available proxy DLL: {preferred}")
                        return preferred
                
                logger.info(f"Selected first available proxy DLL: {available_proxies[0]}")
                return available_proxies[0]
        
        # Default fallback order (only include proxies that actually have DLLs)
        default_order = ["d3d9.dll", "dinput8.dll", "d3d11.dll", "dxgi.dll", "opengl32.dll"]
        for proxy in default_order:
            if proxy in self.PROXY_OPTIONS:
                logger.info(f"Defaulting to proxy DLL: {proxy}")
                return proxy
        
        # Last resort: return first proxy in list
        logger.warning("No preferred proxy found, using first in list")
        return self.PROXY_OPTIONS[0] if self.PROXY_OPTIONS else None
    
    def install(self, game_dir: Path, dlc_ids: list[int], app_id: int,
                koaloader_dir: Optional[Path] = None,
                smokeapi_dir: Optional[Path] = None,
                proxy_dll: Optional[str] = None) -> bool:
        try:
            # Detect architecture (32 or 64 bit)
            # Check for steam_api64.dll to determine architecture (search in subdirectories too)
            steam_api_64 = game_dir / "steam_api64.dll"
            steam_api_32 = game_dir / "steam_api.dll"
            
            if steam_api_64.exists():
                arch = "64"
            elif steam_api_32.exists():
                arch = "32"
            else:
                # Search in subdirectories
                found_64 = False
                found_32 = False
                
                for dll_path in game_dir.rglob("steam_api64.dll"):
                    logger.info(f"Found steam_api64.dll in subdirectory: {dll_path.relative_to(game_dir)}")
                    found_64 = True
                    break
                
                if not found_64:
                    for dll_path in game_dir.rglob("steam_api.dll"):
                        logger.info(f"Found steam_api.dll in subdirectory: {dll_path.relative_to(game_dir)}")
                        found_32 = True
                        break
                
                if found_64:
                    arch = "64"
                elif found_32:
                    arch = "32"
                else:
                    logger.error("Could not detect game architecture - no steam_api DLL found")
                    return False
            
            logger.info(f"Detected {arch}-bit game architecture")
            
            # Select proxy DLL (pass koaloader_dir and arch to check availability)
            if proxy_dll is None:
                proxy_dll = self._select_proxy_dll(game_dir, koaloader_dir, arch)
            
            if proxy_dll not in self.PROXY_OPTIONS:
                logger.error(f"Invalid proxy DLL: {proxy_dll}")
                return False
            
            logger.info(f"Using proxy DLL: {proxy_dll}")
            
            proxy_path = game_dir / proxy_dll
            backup_path = game_dir / f"{proxy_dll.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
            
            # Backup original proxy DLL if it exists and not already backed up
            if proxy_path.exists() and not backup_path.exists():
                logger.info(f"Backing up original {proxy_dll} to {backup_path.name}")
                shutil.copy2(proxy_path, backup_path)
            elif not proxy_path.exists():
                logger.info(f"No existing {proxy_dll} to backup (will create new)")
            else:
                logger.info(f"Backup already exists: {backup_path.name}")
            
            # Find Koaloader DLL in new structure: {proxy_name}-{arch}/{proxy_name}.dll
            proxy_name = proxy_dll.replace('.dll', '')
            koaloader_subdir = f"{proxy_name}-{arch}"
            
            if koaloader_dir:
                koaloader_dll_path = koaloader_dir / koaloader_subdir / proxy_dll
            else:
                # In production, this would come from the downloader
                koaloader_dll_path = game_dir / koaloader_subdir / proxy_dll
            
            if not koaloader_dll_path.exists():
                logger.error(f"Koaloader DLL not found: {koaloader_dll_path}")
                logger.error(f"Expected structure: {koaloader_subdir}/{proxy_dll}")
                logger.error("Please download Koaloader first using the downloader")
                return False
            
            logger.info(f"Copying Koaloader from {koaloader_subdir}/{proxy_dll}")
            shutil.copy2(koaloader_dll_path, proxy_path)
            
            # Copy SmokeAPI DLLs to game directory
            if smokeapi_dir:
                # Try both naming conventions:
                # 1. GitHub release format: smoke_api32.dll, smoke_api64.dll
                # 2. CreamInstaller format: steam_api.dll, steam_api64.dll
                
                # Map architecture to DLL names
                dll_mappings = [
                    ("smoke_api32.dll", "smoke_api32.dll"),  # GitHub -> target
                    ("smoke_api64.dll", "smoke_api64.dll"),  # GitHub -> target
                    ("steam_api.dll", "smoke_api32.dll"),    # CreamInstaller 32-bit -> target
                    ("steam_api64.dll", "smoke_api64.dll")   # CreamInstaller 64-bit -> target
                ]
                
                copied_count = 0
                for source_name, target_name in dll_mappings:
                    source_path = smokeapi_dir / source_name
                    if source_path.exists():
                        target_path = game_dir / target_name
                        logger.info(f"Copying {source_name} as {target_name}")
                        shutil.copy2(source_path, target_path)
                        copied_count += 1
                
                if copied_count == 0:
                    logger.error(f"No SmokeAPI DLLs found in {smokeapi_dir}")
                    logger.error("Expected: smoke_api32.dll/smoke_api64.dll or steam_api.dll/steam_api64.dll")
            
            # Verify at least one SmokeAPI DLL exists
            if not (game_dir / "smoke_api32.dll").exists() and not (game_dir / "smoke_api64.dll").exists():
                logger.error("No SmokeAPI DLLs found in game directory")
                logger.error("Please download SmokeAPI first using the downloader")
                return False
            
            # Generate and write config file
            config = self.generate_config(dlc_ids, app_id)
            config_path = game_dir / self.CONFIG_FILENAME
            
            logger.info(f"Writing config to {config_path}")
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
            logger.info("Koaloader installation completed successfully")
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
            
            # Restore backups for all proxy DLLs
            for proxy_dll in self.PROXY_OPTIONS:
                backup_path = game_dir / f"{proxy_dll.replace('.dll', '')}{self.BACKUP_SUFFIX}.dll"
                proxy_path = game_dir / proxy_dll
                
                if backup_path.exists():
                    logger.info(f"Restoring backup: {backup_path.name} -> {proxy_dll}")
                    
                    # Remove the Koaloader proxy DLL
                    if proxy_path.exists():
                        proxy_path.unlink()
                    
                    # Restore the backup
                    shutil.copy2(backup_path, proxy_path)
                    
                    # Remove the backup file
                    backup_path.unlink()
                    logger.info(f"Restored {proxy_dll} from backup")
                elif proxy_path.exists():
                    # Check if this is a Koaloader installation without backup
                    # In this case, we should remove the proxy DLL
                    logger.info(f"Removing {proxy_dll} (no backup found)")
                    proxy_path.unlink()
            
            # Remove SmokeAPI DLL files (use correct lowercase names)
            for smokeapi_dll in ["smoke_api32.dll", "smoke_api64.dll"]:
                smokeapi_path = game_dir / smokeapi_dll
                if smokeapi_path.exists():
                    logger.info(f"Removing {smokeapi_dll}")
                    smokeapi_path.unlink()
            
            logger.info("Koaloader uninstallation completed")
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
            "enabled": True,
            "auto_load": True,
            "targets": [],
            "modules": ["smoke_api32.dll", "smoke_api64.dll"]
        }
