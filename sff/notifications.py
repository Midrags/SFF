"""Windows Toast Notifications for SFF"""

import logging
import warnings
from enum import Enum
from typing import Optional

from sff.storage.settings import get_setting
from sff.structs import Settings

logger = logging.getLogger(__name__)

# Try to import notification library (always define ToastNotifier for test patching)
# Suppress pkg_resources deprecation from win10toast (build + runtime)
try:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*pkg_resources is deprecated.*",
            category=UserWarning,
        )
        from win10toast import ToastNotifier
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    ToastNotifier = None  # type: ignore[misc, assignment]
    NOTIFICATIONS_AVAILABLE = False
    logger.warning("win10toast not available. Notifications disabled.")


class NotificationType(Enum):
    """Types of notifications"""
    SUCCESS = "Success"
    ERROR = "Error"
    INFO = "Information"
    UPDATE = "Update Available"


class NotificationService:
    """Service for displaying Windows toast notifications"""
    
    def __init__(self):
        """Initialize the notification service"""
        self.toaster: Optional[ToastNotifier] = None
        self.enabled = True
        self.last_notification_time = 0
        self.notification_cooldown = 2  # seconds between notifications
        
        if NOTIFICATIONS_AVAILABLE:
            try:
                self.toaster = ToastNotifier()
            except Exception as e:
                logger.error(f"Failed to initialize ToastNotifier: {e}")
                self.enabled = False
    
    def is_enabled(self) -> bool:
        """Check if notifications are enabled in settings"""
        # For now, always return True if available
        # Can be extended to check Settings in the future
        return self.enabled and NOTIFICATIONS_AVAILABLE and self.toaster is not None
    
    def show(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        duration: int = 5
    ) -> bool:
        """
        Display a toast notification
        
        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            duration: Duration in seconds
            
        Returns:
            True if notification was shown, False otherwise
        """
        if not self.is_enabled():
            logger.debug(f"Notifications disabled. Would show: {title} - {message}")
            return False
        
        try:
            # Add icon based on notification type
            icon_path = None  # Can be extended to use custom icons
            
            # Wrap in try-except to catch pkg_resources errors
            try:
                self.toaster.show_toast(
                    title=f"SFF - {title}",
                    msg=message,
                    duration=duration,
                    icon_path=icon_path,
                    threaded=True
                )
                logger.info(f"Notification shown: {title}")
                return True
            except Exception as toast_error:
                # If pkg_resources error occurs, disable notifications and log
                if "pkg_resources" in str(toast_error) or "DistributionNotFound" in str(toast_error):
                    logger.warning(f"Disabling notifications due to pkg_resources error: {toast_error}")
                    self.enabled = False
                    return False
                else:
                    raise
            
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            # Disable notifications on any error to prevent repeated failures
            self.enabled = False
            return False
    
    def show_success(self, title: str, message: str) -> bool:
        """Show a success notification"""
        return self.show(title, message, NotificationType.SUCCESS)
    
    def show_error(self, title: str, message: str) -> bool:
        """Show an error notification"""
        return self.show(title, message, NotificationType.ERROR, duration=10)
    
    def show_info(self, title: str, message: str) -> bool:
        """Show an info notification"""
        return self.show(title, message, NotificationType.INFO)
    
    def show_update_available(self, version: str) -> bool:
        """Show an update available notification"""
        return self.show(
            "Update Available",
            f"Version {version} is available for download",
            NotificationType.UPDATE,
            duration=10
        )


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
