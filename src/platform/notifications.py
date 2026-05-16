"""
src/platform/notifications.py
Cross-platform notification manager.
"""

import sys
import threading
import time
import queue
from typing import Dict, Any, Optional

try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    print("Warning: plyer not available. Notifications will be limited.")

from ..config import constants


class NotificationManager:
    """Cross-platform notification manager."""

    def __init__(self, app_name: str, window_getter=None, tray_manager_getter=None, logger=None):
        self.app_name = app_name
        self.window_getter = window_getter
        self.tray_manager_getter = tray_manager_getter
        self.logger = logger or self._get_default_logger()

        self._notification_queue = queue.Queue()
        self._running = False
        self._thread = None

    def _get_default_logger(self):
        import logging
        return logging.getLogger(__name__)

    def start(self):
        """Start notification manager."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._process_notifications,
            daemon=True
        )
        self._thread.start()
        self.logger.info("Notification manager started")

    def stop(self):
        """Stop notification manager."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.logger.info("Notification manager stopped")

    def _process_notifications(self):
        """Process notifications from queue."""
        while self._running:
            try:
                notification = self._notification_queue.get(timeout=0.5)
                if notification:
                    self._show_notification(notification)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error processing notification: {e}")

    def _show_notification(self, notification: Dict[str, Any]):
        """Show a single notification."""
        try:
            title = notification.get('title', self.app_name)
            message = notification.get('message', '')
            notification_type = notification.get('type', constants.NOTIFICATION_INFO)
            duration = notification.get('duration', 5)

            self.logger.info(f"📣 Delivering notification: [{title}] {message}")

            # Try tray notification on Windows first (more reliable than plyer)
            tray_success = False
            if sys.platform == "win32" and self.tray_manager_getter:
                try:
                    tray = self.tray_manager_getter()
                    if tray and hasattr(tray, 'notify'):
                        self.logger.debug("Using Tray notification method")
                        tray.notify(message, title)
                        tray_success = True
                    else:
                        self.logger.warning("Tray manager not available or has no notify() method")
                except Exception as e:
                    self.logger.error(f"Tray notification failed: {e}")

            # Platform-specific notification
            # On Windows, we only use Plyer if the Tray notification failed
            should_use_plyer = PLYER_AVAILABLE and self._should_use_plyer()
            if sys.platform == "win32" and tray_success:
                should_use_plyer = False

            if should_use_plyer:
                self.logger.debug(f"Using Plyer notification method")
                self._show_plyer_notification(title, message, duration)
            elif sys.platform != "win32" or not tray_success:
                self.logger.debug("Using Fallback notification method")
                self._show_fallback_notification(title, message, notification_type)

            # Also show in-app notification if window is available
            self._show_in_app_notification(title, message, notification_type)

        except Exception as e:
            self.logger.error(f"Failed to show notification: {e}")

    def _should_use_plyer(self):
        """Determine if plyer should be used for notifications."""
        # Plyer works well on Windows and macOS
        # On Linux, it depends on the desktop environment
        return PLYER_AVAILABLE and sys.platform in ['win32', 'darwin', 'linux']

    def _show_plyer_notification(self, title: str, message: str, duration: int):
        """Show notification using plyer."""
        try:
            plyer_notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                timeout=duration,
                app_icon=self._get_notification_icon()
            )
        except Exception as e:
            self.logger.error(f"Plyer notification failed: {e}")
            self._show_fallback_notification(title, message, constants.NOTIFICATION_INFO)

    def _show_fallback_notification(self, title: str, message: str, notification_type: str):
        """Show fallback notification (console or simple dialog)."""
        # Simple console output for debugging
        icon = self._get_notification_icon_char(notification_type)
        print(f"{icon} {title}: {message}")

    def _show_in_app_notification(self, title: str, message: str, notification_type: str):
        """Show notification within the application window."""
        if not self.window_getter:
            return

        try:
            window = self.window_getter()
            if window:
                js_code = f"""
                (function() {{
                    showInAppNotification("{title}", "{message}", "{notification_type}");
                }})();
                """
                window.evaluate_js(js_code)
        except Exception as e:
            # Silent fail - in-app notifications are optional
            pass

    def _get_notification_icon(self):
        """Get path to notification icon."""
        # Implement icon path logic based on platform
        return None

    def _get_notification_icon_char(self, notification_type: str) -> str:
        """Get icon character for notification type."""
        icons = {
            constants.NOTIFICATION_INFO: "ℹ️",
            constants.NOTIFICATION_WARNING: "⚠️",
            constants.NOTIFICATION_ERROR: "❌",
            constants.NOTIFICATION_SUCCESS: "✅",
            constants.NOTIFICATION_BREAK: "☕",
            constants.NOTIFICATION_CONNECTION: "🌐",
        }
        return icons.get(notification_type, "📢")

    def show_professional_notification(self, title: str, message: str,
                                       notification_type: str = constants.NOTIFICATION_INFO,
                                       duration: int = 5):
        """
        Show a professional notification.

        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification (info, warning, error, success, break, connection)
            duration: Duration in seconds
        """
        notification = {
            'title': title,
            'message': message,
            'type': notification_type,
            'duration': duration,
            'timestamp': time.time()
        }

        self._notification_queue.put(notification)
        self.logger.debug(f"Queued notification: {title} - {message}")

    # Convenience methods
    def show_info(self, title: str, message: str, duration: int = 5):
        """Show info notification."""
        self.show_professional_notification(title, message, constants.NOTIFICATION_INFO, duration)

    def show_warning(self, title: str, message: str, duration: int = 5):
        """Show warning notification."""
        self.show_professional_notification(title, message, constants.NOTIFICATION_WARNING, duration)

    def show_error(self, title: str, message: str, duration: int = 5):
        """Show error notification."""
        self.show_professional_notification(title, message, constants.NOTIFICATION_ERROR, duration)

    def show_success(self, title: str, message: str, duration: int = 5):
        """Show success notification."""
        self.show_professional_notification(title, message, constants.NOTIFICATION_SUCCESS, duration)

    def show_break_notification(self, title: str, message: str, duration: int = 5):
        """Show break notification."""
        self.show_professional_notification(title, message, constants.NOTIFICATION_BREAK, duration)

    def show_connection_notification(self, title: str, message: str, duration: int = 5):
        """Show connection notification."""
        self.show_professional_notification(title, message, constants.NOTIFICATION_CONNECTION, duration)