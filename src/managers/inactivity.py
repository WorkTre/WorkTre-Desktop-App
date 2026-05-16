"""
src/managers/inactivity.py
Inactivity manager for tracking user activity.
"""

import threading
import time
import sys
from typing import Optional, Callable
from datetime import datetime

from ..config import constants


class InactivityManager:
    """Manager for tracking user inactivity."""

    def __init__(self, logger=None):
        self.logger = logger or self._get_default_logger()
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

        # Callbacks
        self._on_warning: Optional[Callable] = None
        self._on_logout: Optional[Callable] = None

        # Timeouts (in seconds)
        self._warning_timeout = constants.DEFAULT_INACTIVITY_WARN
        self._logout_timeout = constants.DEFAULT_INACTIVITY_LOGOUT

        # State
        self._last_activity = time.time()
        self._warning_triggered = False
        self._warning_time = 0.0
        self._user_logged_in = False

    def _get_default_logger(self):
        import logging
        return logging.getLogger(__name__)

    def _get_idle_time(self) -> float:
        """Get system idle time."""
        # Platform-specific idle time detection
        if sys.platform == "win32":
            return self._get_windows_idle_time()
        elif sys.platform == "darwin":
            return self._get_macos_idle_time()
        else:
            return self._get_linux_idle_time()

    def _get_windows_idle_time(self) -> float:
        """Get system idle time in seconds on Windows."""
        try:
            import ctypes
            from ctypes import wintypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT),
                           ("dwTime", wintypes.DWORD)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(lii)
            
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                return 0.0

            # GetTickCount returns the number of milliseconds since the system was started.
            # dwTime is also a 32-bit DWORD from GetTickCount.
            current_tick = ctypes.windll.kernel32.GetTickCount()
            
            # 32-bit unsigned subtraction handles rollover automatically in Python with & 0xFFFFFFFF
            idle_ms = (current_tick - lii.dwTime) & 0xFFFFFFFF
            
            # Debug logging every 30 seconds of idle time to help diagnose issues
            if idle_ms > 0 and (idle_ms // 1000) % 30 == 0:
                self.logger.debug(f"Windows Idle: current={current_tick}, last={lii.dwTime}, idle_ms={idle_ms}")
                
            return idle_ms / 1000.0
        except Exception as e:
            self.logger.error(f"Failed to get Windows idle time: {e}")
            return 0.0

    def _get_macos_idle_time(self) -> float:
        """Get idle time on macOS."""
        try:
            import subprocess
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem"],
                capture_output=True,
                text=True
            )
            # Parse output to find idle time
            # This is simplified - you might need better parsing
            for line in result.stdout.split('\n'):
                if '"HIDIdleTime"' in line:
                    # Extract nanoseconds and convert to seconds
                    parts = line.strip().split('=')
                    if len(parts) > 1:
                        nanoseconds = int(parts[1].strip())
                        return nanoseconds / 1_000_000_000
            return 0.0
        except Exception as e:
            self.logger.error(f"Failed to get macOS idle time: {e}")
            return 0.0

    def _get_linux_idle_time(self) -> float:
        """Get idle time on Linux."""
        # Try different methods for different desktop environments
        try:
            # Try X11 first
            import subprocess
            result = subprocess.run(
                ["xprintidle"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                millis = int(result.stdout.strip())
                return millis / 1000.0
        except Exception:
            pass

        # Fallback: use our own activity tracking
        return time.time() - self._last_activity

    def reset_timer(self):
        """Reset inactivity timer."""
        self._last_activity = time.time()
        self._warning_triggered = False
        self._warning_time = 0.0
        self.logger.debug("Inactivity timer reset")

    def _monitor_activity(self):
        """Monitor user activity in background thread."""
        self.logger.info(f"Inactivity monitor started (Thresholds: warn={self._warning_timeout}s, logout={self._logout_timeout}s)")

        while not self._stop_event.is_set():
            try:
                if not self._user_logged_in:
                    time.sleep(1)
                    continue

                idle_time = self._get_idle_time()

                # Check for warning timeout
                if not self._warning_triggered:
                    if idle_time >= self._warning_timeout:
                        self.logger.warning(f"🚨 Inactivity threshold reached: {idle_time:.1f}s >= {self._warning_timeout}s")
                        self._warning_triggered = True
                        self._warning_time = time.time()
                        if self._on_warning:
                            threading.Thread(target=self._on_warning, daemon=True).start()
                else:
                    # Warning already triggered, check for logout or reset
                    if idle_time < 1.0: # User moved mouse/keyboard (idle time reset)
                        # We don't necessarily reset the warning modal here if the app design
                        # requires a manual "Resume", but we should log it.
                        self.logger.debug("User activity detected during warning period")
                        # self._warning_triggered = False # Uncomment if we want auto-reset

                    # Check for logout timeout
                    if self._warning_time > 0:
                        time_since_warning = time.time() - self._warning_time
                        logout_threshold = max(10, self._logout_timeout - self._warning_timeout)
                        
                        if time_since_warning >= logout_threshold:
                            self.logger.warning(f"🚨 Inactivity logout threshold reached: {time_since_warning:.1f}s")
                            if self._on_logout:
                                threading.Thread(target=self._on_logout, daemon=True).start()
                            self._user_logged_in = False
                            self._warning_triggered = False
                            self._warning_time = 0.0

                time.sleep(1)  # Check every second

            except Exception as e:
                self.logger.error(f"Error in inactivity monitor: {e}")
                time.sleep(5)

    def set_timeouts(self, warn_seconds: int, logout_seconds: int):
        """Set inactivity timeouts."""
        self._warning_timeout = warn_seconds
        self._logout_timeout = logout_seconds
        self.logger.info(f"Inactivity timeouts set: warn={warn_seconds}s, logout={logout_seconds}s")

    def set_callbacks(self, on_warning: Callable, on_logout: Callable):
        """Set callback functions."""
        self._on_warning = on_warning
        self._on_logout = on_logout

    def start_monitoring(self):
        """Start inactivity monitoring."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_activity, daemon=True)
        self._thread.start()
        self.logger.info("Inactivity monitoring started")

    def stop_monitoring(self):
        """Stop inactivity monitoring."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.logger.info("Inactivity monitoring stopped")

    def user_logged_in(self, logged_in: bool = True):
        """Set user login status."""
        self._user_logged_in = logged_in
        if logged_in:
            self.reset_timer()
            self.logger.info("User logged in - inactivity monitoring active")
        else:
            self.logger.info("User logged out - inactivity monitoring inactive")

    def get_idle_time(self) -> float:
        """Get current idle time."""
        return self._get_idle_time()

    def get_status(self) -> dict:
        """Get current inactivity status."""
        idle_time = self.get_idle_time()
        return {
            'idle_time': idle_time,
            'warning_timeout': self._warning_timeout,
            'logout_timeout': self._logout_timeout,
            'warning_triggered': self._warning_triggered,
            'user_logged_in': self._user_logged_in,
            'time_to_warning': max(0, self._warning_timeout - idle_time),
            'time_to_logout': max(0, self._logout_timeout - idle_time),
            'last_activity': datetime.fromtimestamp(self._last_activity).isoformat()
        }