"""Backup system for critical files and folders"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from colorama import Fore, Style

from smd.storage.settings import get_setting
from smd.structs import Settings
from smd.utils import root_folder

logger = logging.getLogger(__name__)

BACKUP_DIR = root_folder(outside_internal=True) / "backups"
DEFAULT_RETENTION = 5  # Keep last 5 backups


class BackupManager:
    """Manages backups of critical files and folders"""
    
    def __init__(self):
        self.backup_dir = BACKUP_DIR
        self.backup_dir.mkdir(exist_ok=True)
    
    def get_retention_count(self) -> int:
        """Get backup retention count from settings"""
        try:
            retention_str = get_setting(Settings.BACKUP_RETENTION)
            if retention_str:
                return max(1, int(retention_str))
        except (ValueError, TypeError, AttributeError):
            pass
        return DEFAULT_RETENTION
    
    def create_backup(self, source: Path, backup_name: Optional[str] = None) -> Optional[Path]:
        """
        Create a backup of a file or folder.
        
        Args:
            source: Path to file or folder to backup
            backup_name: Optional custom backup name
            
        Returns:
            Path to backup if successful, None otherwise
        """
        try:
            if not source.exists():
                logger.error(f"Source does not exist: {source}")
                return None
            
            # Generate backup name with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if backup_name is None:
                backup_name = f"{source.name}_{timestamp}"
            else:
                backup_name = f"{backup_name}_{timestamp}"
            
            backup_path = self.backup_dir / backup_name
            
            # Create backup
            if source.is_dir():
                shutil.copytree(source, backup_path)
                logger.info(f"Created folder backup: {backup_path}")
            else:
                shutil.copy2(source, backup_path)
                logger.info(f"Created file backup: {backup_path}")
            
            # Cleanup old backups
            self._cleanup_old_backups(source.name)
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to create backup of {source}: {e}", exc_info=True)
            return None
    
    def restore_backup(self, backup_path: Path, destination: Path) -> bool:
        """
        Restore from a backup.
        
        Args:
            backup_path: Path to backup to restore
            destination: Where to restore the backup
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not backup_path.exists():
                logger.error(f"Backup does not exist: {backup_path}")
                return False
            
            # Verify backup integrity (basic check)
            if not self._verify_backup(backup_path):
                logger.error(f"Backup integrity check failed: {backup_path}")
                return False
            
            # Remove destination if it exists
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            
            # Restore backup
            if backup_path.is_dir():
                shutil.copytree(backup_path, destination)
            else:
                shutil.copy2(backup_path, destination)
            
            logger.info(f"Restored backup from {backup_path} to {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}", exc_info=True)
            return False
    
    def list_backups(self, filter_name: Optional[str] = None) -> list[Path]:
        """
        List available backups.
        
        Args:
            filter_name: Optional filter to show only backups matching this name
            
        Returns:
            List of backup paths sorted by modification time (newest first)
        """
        try:
            if filter_name:
                backups = [p for p in self.backup_dir.iterdir() if p.name.startswith(filter_name)]
            else:
                backups = list(self.backup_dir.iterdir())
            
            # Sort by modification time, newest first
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}", exc_info=True)
            return []
    
    def _verify_backup(self, backup_path: Path) -> bool:
        """Basic integrity check for backup"""
        try:
            if backup_path.is_dir():
                # Check if directory is not empty
                return any(backup_path.iterdir())
            else:
                # Check if file is not empty
                return backup_path.stat().st_size > 0
        except Exception as e:
            logger.error(f"Backup verification failed: {e}", exc_info=True)
            return False
    
    def _cleanup_old_backups(self, source_name: str):
        """Remove old backups beyond retention count"""
        try:
            retention = self.get_retention_count()
            backups = self.list_backups(source_name)
            
            # Remove backups beyond retention count
            for backup in backups[retention:]:
                try:
                    if backup.is_dir():
                        shutil.rmtree(backup)
                    else:
                        backup.unlink()
                    logger.info(f"Removed old backup: {backup}")
                except Exception as e:
                    logger.error(f"Failed to remove old backup {backup}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}", exc_info=True)
    
    def get_backup_size(self) -> int:
        """Get total size of all backups in bytes"""
        try:
            total_size = 0
            for backup in self.backup_dir.rglob("*"):
                if backup.is_file():
                    total_size += backup.stat().st_size
            return total_size
        except Exception as e:
            logger.error(f"Failed to calculate backup size: {e}", exc_info=True)
            return 0


# Global backup manager instance
_backup_manager: Optional[BackupManager] = None


def get_backup_manager() -> BackupManager:
    """Get or create global backup manager instance"""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager


def backup_before_operation(source: Path, operation_name: str) -> Optional[Path]:
    """
    Convenience function to create a backup before a risky operation.
    
    Args:
        source: Path to backup
        operation_name: Name of the operation (for backup naming)
        
    Returns:
        Path to backup if successful, None otherwise
    """
    manager = get_backup_manager()
    print(Fore.YELLOW + f"Creating backup before {operation_name}..." + Style.RESET_ALL)
    backup_path = manager.create_backup(source, f"{operation_name}_{source.name}")
    
    if backup_path:
        print(Fore.GREEN + f"✓ Backup created: {backup_path.name}" + Style.RESET_ALL)
    else:
        print(Fore.RED + "✗ Failed to create backup" + Style.RESET_ALL)
    
    return backup_path
