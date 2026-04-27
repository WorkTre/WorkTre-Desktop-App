"""
src/managers/connectivity.py
Network connectivity manager.
"""

import threading
import time
import socket
import requests
from typing import Optional, Callable
from datetime import datetime, timedelta

from ..config import constants


class ConnectivityManager:
    """Manager for monitoring network connectivity."""

    def __init__(self, logger=None):
        self.logger = logger or self._get_default_logger()
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

        # Callbacks
        self._on_online: Optional[Callable] = None
        self._on_offline: Optional[Callable] = None
        self._on_timeout: Optional[Callable] = None

        # Configuration
        self._check_interval = 30  # seconds
        self._timeout = 5  # seconds
        self._max_offline_time = 300  # 5 minutes before triggering action

        # State
        self._is_online = True
        self._last_check = None
        self._offline_since = None
        self._check_urls = [
            "https://www.google.com",
            "https://www.cloudflare.com",
            "https://worktre.com"
        ]

    def _get_default_logger(self):
        import logging
        return logging.getLogger(__name__)

    def _check_connectivity(self) -> bool:
        """Check network connectivity."""
        for url in self._check_urls:
            try:
                response = requests.get(url, timeout=self._timeout)
                if response.status_code < 400:
                    return True
            except Exception:
                continue

        # Also try simple socket connection
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=self._timeout)
            return True
        except Exception:
            pass

        return False

    def _monitor_connectivity(self):
        """Monitor network connectivity in background thread."""
        self.logger.info(f"Connectivity monitor started (interval: {self._check_interval}s)")

        while not self._stop_event.is_set():
            try:
                was_online = self._is_online
                self._is_online = self._check_connectivity()
                self._last_check = datetime.now()

                # State change detection
                if was_online and not self._is_online:
                    self.logger.warning("Network connection lost")
                    self._offline_since = self._last_check
                    if self._on_offline:
                        threading.Thread(target=self._on_offline, daemon=True).start()

                elif not was_online and self._is_online:
                    self.logger.info("Network connection restored")
                    self._offline_since = None
                    if self._on_online:
                        threading.Thread(target=self._on_online, daemon=True).start()

                # Check if offline for too long
                if (not self._is_online and self._offline_since and
                    (datetime.now() - self._offline_since).total_seconds() > self._max_offline_time):
                    self.logger.error(f"Offline for more than {self._max_offline_time}s")
                    if self._on_timeout:
                        threading.Thread(target=self._on_timeout, daemon=True).start()
                    # Reset so it doesn't fire continuously
                    self._offline_since = None

                time.sleep(self._check_interval)

            except Exception as e:
                self.logger.error(f"Error in connectivity monitor: {e}")
                time.sleep(self._check_interval * 2)  # Longer delay on error

    def set_callbacks(self, on_online: Callable, on_offline: Callable, on_timeout: Callable = None):
        """Set callback functions."""
        self._on_online = on_online
        self._on_offline = on_offline
        self._on_timeout = on_timeout

    def set_check_interval(self, interval: int):
        """Set connectivity check interval in seconds."""
        self._check_interval = interval
        self.logger.info(f"Connectivity check interval set to {interval}s")

    def set_max_offline_time(self, max_time: int):
        """Set maximum offline time before action (in seconds)."""
        self._max_offline_time = max_time
        self.logger.info(f"Max offline time set to {max_time}s")

    def start_monitoring(self):
        """Start connectivity monitoring."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_connectivity, daemon=True)
        self._thread.start()
        self.logger.info("Connectivity monitoring started")

    def stop_monitoring(self):
        """Stop connectivity monitoring."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.logger.info("Connectivity monitoring stopped")

    def force_check(self) -> bool:
        """Force an immediate connectivity check."""
        self._is_online = self._check_connectivity()
        self._last_check = datetime.now()
        return self._is_online

    def is_online(self) -> bool:
        """Check if currently online."""
        return self._is_online

    def get_status(self) -> dict:
        """Get current connectivity status."""
        return {
            'is_online': self._is_online,
            'last_check': self._last_check.isoformat() if self._last_check else None,
            'offline_since': self._offline_since.isoformat() if self._offline_since else None,
            'check_interval': self._check_interval,
            'time_offline': (datetime.now() - self._offline_since).total_seconds()
                           if self._offline_since else 0,
            'max_offline_time': self._max_offline_time
        }