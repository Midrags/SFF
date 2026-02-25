"""Validation utilities for DLC unlocker operations."""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def validate_game_directory(game_dir: Path) -> Tuple[bool, Optional[str]]:
    if not game_dir.exists():
        return False, f"Game directory does not exist: {game_dir}"
    
    if not game_dir.is_dir():
        return False, f"Path is not a directory: {game_dir}"
    
    # Check read permissions
    try:
        os.access(game_dir, os.R_OK)
    except Exception as e:
        return False, f"Cannot read game directory: {e}"
    
    return True, None


def validate_write_permissions(directory: Path) -> Tuple[bool, Optional[str]]:
    if not directory.exists():
        return False, f"Directory does not exist: {directory}"
    
    try:
        # Try to create a test file
        test_file = directory / ".sff_write_test"
        test_file.write_text("test")
        test_file.unlink()
        return True, None
    except PermissionError:
        return False, f"No write permission for directory: {directory}"
    except Exception as e:
        return False, f"Cannot write to directory: {e}"


def check_disk_space(directory: Path, required_bytes: int = 10 * 1024 * 1024) -> Tuple[bool, Optional[str]]:
    try:
        stat = shutil.disk_usage(directory)
        free_space = stat.free
        
        if free_space < required_bytes:
            return False, f"Insufficient disk space: {free_space / 1024 / 1024:.1f}MB free, {required_bytes / 1024 / 1024:.1f}MB required"
        
        return True, None
    except Exception as e:
        logger.warning(f"Could not check disk space: {e}")
        return True, None  # Assume OK if check fails


def validate_dll_file(dll_path: Path) -> Tuple[bool, Optional[str]]:
    if not dll_path.exists():
        return False, f"DLL file does not exist: {dll_path}"
    
    if not dll_path.is_file():
        return False, f"Path is not a file: {dll_path}"
    
    try:
        # Check if file is readable
        with dll_path.open("rb") as f:
            f.read(1)
        return True, None
    except PermissionError:
        return False, f"No read permission for DLL: {dll_path}"
    except Exception as e:
        return False, f"Cannot read DLL file: {e}"


def validate_app_id(app_id: int) -> Tuple[bool, Optional[str]]:
    if app_id <= 0:
        return False, f"Invalid App ID: {app_id} (must be positive)"
    
    if app_id > 2147483647:  # Max 32-bit signed int
        return False, f"App ID too large: {app_id}"
    
    return True, None


def validate_dlc_ids(dlc_ids: list[int]) -> Tuple[bool, Optional[str]]:
    if not isinstance(dlc_ids, list):
        return False, f"DLC IDs must be a list, got {type(dlc_ids)}"
    
    for dlc_id in dlc_ids:
        if not isinstance(dlc_id, int):
            return False, f"DLC ID must be int, got {type(dlc_id)}: {dlc_id}"
        if dlc_id <= 0:
            return False, f"Invalid DLC ID: {dlc_id} (must be positive)"
        if dlc_id > 2147483647:
            return False, f"DLC ID too large: {dlc_id}"
    
    return True, None


def check_file_in_use(file_path: Path) -> Tuple[bool, Optional[str]]:
    if not file_path.exists():
        return False, None  # Not in use if doesn't exist
    
    import sys
    if sys.platform != "win32":
        return False, None  # Only check on Windows
    
    try:
        # Try to open file in exclusive mode
        with file_path.open("r+b"):
            return False, None  # File is not locked
    except PermissionError:
        return True, f"File is locked (may be in use): {file_path}"
    except Exception:
        return False, None  # Assume OK if check fails
