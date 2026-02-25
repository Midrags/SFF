"""Game Library Scanner for SFF"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from colorama import Fore, Style

from sff.storage.acf import ACFParser
from sff.storage.vdf import get_steam_libs
from sff.progress import create_progress_bar

logger = logging.getLogger(__name__)


@dataclass
class GameInfo:
    """Information about an installed game"""
    app_id: int
    name: str
    install_dir: str
    library_path: Path
    needs_manifest: bool
    has_lua_backup: bool
    in_applist: bool
    has_acf: bool


class LibraryScanner:
    """Scans Steam library for installed games and manifest status"""
    
    def __init__(self, steam_path: Path, lua_backup_path: Path, applist_folder: Optional[Path] = None):
        """
        Initialize library scanner
        
        Args:
            steam_path: Path to Steam installation
            lua_backup_path: Path to lua backup directory
            applist_folder: Path to GreenLuma AppList folder (optional)
        """
        self.steam_path = steam_path
        self.lua_backup_path = lua_backup_path
        self.applist_folder = applist_folder
    
    def _get_applist_ids(self) -> Set[int]:
        """
        Get all App IDs from GreenLuma AppList folder
        
        Returns:
            Set of App IDs found in AppList
        """
        app_ids: Set[int] = set()
        
        if not self.applist_folder or not self.applist_folder.exists():
            return app_ids
        
        try:
            for file in self.applist_folder.glob("*.txt"):
                if not file.stem.isdigit():
                    continue
                
                try:
                    content = file.read_text(encoding="utf-8").strip()
                    if content.isdigit():
                        app_ids.add(int(content))
                except Exception as e:
                    logger.debug(f"Failed to read {file.name}: {e}")
            
            logger.info(f"Found {len(app_ids)} IDs in AppList folder")
        except Exception as e:
            logger.error(f"Failed to scan AppList folder: {e}")
        
        return app_ids
    
    def _scan_all_drives(self) -> List[Path]:
        """
        Scan all drives for Steam library folders
        
        Returns:
            List of potential Steam library paths
        """
        steam_libs = []
        
        # Get libraries from Steam's config
        try:
            configured_libs = get_steam_libs(self.steam_path)
            steam_libs.extend(configured_libs)
            logger.info(f"Found {len(configured_libs)} configured Steam libraries")
        except Exception as e:
            logger.warning(f"Failed to read Steam library config: {e}")
        
        # Scan all drives for additional Steam libraries
        if os.name == 'nt':  # Windows
            from string import ascii_uppercase
            for drive_letter in ascii_uppercase:
                drive = Path(f"{drive_letter}:/")
                if not drive.exists():
                    continue
                
                # Common Steam library locations
                potential_paths = [
                    drive / "SteamLibrary",
                    drive / "Steam",
                    drive / "Program Files (x86)" / "Steam",
                    drive / "Program Files" / "Steam",
                    drive / "Games" / "Steam",
                ]
                
                for path in potential_paths:
                    steamapps = path / "steamapps"
                    if steamapps.exists() and path not in steam_libs:
                        steam_libs.append(path)
                        logger.info(f"Discovered Steam library: {path}")
        
        return steam_libs
    
    def scan_all_games(self, scan_all_drives: bool = True) -> List[GameInfo]:
        """
        Scan all Steam libraries for installed games
        
        Args:
            scan_all_drives: If True, scan all drives for Steam libraries
        
        Returns:
            List of GameInfo objects
        """
        logger.info("Starting comprehensive library scan...")
        
        # Get AppList IDs
        applist_ids = self._get_applist_ids()
        
        # Get Steam libraries
        if scan_all_drives:
            steam_libs = self._scan_all_drives()
        else:
            steam_libs = get_steam_libs(self.steam_path)
        
        # Remove duplicates
        steam_libs = list(set(steam_libs))
        
        all_games: List[GameInfo] = []
        seen_app_ids: Set[int] = set()
        
        print(Fore.CYAN + f"\nScanning {len(steam_libs)} Steam libraries across all drives..." + Style.RESET_ALL)
        
        for lib in steam_libs:
            print(Fore.LIGHTBLACK_EX + f"  Scanning: {lib}" + Style.RESET_ALL)
            games = self._scan_library(lib, applist_ids, seen_app_ids)
            all_games.extend(games)
        
        # Also check for games in AppList that might not have ACF files
        orphaned_games = self._check_orphaned_applist_ids(applist_ids, seen_app_ids)
        all_games.extend(orphaned_games)
        
        logger.info(f"Found {len(all_games)} total games ({len(seen_app_ids)} with ACF files)")
        print(Fore.GREEN + f"\n✓ Found {len(all_games)} installed games" + Style.RESET_ALL)
        
        return all_games
    
    def _scan_library(self, library_path: Path, applist_ids: Set[int], seen_app_ids: Set[int]) -> List[GameInfo]:
        """
        Scan a single Steam library
        
        Args:
            library_path: Path to Steam library
            applist_ids: Set of App IDs in AppList
            seen_app_ids: Set to track which App IDs we've already seen
            
        Returns:
            List of GameInfo objects
        """
        games: List[GameInfo] = []
        steamapps = library_path / "steamapps"
        
        if not steamapps.exists():
            logger.warning(f"Steamapps folder not found: {steamapps}")
            return games
        
        acf_files = list(steamapps.glob("appmanifest_*.acf"))
        
        for acf_file in acf_files:
            try:
                acf = ACFParser(acf_file)
                
                # Get app info
                app_id = acf.id
                app_name = acf.name
                app_install_dir = acf.install_dir
                
                # Skip if essential data is missing
                if not app_id or not app_name:
                    logger.warning(f"Skipping {acf_file}: missing app_id or name")
                    continue
                
                # Skip if we've already seen this app_id (duplicate across libraries)
                if app_id in seen_app_ids:
                    logger.debug(f"Skipping duplicate app_id {app_id} in {library_path}")
                    continue
                
                seen_app_ids.add(app_id)
                
                # Check if game is actually installed (has files)
                game_path = steamapps / "common" / app_install_dir
                if not game_path.exists():
                    logger.debug(f"Skipping {app_name}: install directory not found")
                    continue
                
                # Check if lua backup exists
                lua_backup_file = self.lua_backup_path / f"{app_id}.lua"
                has_lua_backup = lua_backup_file.exists()
                
                # Check if in AppList
                in_applist = app_id in applist_ids
                
                # Check if manifest update is needed
                needs_manifest = acf.needs_update()
                
                game_info = GameInfo(
                    app_id=app_id,
                    name=app_name,
                    install_dir=app_install_dir,
                    library_path=library_path,
                    needs_manifest=needs_manifest,
                    has_lua_backup=has_lua_backup,
                    in_applist=in_applist,
                    has_acf=True
                )
                games.append(game_info)
                
            except Exception as e:
                logger.error(f"Failed to parse {acf_file}: {e}")
        
        return games
    
    def _check_orphaned_applist_ids(self, applist_ids: Set[int], seen_app_ids: Set[int]) -> List[GameInfo]:
        """
        Check for App IDs in AppList that don't have ACF files
        
        Args:
            applist_ids: Set of App IDs in AppList
            seen_app_ids: Set of App IDs that have ACF files
            
        Returns:
            List of GameInfo objects for orphaned IDs
        """
        orphaned_games: List[GameInfo] = []
        orphaned_ids = applist_ids - seen_app_ids
        
        if orphaned_ids:
            logger.info(f"Found {len(orphaned_ids)} App IDs in AppList without ACF files")
            
            for app_id in orphaned_ids:
                # Check if lua backup exists
                lua_backup_file = self.lua_backup_path / f"{app_id}.lua"
                has_lua_backup = lua_backup_file.exists()
                
                game_info = GameInfo(
                    app_id=app_id,
                    name=f"App ID {app_id} (No ACF)",
                    install_dir="",
                    library_path=Path(""),
                    needs_manifest=True,  # Assume needs manifest if no ACF
                    has_lua_backup=has_lua_backup,
                    in_applist=True,
                    has_acf=False
                )
                orphaned_games.append(game_info)
        
        return orphaned_games
    
    def filter_needs_manifest(self, games: List[GameInfo]) -> List[GameInfo]:
        """
        Filter games that need manifest updates
        
        Args:
            games: List of all games
            
        Returns:
            List of games needing manifests
        """
        return [g for g in games if g.needs_manifest]
    
    def filter_downloaded_only(self, games: List[GameInfo]) -> List[GameInfo]:
        """
        Filter to show only games that are actually downloaded
        
        Args:
            games: List of all games
            
        Returns:
            List of downloaded games (have ACF and install directory)
        """
        return [g for g in games if g.has_acf and g.install_dir]
    
    def generate_report_text(self, games: List[GameInfo]) -> str:
        """
        Generate a text report of scanned games
        
        Args:
            games: List of games
            
        Returns:
            Formatted text report
        """
        needs_manifest = self.filter_needs_manifest(games)
        downloaded_only = self.filter_downloaded_only(games)
        
        report = []
        report.append("=" * 80)
        report.append("SFF Comprehensive Library Scan Report")
        report.append("=" * 80)
        report.append(f"\nTotal games found: {len(games)}")
        report.append(f"Downloaded games (with files): {len(downloaded_only)}")
        report.append(f"Games in AppList: {sum(1 for g in games if g.in_applist)}")
        report.append(f"Games needing manifests: {len(needs_manifest)}")
        report.append(f"Games with lua backups: {sum(1 for g in games if g.has_lua_backup)}")
        report.append(f"Orphaned AppList IDs (no ACF): {sum(1 for g in games if not g.has_acf)}")
        
        if downloaded_only:
            report.append("\n" + "=" * 80)
            report.append("Downloaded Games:")
            report.append("=" * 80)
            for game in sorted(downloaded_only, key=lambda g: g.name.lower()):
                report.append(f"\n[{game.app_id}] {game.name}")
                report.append(f"  Library: {game.library_path}")
                report.append(f"  In AppList: {'Yes' if game.in_applist else 'No'}")
                report.append(f"  Has Lua Backup: {'Yes' if game.has_lua_backup else 'No'}")
                report.append(f"  Needs Manifest: {'Yes' if game.needs_manifest else 'No'}")
        
        if needs_manifest:
            report.append("\n" + "=" * 80)
            report.append("Games Needing Manifest Updates:")
            report.append("=" * 80)
            for game in needs_manifest:
                report.append(f"\n[{game.app_id}] {game.name}")
                if game.has_acf:
                    report.append(f"  Library: {game.library_path}")
                report.append(f"  In AppList: {'Yes' if game.in_applist else 'No'}")
                report.append(f"  Has Lua Backup: {'Yes' if game.has_lua_backup else 'No'}")
        
        return "\n".join(report)
    
    def generate_report_json(self, games: List[GameInfo]) -> dict:
        """
        Generate a JSON report of scanned games
        
        Args:
            games: List of games
            
        Returns:
            Dictionary suitable for JSON export
        """
        needs_manifest = self.filter_needs_manifest(games)
        downloaded_only = self.filter_downloaded_only(games)
        
        return {
            "total_games": len(games),
            "downloaded_games_count": len(downloaded_only),
            "in_applist_count": sum(1 for g in games if g.in_applist),
            "needs_manifest_count": len(needs_manifest),
            "has_backup_count": sum(1 for g in games if g.has_lua_backup),
            "orphaned_ids_count": sum(1 for g in games if not g.has_acf),
            "games": [
                {
                    "app_id": g.app_id,
                    "name": g.name,
                    "install_dir": g.install_dir,
                    "library_path": str(g.library_path),
                    "needs_manifest": g.needs_manifest,
                    "has_lua_backup": g.has_lua_backup,
                    "in_applist": g.in_applist,
                    "has_acf": g.has_acf
                }
                for g in games
            ],
            "downloaded_games": [
                {
                    "app_id": g.app_id,
                    "name": g.name,
                    "library_path": str(g.library_path),
                    "in_applist": g.in_applist
                }
                for g in downloaded_only
            ],
            "needs_manifest": [
                {
                    "app_id": g.app_id,
                    "name": g.name,
                    "has_lua_backup": g.has_lua_backup,
                    "in_applist": g.in_applist
                }
                for g in needs_manifest
            ]
        }
    
    def export_report(
        self,
        games: List[GameInfo],
        output_path: Path,
        format: str = "json"
    ) -> bool:
        """
        Export scan report to file
        
        Args:
            games: List of games
            output_path: Output file path
            format: Output format ('json' or 'text')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if format == "json":
                report = self.generate_report_json(games)
                with output_path.open("w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
            else:  # text
                report = self.generate_report_text(games)
                with output_path.open("w", encoding="utf-8") as f:
                    f.write(report)
            
            logger.info(f"Report exported to: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export report: {e}", exc_info=True)
            return False
