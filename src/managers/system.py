"""
src/managers/system.py
System monitoring manager.
"""

import threading
import time
import psutil
import platform
from typing import Dict, Any
from datetime import datetime

from ..config import constants


class SystemMonitor:
    """Manager for system resource monitoring."""

    def __init__(self, logger=None):
        self.logger = logger or self._get_default_logger()
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

        # Monitoring intervals
        self._monitor_interval = 60  # seconds

        # Thresholds
        self._cpu_threshold = 90  # percent
        self._memory_threshold = 85  # percent
        self._disk_threshold = 90  # percent

        # State
        self._last_monitor = None
        self._system_info = self._get_system_info()

    def _get_default_logger(self):
        import logging
        return logging.getLogger(__name__)

    def _get_system_info(self) -> Dict[str, Any]:
        """Get basic system information."""
        try:
            return {
                'platform': platform.system(),
                'platform_release': platform.release(),
                'platform_version': platform.version(),
                'architecture': platform.machine(),
                'processor': platform.processor(),
                'hostname': platform.node(),
                'python_version': platform.python_version(),
                'cpu_count': psutil.cpu_count(logical=False),
                'cpu_count_logical': psutil.cpu_count(logical=True),
                'total_memory': psutil.virtual_memory().total,
                'total_disk': psutil.disk_usage('/').total if hasattr(psutil, 'disk_usage') else 0,
            }
        except Exception as e:
            self.logger.error(f"Failed to get system info: {e}")
            return {}

    def _monitor_resources(self):
        """Monitor system resources in background thread."""
        self.logger.info(f"System monitor started (interval: {self._monitor_interval}s)")

        while not self._stop_event.is_set():
            try:
                self._last_monitor = datetime.now()

                # Get current resource usage
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/') if hasattr(psutil, 'disk_usage') else None

                # Check thresholds
                if cpu_percent > self._cpu_threshold:
                    self.logger.warning(f"High CPU usage: {cpu_percent}%")

                if memory.percent > self._memory_threshold:
                    self.logger.warning(f"High memory usage: {memory.percent}%")

                if disk and disk.percent > self._disk_threshold:
                    self.logger.warning(f"High disk usage: {disk.percent}%")

                # Log periodic status (every 10 minutes)
                if int(time.time()) % 600 == 0:  # Every 10 minutes
                    self.logger.info(
                        f"System status - CPU: {cpu_percent}%, "
                        f"Memory: {memory.percent}%, "
                        f"Disk: {disk.percent if disk else 'N/A'}%"
                    )

                time.sleep(self._monitor_interval)

            except Exception as e:
                self.logger.error(f"Error in system monitor: {e}")
                time.sleep(self._monitor_interval * 2)

    def start_monitoring(self):
        """Start system monitoring."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self._thread.start()
        self.logger.info("System monitoring started")

    def stop_monitoring(self):
        """Stop system monitoring."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.logger.info("System monitoring stopped")

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        return self._system_info.copy()

    def get_resource_usage(self) -> Dict[str, Any]:
        """Get current resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/') if hasattr(psutil, 'disk_usage') else None

            # Get process info
            process = psutil.Process()
            process_info = {
                'pid': process.pid,
                'name': process.name(),
                'status': process.status(),
                'cpu_percent': process.cpu_percent(),
                'memory_percent': process.memory_percent(),
                'memory_rss': process.memory_info().rss,
                'create_time': datetime.fromtimestamp(process.create_time()).isoformat(),
                'threads': process.num_threads(),
            }

            return {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': psutil.cpu_count(logical=False),
                    'count_logical': psutil.cpu_count(logical=True),
                    'threshold': self._cpu_threshold,
                },
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'used': memory.used,
                    'free': memory.free,
                    'percent': memory.percent,
                    'threshold': self._memory_threshold,
                },
                'disk': {
                    'total': disk.total if disk else 0,
                    'used': disk.used if disk else 0,
                    'free': disk.free if disk else 0,
                    'percent': disk.percent if disk else 0,
                    'threshold': self._disk_threshold,
                } if disk else None,
                'process': process_info,
                'thresholds_exceeded': {
                    'cpu': cpu_percent > self._cpu_threshold,
                    'memory': memory.percent > self._memory_threshold,
                    'disk': disk.percent > self._disk_threshold if disk else False,
                }
            }
        except Exception as e:
            self.logger.error(f"Failed to get resource usage: {e}")
            return {}

    def set_thresholds(self, cpu: int = None, memory: int = None, disk: int = None):
        """Set resource thresholds."""
        if cpu is not None:
            self._cpu_threshold = cpu
        if memory is not None:
            self._memory_threshold = memory
        if disk is not None:
            self._disk_threshold = disk

        self.logger.info(
            f"Thresholds set - CPU: {self._cpu_threshold}%, "
            f"Memory: {self._memory_threshold}%, "
            f"Disk: {self._disk_threshold}%"
        )

    def get_status(self) -> Dict[str, Any]:
        """Get monitoring status."""
        return {
            'running': self._running,
            'last_monitor': self._last_monitor.isoformat() if self._last_monitor else None,
            'interval': self._monitor_interval,
            'thresholds': {
                'cpu': self._cpu_threshold,
                'memory': self._memory_threshold,
                'disk': self._disk_threshold,
            },
            'system_info': self._system_info,
        }