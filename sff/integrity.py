# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

"""Integrity Verification for SteaMidra"""

import hashlib
import logging
import struct
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Steam manifest magic bytes
MANIFEST_MAGIC = b'\x27\x44\x56\x01'  # Steam depot manifest signature


class IntegrityVerifier:
    
    @staticmethod
    def verify_file_size(file_path: Path, expected_size: Optional[int] = None) -> bool:
        if expected_size is None:
            return True
        
        try:
            actual_size = file_path.stat().st_size
            if actual_size != expected_size:
                logger.error(
                    f"Size mismatch for {file_path.name}: "
                    f"expected {expected_size}, got {actual_size}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to check file size: {e}")
            return False
    
    @staticmethod
    def verify_manifest_magic(file_path: Path) -> bool:
        try:
            with file_path.open("rb") as f:
                magic = f.read(4)
                if magic != MANIFEST_MAGIC:
                    logger.error(
                        f"Invalid manifest magic bytes in {file_path.name}: "
                        f"expected {MANIFEST_MAGIC.hex()}, got {magic.hex()}"
                    )
                    return False
            return True
        except Exception as e:
            logger.error(f"Failed to verify manifest magic: {e}")
            return False
    
    @staticmethod
    def compute_checksum(file_path: Path, algorithm: str = "sha256") -> Optional[str]:
        try:
            hash_obj = hashlib.new(algorithm)
            with file_path.open("rb") as f:
                while chunk := f.read(8192):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except Exception as e:
            logger.error(f"Failed to compute checksum: {e}")
            return None
    
    @staticmethod
    def verify_checksum(
        file_path: Path,
        expected_checksum: str,
        algorithm: str = "sha256"
    ) -> bool:
        actual_checksum = IntegrityVerifier.compute_checksum(file_path, algorithm)
        if actual_checksum is None:
            return False
        
        if actual_checksum.lower() != expected_checksum.lower():
            logger.error(
                f"Checksum mismatch for {file_path.name}: "
                f"expected {expected_checksum}, got {actual_checksum}"
            )
            return False
        
        return True
    
    @staticmethod
    def verify_manifest_parseable(file_path: Path) -> bool:
        try:
            with file_path.open("rb") as f:
                magic = f.read(4)
                if magic != MANIFEST_MAGIC:
                    return False
                
                # simplified check, full parsing would be more involved
                data = f.read(100)
                if len(data) < 20:
                    logger.error(f"Manifest file too small: {file_path.name}")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to parse manifest: {e}")
            return False
    
    @staticmethod
    def verify_manifest_full(
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_checksum: Optional[str] = None
    ) -> Tuple[bool, str]:
        if not file_path.exists():
            return False, f"File not found: {file_path}"
        
        if expected_size is not None:
            if not IntegrityVerifier.verify_file_size(file_path, expected_size):
                return False, "File size mismatch"
        
        if not IntegrityVerifier.verify_manifest_magic(file_path):
            return False, "Invalid manifest magic bytes"
        
        if not IntegrityVerifier.verify_manifest_parseable(file_path):
            return False, "Manifest file is corrupted or invalid"
        
        if expected_checksum is not None:
            if not IntegrityVerifier.verify_checksum(file_path, expected_checksum):
                return False, "Checksum mismatch"
        
        logger.info(f"Manifest verification passed: {file_path.name}")
        return True, "Verification successful"
    
    @staticmethod
    def handle_verification_failure(file_path: Path, delete: bool = True) -> None:
        if delete:
            try:
                file_path.unlink(missing_ok=True)
                logger.warning(f"Deleted corrupted file: {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to delete corrupted file: {e}")
