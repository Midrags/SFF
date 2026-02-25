"""GitHub release downloader for DLC unlocker DLLs"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

import httpx

from smd.dlc_unlockers.base import UnlockerType
from smd.http_utils import download_to_tempfile, get_request

logger = logging.getLogger(__name__)


class GitHubReleaseDownloader:
    RELEASE_URLS = {
        UnlockerType.SMOKEAPI: "https://api.github.com/repos/acidicoala/SmokeAPI/releases/latest",
        UnlockerType.CREAMAPI: "https://api.github.com/repos/acidicoala/CreamAPI/releases/latest",
        UnlockerType.KOALOADER: "https://api.github.com/repos/acidicoala/Koaloader/releases/latest",
        UnlockerType.UPLAY_R1: "https://api.github.com/repos/acidicoala/UplayR1Unlocker/releases/latest",
        UnlockerType.UPLAY_R2: "https://api.github.com/repos/acidicoala/UplayR2Unlocker/releases/latest"
    }
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def download_latest(self, unlocker_type: UnlockerType) -> Optional[Path]:
        if unlocker_type not in self.RELEASE_URLS:
            logger.error(f"No release URL configured for {unlocker_type}")
            return None
        
        # Check local resources first (bundled with the application)
        local_resource = self._get_local_resource(unlocker_type)
        if local_resource:
            logger.info(f"Using local resource for {unlocker_type.value} from {local_resource}")
            return local_resource
        
        # Check if already cached from previous download
        cached = self.get_cached_dll(unlocker_type)
        if cached:
            logger.info(f"Using cached {unlocker_type.value} from {cached}")
            return cached
        
        # Fetch release info from GitHub API with retry logic
        release_url = self.RELEASE_URLS[unlocker_type]
        logger.info(f"Fetching release info from {release_url}")
        
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                release_info = await get_request(release_url, type="json", timeout=30)
                if release_info:
                    break  # Success
                elif attempt < max_retries - 1:
                    logger.warning(f"Empty response, retrying ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(retry_delay)
                    continue
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Network error after {max_retries} attempts: {e}")
                    return None
            except Exception as e:
                logger.error(f"Unexpected error fetching release info for {unlocker_type.value}: {e}")
                return None
        
        if not release_info:
            logger.error(f"Failed to fetch release info after {max_retries} attempts")
            return None
            
        if not release_info:
            logger.error(f"Failed to fetch release info for {unlocker_type.value}")
            return None
        
        # Parse asset download URL
        assets = release_info.get("assets", [])
        if not assets:
            logger.error(f"No assets found in release for {unlocker_type.value}")
            return None
        
        # Find the ZIP asset (usually the first one)
        zip_asset = None
        for asset in assets:
            if asset.get("name", "").endswith(".zip"):
                zip_asset = asset
                break
        
        if not zip_asset:
            logger.error(f"No ZIP asset found in release for {unlocker_type.value}")
            return None
        
        download_url = zip_asset.get("browser_download_url")
        if not download_url:
            logger.error(f"No download URL found for {unlocker_type.value}")
            return None
        
        # Download and extract ZIP
        logger.info(f"Downloading {unlocker_type.value} from {download_url}")
        
        # Create version-specific cache directory
        version = release_info.get("tag_name", "latest")
        cache_subdir = self.cache_dir / unlocker_type.value / version
        cache_subdir.mkdir(parents=True, exist_ok=True)
        
        # Download to temp file and extract
        with download_to_tempfile(download_url) as temp_file:
            if temp_file is None:
                logger.error(f"Failed to download {unlocker_type.value}")
                return None
            
            try:
                with ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(cache_subdir)
                logger.info(f"Extracted {unlocker_type.value} to {cache_subdir}")
                
                # Find the actual DLL directory (may be in a subdirectory)
                dll_dir = self._find_dll_directory(cache_subdir, unlocker_type)
                if dll_dir:
                    logger.info(f"Found DLLs in {dll_dir}")
                    return dll_dir
                else:
                    logger.warning(f"DLLs not found in expected location, returning root: {cache_subdir}")
                    return cache_subdir
            except Exception as e:
                logger.error(f"Failed to extract ZIP for {unlocker_type.value}: {e}")
                return None
    
    def get_cached_dll(self, unlocker_type: UnlockerType) -> Optional[Path]:
        unlocker_cache_dir = self.cache_dir / unlocker_type.value
        if not unlocker_cache_dir.exists():
            return None
        
        # Find the latest version directory
        version_dirs = [d for d in unlocker_cache_dir.iterdir() if d.is_dir()]
        if not version_dirs:
            return None
        
        # Return the most recently modified version
        latest_version = max(version_dirs, key=lambda d: d.stat().st_mtime)
        
        # Find the actual DLL directory within the version directory
        dll_dir = self._find_dll_directory(latest_version, unlocker_type)
        return dll_dir if dll_dir else latest_version
    
    def _find_dll_directory(self, root_dir: Path, unlocker_type: UnlockerType) -> Optional[Path]:
        # Define expected DLL names for each unlocker type
        expected_dlls = {
            UnlockerType.SMOKEAPI: ["smoke_api32.dll", "smoke_api64.dll"],
            UnlockerType.CREAMAPI: ["steam_api.dll", "steam_api64.dll"],
            UnlockerType.KOALOADER: ["winmm-64", "winmm-32", "winhttp-64", "version-64"],  # Koaloader v3.0.4+ has subdirectories
            UnlockerType.UPLAY_R1: ["UplayR1Unlocker.dll", "UplayR1Unlocker32.dll", "UplayR1Unlocker64.dll"],
            UnlockerType.UPLAY_R2: ["UplayR2Unlocker.dll", "UplayR2Unlocker32.dll", "UplayR2Unlocker64.dll"]
        }
        
        items_to_find = expected_dlls.get(unlocker_type, [])
        
        # Search for DLLs/directories in root and subdirectories (max depth 2)
        for depth in range(3):  # Check root, 1 level deep, 2 levels deep
            if depth == 0:
                dirs_to_check = [root_dir]
            elif depth == 1:
                dirs_to_check = [d for d in root_dir.iterdir() if d.is_dir()]
            else:
                dirs_to_check = [
                    subdir 
                    for d in root_dir.iterdir() if d.is_dir()
                    for subdir in d.iterdir() if subdir.is_dir()
                ]
            
            for dir_path in dirs_to_check:
                # Check if any expected DLL/directory exists in this directory
                for item_name in items_to_find:
                    item_path = dir_path / item_name
                    if item_path.exists():
                        logger.debug(f"Found {item_name} in {dir_path}")
                        return dir_path
        
        logger.warning(f"Could not find DLLs for {unlocker_type.value} in {root_dir}")
        return None
    
    def _get_local_resource(self, unlocker_type: UnlockerType) -> Optional[Path]:
        # Local resources are in smd/dlc_unlockers/resources/
        from smd.utils import root_folder
        
        resource_map = {
            UnlockerType.SMOKEAPI: "SmokeAPI",
            UnlockerType.CREAMAPI: "CreamAPI",
            UnlockerType.KOALOADER: "Koaloader",
            UnlockerType.UPLAY_R1: "UplayR1",
            UnlockerType.UPLAY_R2: "UplayR2"
        }
        
        resource_name = resource_map.get(unlocker_type)
        if not resource_name:
            return None
        
        resource_dir = root_folder() / "smd" / "dlc_unlockers" / "resources" / resource_name
        
        if resource_dir.exists() and resource_dir.is_dir():
            logger.debug(f"Found local resource for {unlocker_type.value} at {resource_dir}")
            return resource_dir
        
        logger.debug(f"No local resource found for {unlocker_type.value} at {resource_dir}")
        return None
    
    def get_dll(self, unlocker_type: UnlockerType, architecture: str) -> Optional[Path]:
        # Get the directory containing DLLs
        dll_dir = self.get_cached_dll(unlocker_type)
        if not dll_dir:
            # Try local resources
            dll_dir = self._get_local_resource(unlocker_type)
        
        if not dll_dir:
            return None
        
        # Map unlocker types to their DLL names
        dll_names = {
            UnlockerType.SMOKEAPI: {
                "32": ["steam_api.dll", "smoke_api32.dll"],  # Try both naming conventions
                "64": ["steam_api64.dll", "smoke_api64.dll"]
            },
            UnlockerType.CREAMAPI: {
                "32": ["steam_api.dll"],
                "64": ["steam_api64.dll"]
            },
            UnlockerType.UPLAY_R1: {
                "32": ["uplay_r1_loader.dll"],
                "64": ["uplay_r1_loader64.dll"]
            },
            UnlockerType.UPLAY_R2: {
                "32": ["upc_r2_loader.dll"],
                "64": ["upc_r2_loader64.dll"]
            }
        }
        
        possible_names = dll_names.get(unlocker_type, {}).get(architecture, [])
        
        for dll_name in possible_names:
            dll_path = dll_dir / dll_name
            if dll_path.exists():
                logger.debug(f"Found {dll_name} at {dll_path}")
                return dll_path
        
        logger.warning(f"Could not find {architecture}-bit DLL for {unlocker_type.value} in {dll_dir}")
        return None
