"""
src/platform/tray/__init__.py
Tray manager package initialization.
"""

from .base import CrossPlatformTrayManager, create_tray_manager
from .windows import WindowsTrayManager
from .macos import MacTrayManager
from .linux import LinuxTrayManager

__all__ = [
    'CrossPlatformTrayManager',
    'create_tray_manager',
    'WindowsTrayManager',
    'MacTrayManager',
    'LinuxTrayManager'
]