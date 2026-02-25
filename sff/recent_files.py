"""Recent Files Management for SFF"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from sff.utils import root_folder

logger = logging.getLogger(__name__)

RECENT_FILES_PATH = root_folder(outside_internal=True) / "recent_files.json"
MAX_RECENT_FILES = 10


class RecentFilesManager:
    """Manages the list of recently processed lua files"""
    
    def __init__(self):
        """Initialize the recent files manager"""
        self.recent_files: List[str] = []
        self.load()
    
    def load(self) -> None:
        """Load recent files from disk"""
        try:
            if RECENT_FILES_PATH.exists():
                with RECENT_FILES_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.recent_files = data.get("files", [])
                logger.debug(f"Loaded {len(self.recent_files)} recent files")
        except Exception as e:
            logger.error(f"Failed to load recent files: {e}", exc_info=True)
            self.recent_files = []
    
    def save(self) -> None:
        """Save recent files to disk"""
        try:
            data = {"files": self.recent_files}
            with RECENT_FILES_PATH.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self.recent_files)} recent files")
        except Exception as e:
            logger.error(f"Failed to save recent files: {e}", exc_info=True)
    
    def add(self, file_path: Path) -> None:
        """
        Add a file to the recent files list
        
        Args:
            file_path: Path to the lua file
        """
        file_str = str(file_path.resolve())
        
        # Remove if already exists (to move it to the front)
        if file_str in self.recent_files:
            self.recent_files.remove(file_str)
        
        # Add to front of list
        self.recent_files.insert(0, file_str)
        
        # Trim to max size
        if len(self.recent_files) > MAX_RECENT_FILES:
            self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        
        self.save()
        logger.info(f"Added to recent files: {file_path.name}")
    
    def get_all(self) -> List[Path]:
        """
        Get all recent files that still exist
        
        Returns:
            List of Path objects for existing files
        """
        existing_files = []
        removed_files = []
        
        for file_str in self.recent_files:
            file_path = Path(file_str)
            if file_path.exists():
                existing_files.append(file_path)
            else:
                removed_files.append(file_str)
        
        # Clean up non-existent files
        if removed_files:
            for file_str in removed_files:
                self.recent_files.remove(file_str)
            self.save()
            logger.info(f"Removed {len(removed_files)} non-existent files from recent list")
        
        return existing_files
    
    def clear(self) -> None:
        """Clear all recent files"""
        self.recent_files = []
        self.save()
        logger.info("Cleared recent files list")
    
    def remove(self, file_path: Path) -> bool:
        """
        Remove a specific file from recent files
        
        Args:
            file_path: Path to remove
            
        Returns:
            True if file was removed, False if not found
        """
        file_str = str(file_path.resolve())
        if file_str in self.recent_files:
            self.recent_files.remove(file_str)
            self.save()
            logger.info(f"Removed from recent files: {file_path.name}")
            return True
        return False


# Global recent files manager instance
_recent_files_manager: Optional[RecentFilesManager] = None


def get_recent_files_manager() -> RecentFilesManager:
    """Get or create global recent files manager instance"""
    global _recent_files_manager
    if _recent_files_manager is None:
        _recent_files_manager = RecentFilesManager()
    return _recent_files_manager
