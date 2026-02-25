"""Integrity Verification for SMD"""

import hashlib
import logging
import struct
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Steam manifest magic bytes
MANIFEST_MAGIC = b'\x27\x44\x56\x01'  # Steam depot manifest signature


class IntegrityVerifier:
    """Verifies integrity of downloaded files"""
    
    @staticmethod
    def verify_file_size(file_path: Path, expected_size: Optional[int] = None) -> bool:
        """
        Verify file size matches expected size
        
        Args:
            file_path: Path to file
            expected_size: Expected file size in bytes (None to skip check)
            
        Returns:
            True if size matches or no expected size provided
        """
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
        """
        Verify manifest file has correct magic bytes
        
        Args:
            file_path: Path to manifest file
            
        Returns:
            True if magic bytes are correct
        """
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
        """
        Compute file checksum
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm (md5, sha1, sha256)
            
        Returns:
            Hex digest of checksum, or None on error
        """
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
        """
        Verify file checksum matches expected value
        
        Args:
            file_path: Path to file
            expected_checksum: Expected checksum hex string
            algorithm: Hash algorithm
            
        Returns:
            True if checksum matches
        """
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
        """
        Verify manifest file can be parsed (basic structure check)
        
        Args:
            file_path: Path to manifest file
            
        Returns:
            True if manifest appears valid
        """
        try:
            with file_path.open("rb") as f:
                # Check magic bytes
                magic = f.read(4)
                if magic != MANIFEST_MAGIC:
                    return False
                
                # Try to read some basic structure
                # This is a simplified check - full parsing would be more complex
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
        """
        Perform full manifest verification
        
        Args:
            file_path: Path to manifest file
            expected_size: Expected file size (optional)
            expected_checksum: Expected SHA256 checksum (optional)
            
        Returns:
            Tuple of (success, error_message)
        """
        # Check file exists
        if not file_path.exists():
            return False, f"File not found: {file_path}"
        
        # Check size
        if expected_size is not None:
            if not IntegrityVerifier.verify_file_size(file_path, expected_size):
                return False, "File size mismatch"
        
        # Check magic bytes
        if not IntegrityVerifier.verify_manifest_magic(file_path):
            return False, "Invalid manifest magic bytes"
        
        # Check if parseable
        if not IntegrityVerifier.verify_manifest_parseable(file_path):
            return False, "Manifest file is corrupted or invalid"
        
        # Check checksum
        if expected_checksum is not None:
            if not IntegrityVerifier.verify_checksum(file_path, expected_checksum):
                return False, "Checksum mismatch"
        
        logger.info(f"Manifest verification passed: {file_path.name}")
        return True, "Verification successful"
    
    @staticmethod
    def handle_verification_failure(file_path: Path, delete: bool = True) -> None:
        """
        Handle verification failure by deleting corrupted file
        
        Args:
            file_path: Path to corrupted file
            delete: Whether to delete the file
        """
        if delete:
            try:
                file_path.unlink(missing_ok=True)
                logger.warning(f"Deleted corrupted file: {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to delete corrupted file: {e}")
