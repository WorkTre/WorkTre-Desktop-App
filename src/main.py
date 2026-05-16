"""
src/main.py
Main entry point for WorkTre Desktop Application - WITH MESSAGE QUEUE AND WINDOW SIZE TRACKING
"""

import sys
import os
import json
import threading
import time
import queue
import portalocker
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==================== FAST IMPORTS ====================
from src.config import settings, constants
from src.config.settings import APP_NAME, AssetPaths
from src.utils.logging import setup_logging
from src.utils.file_utils import get_local_version
from src.platform.utils import (
    create_single_instance_lock,
    cleanup_temp_files,
    get_app_data_dir,
    get_icon_path,
    force_window_to_top,
)
from src.ui.window import AppWindow

# Lazy imports
import importlib


class LazyLoader:
    """Lazy load modules to speed up startup."""

    @staticmethod
    def get_security():
        return importlib.import_module('src.utils.security')

    @staticmethod
    def get_notification():
        return importlib.import_module('src.platform.notifications')

    @staticmethod
    def get_tray():
        return importlib.import_module('src.platform.tray')

    @staticmethod
    def get_api():
        return importlib.import_module('src.api.soap_client')

    @staticmethod
    def get_managers():
        return {
            'inactivity': importlib.import_module('src.managers.inactivity'),
            'connectivity': importlib.import_module('src.managers.connectivity'),
            'system': importlib.import_module('src.managers.system'),
            'update': importlib.import_module('src.managers.update_manager'),
        }

    @staticmethod
    def get_dialogs():
        return importlib.import_module('src.ui.dialogs')

    @staticmethod
    def get_screenshot():
        return importlib.import_module('src.utils.screenshot')


# ==================== MESSAGE QUEUE SYSTEM ====================
class MessageQueue:
    """Simple message queue for Python -> JavaScript communication."""

    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()

    def add_message(self, message_type: str, data: dict):
        """Add a message to the queue."""
        with self.lock:
            self.messages.append({
                "type": message_type,
                "data": data,
                "timestamp": time.time()
            })
            # Keep only last 100 messages
            if len(self.messages) > 100:
                self.messages = self.messages[-100:]

    def get_messages(self, last_seen: float = 0):
        """Get messages since last_seen timestamp."""
        with self.lock:
            return [m for m in self.messages if m["timestamp"] > last_seen]

    def clear(self):
        """Clear all messages."""
        with self.lock:
            self.messages = []


# ==================== GLOBAL STATE ====================
class AppState:
    """Global application state."""

    def __init__(self):
        self.is_updating = False
        self.is_logged_in = False
        self.current_user = None
        self.user_info = None
        self.break_type = ""
        self.interval_running = False
        self.interval_timer = None
        self.interval_lock = threading.Lock()
        self.repeat_interval_seconds = 300
        self.restore_requested = False
        self.start_time = time.time()
        self.ui_ready = False
        self.last_activity_called = False

        # Message queue
        self.message_queue = MessageQueue()


