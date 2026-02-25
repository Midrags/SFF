"""Local Analytics Tracking for SMD"""

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from smd.utils import root_folder

logger = logging.getLogger(__name__)

ANALYTICS_FILE = root_folder(outside_internal=True) / "analytics.json"


@dataclass
class OperationRecord:
    timestamp: float
    operation_type: str
    app_id: Optional[int] = None
    success: bool = True
    duration: float = 0.0
    error_message: Optional[str] = None


@dataclass
class AnalyticsData:
    operations: List[OperationRecord] = field(default_factory=list)
    total_downloads: int = 0
    total_successes: int = 0
    total_failures: int = 0
    feature_usage: Dict[str, int] = field(default_factory=dict)


class AnalyticsTracker:
    """Tracks local usage statistics (no network transmission)"""
    
    def __init__(self):
        self.data = AnalyticsData()
        self.load()
    
    def load(self) -> None:
        try:
            if ANALYTICS_FILE.exists():
                with ANALYTICS_FILE.open("r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    self.data.operations = [
                        OperationRecord(**op) for op in raw_data.get("operations", [])
                    ]
                    self.data.total_downloads = raw_data.get("total_downloads", 0)
                    self.data.total_successes = raw_data.get("total_successes", 0)
                    self.data.total_failures = raw_data.get("total_failures", 0)
                    self.data.feature_usage = raw_data.get("feature_usage", {})
                logger.debug(f"Loaded analytics: {len(self.data.operations)} operations")
        except Exception as e:
            logger.error(f"Failed to load analytics: {e}", exc_info=True)
            self.data = AnalyticsData()
    
    def save(self) -> None:
        try:
            raw_data = {
                "operations": [
                    {
                        "timestamp": op.timestamp,
                        "operation_type": op.operation_type,
                        "app_id": op.app_id,
                        "success": op.success,
                        "duration": op.duration,
                        "error_message": op.error_message
                    }
                    for op in self.data.operations
                ],
                "total_downloads": self.data.total_downloads,
                "total_successes": self.data.total_successes,
                "total_failures": self.data.total_failures,
                "feature_usage": self.data.feature_usage
            }
            with ANALYTICS_FILE.open("w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2)
            logger.debug("Saved analytics data")
        except Exception as e:
            logger.error(f"Failed to save analytics: {e}", exc_info=True)
    
    def record_operation(
        self,
        operation_type: str,
        app_id: Optional[int] = None,
        success: bool = True,
        duration: float = 0.0,
        error_message: Optional[str] = None
    ) -> None:
        record = OperationRecord(
            timestamp=time.time(),
            operation_type=operation_type,
            app_id=app_id,
            success=success,
            duration=duration,
            error_message=error_message
        )
        self.data.operations.append(record)
        if operation_type == "download":
            self.data.total_downloads += 1
        if success:
            self.data.total_successes += 1
        else:
            self.data.total_failures += 1
        self.save()
        logger.info(f"Recorded operation: {operation_type} (success={success})")
    
    def record_feature_usage(self, feature_name: str) -> None:
        if feature_name not in self.data.feature_usage:
            self.data.feature_usage[feature_name] = 0
        self.data.feature_usage[feature_name] += 1
        self.save()
        logger.debug(f"Recorded feature usage: {feature_name}")
    
    def get_most_downloaded_games(self, limit: int = 10) -> List[tuple]:
        app_ids = [
            op.app_id for op in self.data.operations
            if op.app_id is not None and op.operation_type == "download"
        ]
        counter = Counter(app_ids)
        return counter.most_common(limit)
    
    def get_success_rate(self) -> float:
        total = self.data.total_successes + self.data.total_failures
        if total == 0:
            return 0.0
        return (self.data.total_successes / total) * 100
    
    def get_average_duration(self, operation_type: Optional[str] = None) -> float:
        operations = self.data.operations
        if operation_type:
            operations = [op for op in operations if op.operation_type == operation_type]
        if not operations:
            return 0.0
        total_duration = sum(op.duration for op in operations)
        return total_duration / len(operations)
    
    def get_feature_usage_stats(self) -> Dict[str, int]:
        return dict(self.data.feature_usage)
    
    def export_to_json(self, output_path: Path) -> bool:
        try:
            export_data = {
                "summary": {
                    "total_operations": len(self.data.operations),
                    "total_downloads": self.data.total_downloads,
                    "total_successes": self.data.total_successes,
                    "total_failures": self.data.total_failures,
                    "success_rate": f"{self.get_success_rate():.2f}%",
                    "average_duration": f"{self.get_average_duration():.2f}s"
                },
                "most_downloaded_games": [
                    {"app_id": app_id, "count": count}
                    for app_id, count in self.get_most_downloaded_games()
                ],
                "feature_usage": self.get_feature_usage_stats(),
                "operations": [
                    {
                        "timestamp": op.timestamp,
                        "operation_type": op.operation_type,
                        "app_id": op.app_id,
                        "success": op.success,
                        "duration": op.duration
                    }
                    for op in self.data.operations
                ]
            }
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            logger.info(f"Analytics exported to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export analytics: {e}", exc_info=True)
            return False
    
    def generate_dashboard_text(self) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append("SFF Analytics Dashboard")
        lines.append("=" * 80)
        lines.append(f"\nTotal Operations: {len(self.data.operations)}")
        lines.append(f"Total Downloads: {self.data.total_downloads}")
        lines.append(f"Success Rate: {self.get_success_rate():.2f}%")
        lines.append(f"Average Duration: {self.get_average_duration():.2f}s")
        
        most_downloaded = self.get_most_downloaded_games(5)
        if most_downloaded:
            lines.append("\n" + "=" * 80)
            lines.append("Most Downloaded Games:")
            lines.append("=" * 80)
            for app_id, count in most_downloaded:
                lines.append(f"  App ID {app_id}: {count} downloads")
        
        feature_stats = self.get_feature_usage_stats()
        if feature_stats:
            lines.append("\n" + "=" * 80)
            lines.append("Feature Usage:")
            lines.append("=" * 80)
            for feature, count in sorted(feature_stats.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {feature}: {count} times")
        
        return "\n".join(lines)


_analytics_tracker: Optional[AnalyticsTracker] = None


def get_analytics_tracker() -> AnalyticsTracker:
    global _analytics_tracker
    if _analytics_tracker is None:
        _analytics_tracker = AnalyticsTracker()
    return _analytics_tracker
