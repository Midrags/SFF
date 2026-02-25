"""Progress Indicators for SFF"""

import logging
import time
from typing import Optional

from tqdm import tqdm

logger = logging.getLogger(__name__)


class ProgressTracker:
    def __init__(
        self,
        total: int,
        desc: str = "Processing",
        unit: str = "it",
        unit_scale: bool = False
    ):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.start_time = time.time()
        self.pbar = tqdm(
            total=total,
            desc=desc,
            unit=unit,
            unit_scale=unit_scale,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
            ncols=100
        )
    
    def update(self, n: int = 1) -> None:
        self.pbar.update(n)
    
    def set_description(self, desc: str) -> None:
        self.pbar.set_description(desc)
    
    def close(self) -> None:
        self.pbar.close()
        elapsed = time.time() - self.start_time
        logger.info(f"{self.desc} completed in {elapsed:.2f}s")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SpinnerProgress:
    def __init__(self, desc: str = "Processing"):
        self.desc = desc
        self.pbar = tqdm(
            desc=desc,
            bar_format='{desc}: {elapsed}',
            ncols=100
        )
    
    def update_description(self, desc: str) -> None:
        self.pbar.set_description(desc)
    
    def close(self) -> None:
        self.pbar.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_progress_bar(
    total: int,
    desc: str = "Processing",
    unit: str = "it",
    unit_scale: bool = False
) -> ProgressTracker:
    return ProgressTracker(total, desc, unit, unit_scale)


def create_spinner(desc: str = "Processing") -> SpinnerProgress:
    return SpinnerProgress(desc)