# ==================== MAIN APPLICATION CLASS ====================
class WorkTreApp:
    """Main application class for WorkTre Desktop."""

    def __init__(self):
        """Initialize the application."""
        self.state = AppState()
        self.logger = None
        self.window = None
        self.tray_manager = None
        self.notification_manager = None
        self.api_client = None
        self.security_manager = None
        self.update_manager = None

        # Managers
        self.inactivity_manager = None
        self.connectivity_manager = None
        self.system_monitor = None

        # Application lifecycle
        self._running = True
        self.lock_file = None
        self.lock_handle = None

        # Lazy loaded modules
        self.lazy = LazyLoader()

        # Version
        self.app_version = get_local_version()
        settings.set_version(self.app_version)

        # Window size tracking
        self.original_width = constants.WINDOW_WIDTH
        self.original_height = constants.WINDOW_HEIGHT
        self.window_size_locked = False
        self._last_size_check = 0

        # Check for restore request
        self._check_restore_request()

    def _check_restore_request(self):
        """Check if app was launched with restore URL."""
        if len(sys.argv) > 1:
            for arg in sys.argv:
                if "worktre://restore" in arg:
                    self.state.restore_requested = True
                    break

    # ==================== WINDOW SIZE TRACKING ====================

    def init_window_tracking(self):
        """Initialize window size tracking"""
        if self.window and self.window.window:
            self.original_width = self.window.window.width
            self.original_height = self.window.window.height
            self.logger.info(f"Window size tracked: {self.original_width}x{self.original_height}")

    def lock_window_size(self):
        """Lock current window size to prevent changes"""
        self.window_size_locked = True
        if self.window and self.window.window:
            # Store current size
            self.original_width = self.window.window.width
            self.original_height = self.window.window.height
            self.logger.info(f"Window size locked: {self.original_width}x{self.original_height}")

    def unlock_window_size(self):
        """Unlock window size"""
        self.window_size_locked = False
        self.logger.info("Window size unlocked")

    def restore_window_size(self):
        """Restore original window size"""
        if self.window and self.window.window:
            try:
                self.window.window.resize(self.original_width, self.original_height)
                self.logger.info(f"Window size restored: {self.original_width}x{self.original_height}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to restore window size: {e}")
                return False
        return False

    def check_window_size(self):
        """Check if window size has changed and restore if needed"""
        if not self.window_size_locked or not self.window or not self.window.window:
            return

        current_time = time.time()
        # Only check every 2 seconds to avoid excessive calls
        if current_time - self._last_size_check < 2:
            return

        self._last_size_check = current_time

        try:
            current_width = self.window.window.width
            current_height = self.window.window.height

            if current_width != self.original_width or current_height != self.original_height:
                self.logger.warning(
                    f"Window size changed: {current_width}x{current_height} (expected: {self.original_width}x{self.original_height})")
                self.restore_window_size()
        except Exception as e:
            self.logger.error(f"Error checking window size: {e}")

    # ==================== FAST INITIALIZATION ====================

    def initialize(self) -> bool:
        """Initialize application - FAST PATH."""
        try:
            # 1. Setup logging (fast)
            self._setup_logging()
            self.logger.info(f"🚀 {APP_NAME} v{self.app_version} starting...")

            # 2. Check single instance (fast)
            if not self._check_single_instance():
                return False

            # 3. Setup directories (fast)
            self._setup_directories()

            # 4. Initialize UI FIRST - Show window ASAP
            self._initialize_ui_fast()

            self.logger.info("✅ Fast initialization complete")
            return True

        except Exception as e:
            if self.logger:
                self.logger.critical(f"Failed to initialize application: {e}", exc_info=True)
            else:
                print(f"CRITICAL: Failed to initialize application: {e}")
            return False

    def _setup_logging(self):
        """Setup application logging."""
        self.logger = setup_logging(APP_NAME, level="DEBUG")

    def _check_single_instance(self) -> bool:
        """Ensure only one instance is running."""
        locked, lock_file, lock_handle = create_single_instance_lock(APP_NAME)
        if not locked:
            self.logger.warning("Another instance is already running")
            if not self.state.restore_requested:
                dialogs = self.lazy.get_dialogs()
                dialogs.show_info_dialog(
                    "Already Running",
                    f"{APP_NAME} is already running.\n\nOnly one instance can run at a time."
                )
            return False

        self.lock_file = lock_file
        self.lock_handle = lock_handle # Store handle to keep lock alive
        return True

    def _setup_directories(self):
        """Create necessary directories."""
        app_data_dir = get_app_data_dir(APP_NAME)
        os.makedirs(app_data_dir, exist_ok=True)

    def _initialize_ui_fast(self):
        """Initialize UI FIRST - get window on screen quickly."""
        html_path = AssetPaths.get_html_path()

        # Create JSApi bridge
        js_api = JSApi(self)

        self.window = AppWindow(
            title=APP_NAME,
            html_path=str(html_path),
            api=js_api,
            width=constants.WINDOW_WIDTH,
            height=constants.WINDOW_HEIGHT
        )

        # Add loaded handler
        self.window.add_loaded_handler(self._on_window_loaded_fast)

        # Add closing handler
        self.window.add_closing_handler(self._on_window_closing)

        self.logger.info("UI initialized - window will show immediately")

    def _on_window_loaded_fast(self):
        """Fast window loaded handler - runs immediately when UI is ready."""
        self.logger.info("Window loaded - UI is now visible")
        self.state.ui_ready = True

        # Initialize window tracking
        self.init_window_tracking()

        # Start window size monitoring thread
        self._start_window_monitor()

        # Start background initialization
        self._start_background_initialization()

    def _start_window_monitor(self):
        """Start a background thread to monitor window size"""

        def monitor():
            while self._running:
                time.sleep(2)
                if not self._running:
                    break
                if self.state.is_logged_in and self.window_size_locked:
                    self.check_window_size()

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        self.logger.info("Window size monitor started")

    def _start_background_initialization(self):
        """Start all non-critical initialization in background threads."""
        self.logger.info("Starting background initialization...")

        # Start security in background
        threading.Thread(target=self._init_security_bg, daemon=True).start()

        # Start API in background
        threading.Thread(target=self._init_api_bg, daemon=True).start()

        # Start tray in background
        threading.Thread(target=self._init_tray_bg, daemon=True).start()

        # Start notification manager in background
        threading.Thread(target=self._init_notifications_bg, daemon=True).start()

        # Start managers in background
        threading.Thread(target=self._init_managers_bg, daemon=True).start()

        # Check for updates in background
        threading.Thread(target=self._check_updates_bg, daemon=True).start()

        # Load remembered credentials in background
        threading.Thread(target=self._load_credentials_bg, daemon=True).start()

        # Start login reminder thread
        threading.Thread(target=self._login_reminder_loop, daemon=True).start()

    def _init_security_bg(self):
        """Initialize security in background."""
        try:
            security = self.lazy.get_security()
            self.security_manager = security.SecurityManager(APP_NAME)
            self.logger.info("✅ Security manager initialized (bg)")
        except Exception as e:
            self.logger.error(f"Security init failed: {e}")

    def _init_api_bg(self):
        """Initialize API client in background."""
        try:
            api_module = self.lazy.get_api()
            self.api_client = api_module.SOAPClient(constants.SOAP_BASE_URL, self.logger)
            self.logger.info("✅ API client initialized (bg)")
        except Exception as e:
            self.logger.error(f"API init failed: {e}")

    def _init_tray_bg(self):
        """Initialize tray in background."""
        try:
            tray_module = self.lazy.get_tray()
            icon_path = get_icon_path("icon") or str(AssetPaths.get_icon_path())

            self.tray_manager = tray_module.create_tray_manager(
                app_name=APP_NAME,
                window_getter=lambda: self.window.window if self.window else None,
                icon_path=icon_path,
                logger=self.logger,
                is_updating_checker=lambda: self.state.is_updating,
                on_quit=self.quit
            )
            self.tray_manager.start()
            self.logger.info("✅ Tray manager initialized (bg)")
        except Exception as e:
            self.logger.error(f"Tray init failed: {e}")

    def _init_notifications_bg(self):
        """Initialize notification manager in background."""
        try:
            notif_module = self.lazy.get_notification()
            self.notification_manager = notif_module.NotificationManager(
                app_name=APP_NAME,
                window_getter=lambda: self.window.window if self.window else None,
                tray_manager_getter=lambda: self.tray_manager,
                logger=self.logger
            )
            self.notification_manager.start()
            self.logger.info("✅ Notification manager initialized (bg)")
        except Exception as e:
            self.logger.error(f"Notification init failed: {e}")

    def _init_managers_bg(self):
        """Initialize all managers in background."""
        try:
            managers = self.lazy.get_managers()

            # Inactivity manager
            self.inactivity_manager = managers['inactivity'].InactivityManager(self.logger)
            self.inactivity_manager.set_callbacks(
                on_warning=self._on_inactivity_warning,
                on_logout=self._on_inactivity_logout
            )

            # Connectivity manager
            self.connectivity_manager = managers['connectivity'].ConnectivityManager(self.logger)
            self.connectivity_manager.set_callbacks(
                on_online=self._on_network_online,
                on_offline=self._on_network_offline,
                on_timeout=self._on_disconnect_timeout
            )

            # System monitor
            self.system_monitor = managers['system'].SystemMonitor(self.logger)

            # Update manager
            self.update_manager = managers['update'].UpdateManager(
                logger=self.logger
            )

            self.logger.info("✅ All managers initialized (bg)")
        except Exception as e:
            self.logger.error(f"Managers init failed: {e}")

    def _check_updates_bg(self):
        """Check for updates in background."""
        try:
            # Wait a bit for UI to be ready
            time.sleep(2)

            if not self.update_manager:
                managers = self.lazy.get_managers()
                self.update_manager = managers['update'].UpdateManager(
                    logger=self.logger
                )

            result = self.update_manager.check_for_updates()

            if result.get("update_available"):
                # Add to message queue instead of direct evaluate_js
                self.state.message_queue.add_message("update_available", {
                    "latestVersion": result["latest_version"],
                    "currentVersion": result["current_version"],
                    "downloadUrl": result["download_url"],
                    "releaseNotes": result.get("release_notes", "")
                })
                self.logger.info(f"✅ Update available message queued")
        except Exception as e:
            self.logger.error(f"Update check failed: {e}")

    def _load_credentials_bg(self):
        """Load remembered credentials in background."""
        try:
            # Wait a bit for UI
            time.sleep(1.5)

            security = self.lazy.get_security()
            saved = security.get_remembered_user(APP_NAME)

            if saved:
                # Add to message queue instead of direct evaluate_js
                self.state.message_queue.add_message("auto_fill_credentials", saved)
                self.logger.info("✅ Credentials auto-fill queued")
        except Exception as e:
            self.logger.error(f"Credential load failed: {e}")

    # ==================== RUN ====================

    def run(self):
        """Run the application main loop."""
        try:
            self.logger.info("Starting application main loop")

            if self.window:
                # Run with debug=False for production
                self.window.run(debug=False)

        except KeyboardInterrupt:
            self.logger.info("Application interrupted by user")
            self.quit()
        except Exception as e:
            self.logger.critical(f"Application error: {e}", exc_info=True)
            dialogs = self.lazy.get_dialogs()
            dialogs.show_error_dialog(
                "Application Error",
                f"An unexpected error occurred:\n\n{str(e)}"
            )
            self.quit()

    # ==================== EVENT HANDLERS ====================

    def _on_window_closing(self):
        """Handle window closing event."""
        if self.state.is_logged_in:
            # If logged in, minimize to tray
            if self.tray_manager:
                self.tray_manager.minimize_to_tray(notify=True)
            return False  # Prevent window from destroying
        else:
            # If not logged in, prompt to quit
            dialogs = self.lazy.get_dialogs()
            confirmed = dialogs.show_confirmation_dialog(
                f"Quit {APP_NAME}",
                f"Are you sure you want to quit {APP_NAME}?"
            )
            if confirmed:
                self.logger.info("User confirmed quit via window cross")
                self._running = False
                return True  # Allow window to destroy
            return False  # Stay open

    def _login_reminder_loop(self):
        """Show a notification every 5 minutes if the user is not logged in."""
        last_reminder_time = 0
        self.logger.info("Login reminder loop started")
        
        while self._running:
            try:
                # Check every minute
                time.sleep(60)
                
                if not self._running:
                    break
                
                current_time = time.time()
                if not self.state.is_logged_in:
                    # Show first reminder after 1 min, then every 5 mins
                    if current_time - last_reminder_time >= 300:
                        self.logger.info("User not logged in - showing login reminder")
                        if self.notification_manager:
                            self.notification_manager.show_info(
                                "📢 WorkTre Login Reminder",
                                "Please login to WorkTre to track your activities and breaks.",
                                10 # Longer duration for visibility
                            )
                            last_reminder_time = current_time
                else:
                    # Reset timer when logged in so it shows 5 mins after logout
                    last_reminder_time = current_time - 240 # Will show 1 min after next logout
            except Exception as e:
                self.logger.error(f"Error in login reminder loop: {e}")
                time.sleep(60)

    def _on_inactivity_warning(self):
        """Handle inactivity warning."""
        self.logger.warning("Inactivity warning triggered")
        
        # Bring window to front with highest priority
        if self.window:
            try:
                self.window.show()
                self.window.restore()
                
                # Force to top on Windows
                if sys.platform == "win32" and self.window.window:
                    force_window_to_top(self.window.window.native_id)
                
                # Some platforms might need this to really grab focus
                self.window.evaluate_js("window.focus();")
            except Exception as e:
                self.logger.error(f"Failed to bring window to front: {e}")
        
        # Show notification
        if self.notification_manager:
            self.notification_manager.show_warning(
                "⏰ Inactivity Detected",
                "Are you still there? Activity monitoring paused.",
                5
            )
            
        self.state.message_queue.add_message("inactivity_warning", {})

    def _on_inactivity_logout(self):
        """Handle inactivity logout."""
        self.logger.warning("Inactivity logout triggered")
        
        # Bring window to front
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception:
                pass
                
        self.state.message_queue.add_message("inactivity_logout", {})

    def _on_network_online(self):
        """Handle network connection restored."""
        self.logger.info("Network connection restored")
        self.state.message_queue.add_message("network_online", {})
        if self.state.is_logged_in:
            self._start_service_interval()

    def _on_network_offline(self):
        """Handle network connection lost."""
        self.logger.warning("Network connection lost")
        self.state.message_queue.add_message("network_offline", {})
        self._stop_service_interval()

    def _on_disconnect_timeout(self):
        """Handle network disconnection timeout."""
        self.logger.warning("Network disconnection timeout triggered")
        self.state.message_queue.add_message("disconnect_logout", {})

    # ==================== AUTHENTICATION ====================

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login to WorkTre - Returns plain object."""
        try:
            import traceback
            print(f"🔐 JSApi.login called for user: {username}")

            # Ensure API client is initialized
            if not self.api_client:
                self.logger.info("API client not initialized, initializing now...")
                self._init_api_bg()
                time.sleep(0.5)

            response = self.api_client.login(username, password)
            print(f"📤 Login result from app: {response}")

            if response.get("status"):
                self.state.is_logged_in = True
                self.state.user_info = response.get("data", {})
                self.state.current_user = self.state.user_info.get("EID")
                self.logger.info(f"Login successful for user: {self.state.current_user}")
                
                # We intentionally DO NOT call _on_login_success() here anymore.
                # It is deferred to start_app_intervals to ensure the API sequence
                # (1-login -> 2-crashlogin -> 3-lastactivitydate -> 4-getservice) is preserved.

                # Lock window size after successful login
                self.lock_window_size()

            return response
        except Exception as e:
            if self.api_client:
                self.api_client.logger.error(f"Login API error: {e}")
            import traceback
            traceback.print_exc()
            return {"status": False, "msg": str(e)}

    def _get_safe_int(self, val: Any, default: int) -> int:
        try:
            return int(val) if val else default
        except (ValueError, TypeError):
            return default

    def _on_login_success(self, service_info: Optional[Dict[str, Any]] = None):
        """Handle successful login."""
        if not self.inactivity_manager:
            self._init_managers_bg()
            time.sleep(0.5)

        # Merge user_info and service_info for settings lookup
        settings_data = {}
        if self.state.user_info:
            settings_data.update(self.state.user_info)
            # Log available keys for debugging
            self.logger.info(f"Available user_info keys: {list(self.state.user_info.keys())}")
            
        if service_info:
            settings_data.update(service_info)
            self.logger.info(f"Available service_info keys: {list(service_info.keys())}")

        if settings_data:
            # Try multiple possible key names for inactivity settings
            warn_val = settings_data.get("InactivityBreakTime") or settings_data.get("inactivity_warn")
            logout_val = settings_data.get("InactivityBreakLogoutTime") or settings_data.get("inactivity_logout")
            
            warn_time = self._get_safe_int(warn_val, 15) * 60
            logout_time = self._get_safe_int(logout_val, 60) * 60
            
            self.logger.info(f"Inactivity settings - warn_time: {warn_time}s ({warn_time//60}m), logout_time: {logout_time}s ({logout_time//60}m)")

            self.inactivity_manager.set_timeouts(warn_time, logout_time)
            self.inactivity_manager.user_logged_in(True)
            self.inactivity_manager.start_monitoring()

        # Connectivity settings
        disconnect_val = settings_data.get("DisconnectLogoutTime") or settings_data.get("disconnect_timeout")
        disconnect_time = self._get_safe_int(disconnect_val, 15) * 60
        self.connectivity_manager.set_max_offline_time(disconnect_time)

        self.connectivity_manager.start_monitoring()

        # THIS STARTS THE SERVICE INTERVAL WHICH CALLS LAST ACTIVITY
        self._start_service_interval()

        # NOTE: Immediate lastactivitydate call has been removed from here.
        # It is now explicitly orchestrated by the JS client to guarantee
        # the sequence: login -> crashlogin -> lastactivitydate -> getservice.

    def logout(self, eod: str = "0", total_chats: str = "0",
               total_billable_chats: str = "0") -> Dict[str, Any]:
        """Logout current user."""
        if not self.state.is_logged_in or not self.state.current_user:
            return {"status": False, "msg": "Not logged in"}

        self.logger.info(f"Logging out user: {self.state.current_user}")

        response = self.api_client.logout(
            self.state.current_user,
            eod,
            total_chats,
            total_billable_chats
        )

        self.state.is_logged_in = False
        self.state.current_user = None
        self.state.user_info = None

        self._stop_service_interval()
        if self.inactivity_manager:
            self.inactivity_manager.stop_monitoring()
            self.inactivity_manager.user_logged_in(False)

        # Unlock window size after logout
        self.unlock_window_size()

        return response

    # ==================== SERVICE INTERVAL ====================

    def _start_service_interval(self, duration: int = 300):
        """Start the repeating service interval."""
        with self.state.interval_lock:
            if self.state.interval_running:
                return

            self.state.repeat_interval_seconds = duration
            self.state.interval_running = True
            self.state.interval_timer = threading.Timer(
                duration,
                self._on_interval_complete
            )
            self.state.interval_timer.start()
            self.logger.info(f"Service interval started ({duration}s)")

    def _stop_service_interval(self):
        """Stop the repeating service interval."""
        with self.state.interval_lock:
            if self.state.interval_timer:
                self.state.interval_timer.cancel()
                self.state.interval_timer = None
            self.state.interval_running = False

    def _on_interval_complete(self):
        """Handle service interval completion."""
        with self.state.interval_lock:
            self.state.interval_timer = None
            if self.state.interval_running and self.state.repeat_interval_seconds > 0:

                if self.state.is_logged_in and self.state.current_user and self.api_client:
                    # Only call if not already called very recently
                    current_time = time.time()
                    if not hasattr(self.state,
                                   '_last_activity_time') or current_time - self.state._last_activity_time > 60:
                        self.state._last_activity_time = current_time

                        self.api_client.last_activity_date(
                            self.state.current_user,
                            "False",
                            "",
                            ""
                        )

                        self.logger.debug(f"Last activity called at {current_time}")

                        if (self.state.user_info and
                                self.state.user_info.get("ScreenShotStatus") == "1"):
                            self._take_screenshot()

                self.state.interval_timer = threading.Timer(
                    self.state.repeat_interval_seconds,
                    self._on_interval_complete
                )
                self.state.interval_timer.start()

    def _take_screenshot(self):
        """Take and upload screenshot."""
        if not self.state.current_user:
            return

        def capture():
            try:
                screenshot = self.lazy.get_screenshot()
                screenshot.take_screenshot(self.state.current_user)
            except Exception as e:
                self.logger.error(f"Screenshot failed: {e}")

        threading.Thread(target=capture, daemon=True).start()

    # ==================== UTILITY METHODS ====================

    def get_app_version(self) -> str:
        """Get application version."""
        return self.app_version

    def quit(self):
        """Quit the application."""
        self.logger.info("Application quitting...")

        if self.inactivity_manager:
            self.inactivity_manager.stop_monitoring()
        if self.connectivity_manager:
            self.connectivity_manager.stop_monitoring()
        if self.system_monitor:
            self.system_monitor.stop_monitoring()
        if self.notification_manager:
            self.notification_manager.stop()
        if self.tray_manager:
            self.tray_manager.stop()

        self.cleanup()
        # Use os._exit(0) instead of sys.exit(0) to prevent pystray from catching 
        # the SystemExit exception and showing a scary traceback in the console.
        # This is safe because we have already called self.cleanup().
        os._exit(0)

    def cleanup(self):
        """Cleanup application resources."""
        self.logger.info("Cleaning up resources...")
        cleanup_temp_files(APP_NAME)

        if hasattr(self, 'lock_handle') and self.lock_handle:
            try:
                portalocker.unlock(self.lock_handle)
                self.lock_handle.close()
            except Exception:
                pass

        if hasattr(self, 'lock_file') and os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except Exception:
                pass


# ==================== JAVASCRIPT API BRIDGE ====================
class JSApi:
    """JavaScript API Bridge - NO COMPLEX OBJECTS RETURNED."""

    def __init__(self, app: WorkTreApp):
        self._app = app
        self._download_progress = 0
        self._download_error = None
        self._download_complete = False
        self._last_message_time = 0

    # ==================== MESSAGE QUEUE METHODS ====================

    def get_messages(self):
        """Get messages from the queue (called by JavaScript polling)."""
        try:
            messages = self._app.state.message_queue.get_messages(self._last_message_time)
            if messages:
                self._last_message_time = max(m["timestamp"] for m in messages)
            return messages
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []

    # ==================== WINDOW SIZE METHODS ====================

    def lock_window_size(self):
        """Lock current window size"""
        try:
            self._app.lock_window_size()
            return {"status": True}
        except Exception as e:
            print(f"Error locking window size: {e}")
            return {"status": False}

    def unlock_window_size(self):
        """Unlock window size"""
        try:
            self._app.unlock_window_size()
            return {"status": True}
        except Exception as e:
            print(f"Error unlocking window size: {e}")
            return {"status": False}

    def restore_window_size(self):
        """Restore original window size"""
        try:
            success = self._app.restore_window_size()
            return {"status": success}
        except Exception as e:
            print(f"Error restoring window size: {e}")
            return {"status": False}

    def get_window_size(self):
        """Get current window size"""
        try:
            if self._app.window and self._app.window.window:
                return {
                    "width": self._app.window.window.width,
                    "height": self._app.window.window.height,
                    "original_width": self._app.original_width,
                    "original_height": self._app.original_height,
                    "locked": self._app.window_size_locked
                }
            return {"width": 0, "height": 0, "original_width": self._app.original_width,
                    "original_height": self._app.original_height, "locked": self._app.window_size_locked}
        except Exception as e:
            print(f"Error getting window size: {e}")
            return {"error": str(e)}

    # ==================== NEW METHODS NEEDED BY UI ====================

    def start_app_intervals(self, user_data, service_data=None):
        """Start application intervals after successful login"""
        try:
            print(f"🔄 Starting app intervals for user: {user_data.get('EID')}")

            # Store user data in app state
            self._app.state.is_logged_in = True
            self._app.state.user_info = user_data
            self._app.state.current_user = user_data.get("EID")

            # Start all the intervals and monitoring
            self._app._on_login_success(service_data)

            # Lock window size after intervals start
            self._app.lock_window_size()

            return {"status": True, "message": "Intervals started"}
        except Exception as e:
            print(f"❌ Error starting intervals: {e}")
            return {"status": False, "message": str(e)}

    def crashlogin(self, eid, crash_reason, break_flag):
        """Handle crash login scenario"""
        try:
            print(f"🔄 Crash login for user: {eid}, reason: {crash_reason}")
            # This should call the appropriate API endpoint
            # You'll need to implement this in your api_client
            if hasattr(self._app.api_client, 'crash_login'):
                result = self._app.api_client.crash_login(eid, crash_reason, break_flag)
                return result
            else:
                # Mock response if not implemented
                return {"status": True, "data": {"Status": "Success"}}
        except Exception as e:
            print(f"❌ Crash login error: {e}")
            return {"status": False, "message": str(e)}

    def getservice(self, eid):
        """Get service data for user"""
        try:
            print(f"🔄 Getting service data for user: {eid}")

            # Call the actual API to get service data
            if hasattr(self._app.api_client, 'get_service'):
                result = self._app.api_client.get_service(eid)
                print(f"📊 Service data result: {result}")

                # Ensure result has the expected structure
                if result and result.get('status'):
                    return {
                        "status": True,
                        "data": result.get('data', {})
                    }
                else:
                    # Return default data structure if API fails
                    return {
                        "status": True,
                        "data": {
                            "8)- totalDuration": "0:00",
                            "3)- breakDetails": "",
                            "7)- ProfileImage": "",
                            "6)- timeIn": "",
                            "2)- totalBreakTime": "0"
                        }
                    }
            else:
                print("⚠️ get_service not implemented, returning mock data")
                # Mock response for testing - REMOVE THIS IN PRODUCTION
                return {
                    "status": True,
                    "data": {
                        "8)- totalDuration": "0:00",
                        "3)- breakDetails": "",
                        "7)- ProfileImage": "avatar-4.jpg",
                        "6)- timeIn": "09:57 am",
                        "2)- totalBreakTime": "0"
                    }
                }
        except Exception as e:
            print(f"❌ Get service error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "message": str(e),
                "data": {
                    "8)- totalDuration": "0:00",
                    "3)- breakDetails": "",
                    "7)- ProfileImage": "",
                    "6)- timeIn": "",
                    "2)- totalBreakTime": "0"
                }
            }

    def clear_app_data(self):
        """Clear application data on logout"""
        try:
            print("🔄 Clearing app data")
            self._app.state.is_logged_in = False
            self._app.state.current_user = None
            self._app.state.user_info = None

            # Unlock window size on logout
            self._app.unlock_window_size()

            return {"status": True}
        except Exception as e:
            print(f"❌ Clear app data error: {e}")
            return {"status": False}

    def resetInactivityTimer(self):
        """Reset the inactivity timer"""
        try:
            print("🔄 Resetting inactivity timer")
            if self._app.inactivity_manager:
                self._app.inactivity_manager.reset_timer()
            return {"status": True}
        except Exception as e:
            print(f"❌ Reset inactivity timer error: {e}")
            return {"status": False}

    def manually_call_lastInactivity(self, break_marked):
        """Manually call last activity"""
        try:
            print(f"🔄 Manually calling last activity, break marked: {break_marked}")
            if self._app.state.current_user and self._app.api_client:
                self._app._start_service_interval()
                if self._app.inactivity_manager:
                    self._app.inactivity_manager.reset_timer()
                self._app.api_client.last_activity_date(
                    self._app.state.current_user,
                    "False" if not break_marked else "True",
                    "",
                    ""
                )
            return {"status": True}
        except Exception as e:
            print(f"❌ Manual last activity error: {e}")
            return {"status": False}

    def maximize(self):
        """Maximize the window - DISABLED to prevent size changes"""
        try:
            print("⚠️ Maximize is disabled to maintain window size")
            # Return success but don't actually maximize
            return {"status": True, "message": "Maximize disabled"}
        except Exception as e:
            print(f"❌ Maximize error: {e}")
            return {"status": False}

    def inactivity(self, eid, reason):
        """Handle inactivity"""
        try:
            print(f"🔄 Inactivity for user: {eid}, reason: {reason}")
            # Check window size during inactivity
            self._app.check_window_size()
            if hasattr(self._app, 'api_client') and self._app.api_client:
                result = self._app.api_client.inactivity(eid, reason)
                
                # Show notification for inactivity detection
                if result.get("status") and self._app.notification_manager:
                    self._app.notification_manager.show_warning(
                        "⏰ Inactivity Detected",
                        "Activity monitoring paused.",
                        3
                    )
                return result
            return {"status": True}
        except Exception as e:
            print(f"❌ Inactivity error: {e}")
            return {"status": False, "msg": str(e)}

    def logoutinactivity(self, eid):
        """Handle logout due to inactivity"""
        try:
            print(f"🔄 Logout due to inactivity for user: {eid}")
            if hasattr(self._app, 'api_client') and self._app.api_client:
                result = self._app.api_client.logout_inactivity(eid)
                
                # Show notification
                if self._app.notification_manager:
                    self._app.notification_manager.show_warning(
                        "⏰ Inactivity Logout",
                        "You were logged out due to inactivity.",
                        5
                    )
                return result
            return {"status": True}
        except Exception as e:
            print(f"❌ Logout inactivity error: {e}")
            return {"status": False, "msg": str(e)}

    def requestforaccess(self, eid):
        """Request IP access"""
        try:
            print(f"🔄 Requesting access for user: {eid}")
            if hasattr(self._app.api_client, 'request_access'):
                result = self._app.api_client.request_access(eid)
                return json.dumps(result)
            else:
                mock_data = {"ip": "192.168.1.100"}
                return json.dumps({"status": True, "data": mock_data})
        except Exception as e:
            print(f"❌ Request access error: {e}")
            return json.dumps({"status": False, "message": str(e)})

    # ==================== UPDATE METHODS ====================

    def downloadUpdate(self, url, version):
        """Download and install update."""
        try:
            print(f"📥 ===== DOWNLOAD UPDATE CALLED =====")
            print(f"📥 URL: {url}")
            print(f"📥 Version: {version}")

            self._app.logger.info(f"Starting download for version {version}")

            from src.managers.update_manager import UpdateManager

            def progress_callback(percentage):
                """Store progress for polling."""
                self._download_progress = percentage
                print(f"📊 Progress: {percentage}%")

            def download_thread():
                try:
                    manager = UpdateManager(logger=self._app.logger)
                    success = manager.download_update(url, version, progress_callback)

                    if not success:
                        print("❌ Download failed")
                        self._download_error = "Download failed. Please check your internet connection."
                        return

                    print("✅ Download successful, installing...")

                    self._app.state.is_updating = True
                    install_success = manager.install_update()

                    if install_success:
                        print("✅ Installation started, exiting app...")
                        self._download_complete = True
                        time.sleep(1)
                        self._app.quit()
                    else:
                        print("❌ Installation failed")
                        self._download_error = "Installation failed"

                except Exception as e:
                    print(f"❌ Download thread error: {e}")
                    self._download_error = str(e)

            threading.Thread(target=download_thread, daemon=True).start()
            return {"status": True, "message": "Download started"}

        except Exception as e:
            print(f"❌ downloadUpdate error: {e}")
            return {"status": False, "message": str(e)}

    def get_download_status(self):
        """Polling method for JavaScript to get download status."""
        return {
            "progress": self._download_progress,
            "error": self._download_error,
            "complete": self._download_complete
        }

    def check_for_updates_manual(self):
        """Manually check for updates."""
        try:
            from src.managers.update_manager import UpdateManager
            manager = UpdateManager(logger=self._app.logger)
            result = manager.check_for_updates()

            if result.get("update_available"):
                return {
                    "status": True,
                    "update_available": True,
                    "latestVersion": result["latest_version"],
                    "currentVersion": result["current_version"],
                    "downloadUrl": result["download_url"],
                    "releaseNotes": result.get("release_notes", "")
                }
            else:
                return {
                    "status": True,
                    "update_available": False,
                    "message": "No updates available"
                }

        except Exception as e:
            self._app.logger.error(f"Manual update check failed: {e}")
            return {"status": False, "error": str(e)}

    # ==================== AUTHENTICATION METHODS ====================

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login to WorkTre - Returns plain object."""
        try:
            print(f"🔐 JSApi.login called for user: {username}")
            result = self._app.login(username, password)
            print(f"📤 Login result from app: {result}")

            # Lock window size after successful login
            if result.get("status"):
                self._app.lock_window_size()

            return result
        except Exception as e:
            self._app.logger.error(f"Login API error: {e}")
            import traceback
            traceback.print_exc()
            return {"status": False, "msg": str(e)}

    def logout(self, eid: str = "", eod: str = "0", total_chats: str = "0", total_billable_chats: str = "0") -> Dict[str, Any]:
        """Logout from WorkTre."""
        try:
            result = self._app.logout(eod, total_chats, total_billable_chats)

            # Unlock window size after logout
            self._app.unlock_window_size()

            return result
        except Exception as e:
            self._app.logger.error(f"Logout API error: {e}")
            return {"status": False, "msg": str(e)}

    def get_remembered_user(self) -> Dict[str, Any]:
        """Get remembered user credentials."""
        try:
            security = self._app.lazy.get_security()
            saved = security.get_remembered_user(APP_NAME)
            return saved or {}
        except Exception as e:
            self._app.logger.error(f"Get remembered user error: {e}")
            return {}

    def save_remembered_user(self, email: str, password: str) -> Dict[str, Any]:
        """Save remembered user credentials."""
        try:
            security = self._app.lazy.get_security()
            security.save_remembered_user(email, password, APP_NAME)
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Save remembered user error: {e}")
            return {"status": False, "error": str(e)}

    def show_login_success_notification(self, username: str) -> Dict[str, Any]:
        """Show login success notification."""
        try:
            if self._app.notification_manager:
                self._app.notification_manager.show_success(
                    "✅ Login Successful",
                    f"{username}, Welcome back!",
                    3
                )
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Notification error: {e}")
            return {"status": False}

    def show_logout_notification(self, username: str) -> Dict[str, Any]:
        """Show logout notification."""
        try:
            if self._app.notification_manager:
                self._app.notification_manager.show_success(
                    "✅ Logout Successful",
                    f"{username}, Goodbye!",
                    3
                )
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Logout notification error: {e}")
            return {"status": False}

    # ==================== BREAK MANAGEMENT ====================

    def breakin(self, eid: str, break_type: str, comments: str = "", **kwargs) -> Dict[str, Any]:
        """Start a break."""
        try:
            if not self._app.state.is_logged_in:
                return {"status": False, "msg": "Not logged in"}

            result = self._app.api_client.breakin(
                eid,
                break_type,
                comments,
                **kwargs
            )

            # Check status robustly (True or "True")
            status = result.get("status")
            if status is True or str(status).lower() == "true":
                self._app.state.break_type = break_type
                if self._app.inactivity_manager:
                    self._app.inactivity_manager.stop_monitoring()
                
                # Show notification
                if self._app.notification_manager:
                    formatted_type = break_type.replace("_", " ").title()
                    self._app.notification_manager.show_break_notification(
                        "☕ Break Started",
                        f"You are now on {formatted_type} break.",
                        3
                    )

            return result
        except Exception as e:
            self._app.logger.error(f"Start break error: {e}")
            return {"status": False, "msg": str(e)}

    def breakout(self, eid: str, break_type: str, comments: str = "", inactivity: bool = False) -> Dict[str, Any]:
        """End a break."""
        try:
            print(f"🔄 breakout called - eid: {eid}, break_type: {break_type}, inactivity: {inactivity}")

            if not self._app.state.is_logged_in:
                return {"status": False, "msg": "Not logged in"}

            result = self._app.api_client.breakout(
                eid,
                break_type,
                comments
            )

            # Check status robustly (True or "True")
            status = result.get("status")
            if status is True or str(status).lower() == "true":
                self._app.state.break_type = ""
            
            # ALWAYS resume monitoring when breakout is called
            if self._app.inactivity_manager:
                self._app.inactivity_manager.reset_timer()
                self._app.inactivity_manager.start_monitoring()

            # ALWAYS show notification when breakout is called, 
            # as the UI has already transitioned the user back to work.
            if self._app.notification_manager:
                msg = "Welcome back! Activity monitoring resumed."
                if inactivity or break_type == "inactivity":
                    msg = "Inactivity break ended. Welcome back!"
                
                self._app.logger.info(f"Showing breakout notification: {msg}")
                self._app.notification_manager.show_success(
                    "✅ Break Ended",
                    msg,
                    5
                )

            # Log success
            print(f"✅ Breakout successful for user {eid}")

            return result
        except Exception as e:
            self._app.logger.error(f"End break error: {e}")
            import traceback
            traceback.print_exc()
            return {"status": False, "msg": str(e)}

    def getBreakTypes(self, eid: str) -> list:
        """Get available break types."""
        try:
            if not self._app.state.is_logged_in:
                return []
            response = self._app.api_client.get_break_types(eid)
            print(f"📊 break types api response: {response}")
            return response.get("data", {}).get("break_types", [])
        except Exception as e:
            self._app.logger.error(f"Get break types error: {e}")
            return []

    # ==================== ACTIVITY METHODS ====================

    def reset_inactivity_timer(self) -> Dict[str, Any]:
        """Reset inactivity timer."""
        try:
            if self._app.inactivity_manager:
                self._app.inactivity_manager.reset_timer()
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Reset timer error: {e}")
            return {"status": False}

    def manually_call_last_activity(self, break_flag: str = "False") -> Dict[str, Any]:
        """Manually call last activity."""
        try:
            print(f"🔄 manually_call_last_activity called with break_flag: {break_flag}")

            # Add debounce
            current_time = time.time()
            if hasattr(self, '_last_manual_call'):
                time_diff = current_time - self._last_manual_call
                if time_diff < 30:  # 30 second debounce
                    print(f"⚠️ Skipping manual last activity call (only {time_diff:.1f}s since last)")
                    return {"status": True, "message": "Skipped (debounce)"}

            self._last_manual_call = current_time

            if self._app.state.current_user and self._app.api_client:
                self._app._start_service_interval()
                if self._app.inactivity_manager:
                    self._app.inactivity_manager.reset_timer()
                self._app.api_client.last_activity_date(
                    self._app.state.current_user,
                    break_flag,
                    "",
                    ""
                )
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Last activity error: {e}")
            return {"status": False}

    # ==================== VERSION METHODS ====================

    def get_app_version(self) -> str:
        """Get application version."""
        try:
            return self._app.get_app_version()
        except Exception as e:
            self._app.logger.error(f"Get version error: {e}")
            return "1.0.1"

    # ==================== SYSTEM METHODS ====================

    def get_system_status(self) -> Dict[str, Any]:
        """Get system status."""
        try:
            status = {
                "app": {
                    "name": APP_NAME,
                    "version": self._app.app_version,
                    "uptime": time.time() - self._app.state.start_time
                },
                "user": {
                    "logged_in": self._app.state.is_logged_in,
                    "current_user": self._app.state.current_user,
                    "on_break": bool(self._app.state.break_type),
                    "break_type": self._app.state.break_type
                },
                "window": {
                    "width": self._app.window.window.width if self._app.window and self._app.window.window else 0,
                    "height": self._app.window.window.height if self._app.window and self._app.window.window else 0,
                    "original_width": self._app.original_width,
                    "original_height": self._app.original_height,
                    "locked": self._app.window_size_locked
                }
            }

            if self._app.connectivity_manager:
                status["network"] = {
                    "online": self._app.connectivity_manager.is_online()
                }

            if self._app.system_monitor:
                status["system"] = self._app.system_monitor.get_resource_usage()

            return status
        except Exception as e:
            self._app.logger.error(f"System status error: {e}")
            return {"error": str(e)}

    def request_access(self) -> Dict[str, Any]:
        """Request access."""
        try:
            if self._app.state.current_user and self._app.api_client:
                return self._app.api_client.request_access(self._app.state.current_user)
            return {"status": False, "msg": "Not logged in"}
        except Exception as e:
            self._app.logger.error(f"Request access error: {e}")
            return {"status": False, "msg": str(e)}

    def handle_forget_password(self, email: str) -> Dict[str, Any]:
        """Handle forgot password."""
        try:
            self._app.logger.info(f"Forgot password requested for: {email}")
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Forgot password error: {e}")
            return {"status": False}

    # ==================== APPLICATION METHODS ====================

    def set_topmost(self, topmost: bool = True) -> Dict[str, Any]:
        """Set or unset the window as topmost."""
        try:
            if sys.platform == "win32" and self._app.window and self._app.window.window:
                force_window_to_top(self._app.window.window.native_id, topmost)
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Set topmost error: {e}")
            return {"status": False}

    def close_app(self) -> Dict[str, Any]:
        """Close the application."""
        try:
            self._app.quit()
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Close app error: {e}")
            return {"status": False}

    def minimize_to_tray(self) -> Dict[str, Any]:
        """Minimize to tray."""
        try:
            if self._app.tray_manager:
                self._app.tray_manager.minimize_to_tray(notify=True)
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Minimize to tray error: {e}")
            return {"status": False}

    def restore_window(self) -> Dict[str, Any]:
        """Restore window."""
        try:
            if self._app.window:
                self._app.window.restore()
                self._app.window.bring_to_front()
                # Also restore size
                self._app.restore_window_size()
            return {"status": True}
        except Exception as e:
            self._app.logger.error(f"Restore window error: {e}")
            return {"status": False}


# ==================== ENTRY POINT ====================
def main():
    """Main entry point."""
    app = WorkTreApp()

    if app.initialize():
        app.run()
        # After app.run() returns (window closed and allowed to destroy), 
        # perform final cleanup.
        app.cleanup()
    else:
        print("❌ Failed to initialize application")
        sys.exit(1)


if __name__ == "__main__":
    main()
