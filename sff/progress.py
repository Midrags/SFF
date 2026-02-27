"""Enhanced Progress Indicators for SteaMidra"""

import logging
import time
from typing import Optional

from tqdm import tqdm

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Enhanced progress tracking with ETA and speed indicators"""
    
    def __init__(
        self,
        total: int,
        desc: str = "Processing",
        unit: str = "it",
        unit_scale: bool = False
    ):
        """
        Initialize progress tracker
        
        Args:
            total: Total number of items to process
            desc: Description of the operation
            unit: Unit name for items
            unit_scale: Whether to scale units (e.g., KB, MB)
        """
        self.total = total
        self.desc = desc
        self.unit = unit
        self.start_time = time.time()
        
        # Create tqdm progress bar with enhanced features
        self.pbar = tqdm(
            total=total,
            desc=desc,
            unit=unit,
            unit_scale=unit_scale,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
            ncols=100
        )
    
    def update(self, n: int = 1) -> None:
        """
        Update progress by n items
        
        Args:
            n: Number of items completed
        """
        self.pbar.update(n)
    
    def set_description(self, desc: str) -> None:
        """
        Update the progress description
        
        Args:
            desc: New description
        """
        self.pbar.set_description(desc)
    
    def close(self) -> None:
        """Close the progress bar"""
        self.pbar.close()
        elapsed = time.time() - self.start_time
        logger.info(f"{self.desc} completed in {elapsed:.2f}s")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class SpinnerProgress:
    """Indeterminate progress indicator (spinner)"""
    
    def __init__(self, desc: str = "Processing"):
        """
        Initialize spinner
        
        Args:
            desc: Description of the operation
        """
        self.desc = desc
        self.pbar = tqdm(
            desc=desc,
            bar_format='{desc}: {elapsed}',
            ncols=100
        )
    
    def update_description(self, desc: str) -> None:
        """Update spinner description"""
        self.pbar.set_description(desc)
    
    def close(self) -> None:
        """Close the spinner"""
        self.pbar.close()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def create_progress_bar(
    total: int,
    desc: str = "Processing",
    unit: str = "it",
    unit_scale: bool = False
) -> ProgressTracker:
    """
    Create a progress bar with enhanced features
    
    Args:
        total: Total number of items
        desc: Description
        unit: Unit name
        unit_scale: Whether to scale units
        
    Returns:
        ProgressTracker instance
    """
    return ProgressTracker(total, desc, unit, unit_scale)


def create_spinner(desc: str = "Processing") -> SpinnerProgress:
    """
    Create an indeterminate progress spinner
    
    Args:
        desc: Description
        
    Returns:
        SpinnerProgress instance
    """
    return SpinnerProgress(desc)
