"""
src/config/settings.py
Application settings and configuration.
"""

import os
import sys
from pathlib import Path

from . import constants

# Base paths
if getattr(sys, 'frozen', False):
    # Running as bundled executable
    BASE_DIR = Path(sys._MEIPASS)
else:
    # Running as script
    BASE_DIR = Path(__file__).parent.parent.parent

# App info
APP_NAME = constants.APP_NAME
APP_DESCRIPTION = constants.APP_DESCRIPTION
APP_AUTHOR = constants.APP_AUTHOR

# Version - will be loaded from file_utils
APP_VERSION = None  # Will be set later

# URLs
UPDATE_URL = constants.UPDATE_URL
SOAP_BASE_URL = constants.SOAP_BASE_URL
SS_UPLOAD_URL = constants.SS_UPLOAD_URL

# Timeouts
DEFAULT_TIMEOUT = constants.REQUEST_TIMEOUT
CONNECTION_TIMEOUT = constants.CONNECTION_TIMEOUT
UPDATE_CHECK_INTERVAL = constants.UPDATE_CHECK_INTERVAL

# Inactivity defaults
DEFAULT_WARN_AFTER = constants.DEFAULT_INACTIVITY_WARN
DEFAULT_KICK_AFTER = constants.DEFAULT_INACTIVITY_LOGOUT

# Screenshot
SCREENSHOT_QUALITY = constants.SCREENSHOT_QUALITY
SCREENSHOT_FORMAT = constants.SCREENSHOT_FORMAT

# Notification
NOTIFICATION_DURATION = 5
NOTIFICATION_MAX_COUNT = 5

# Security
KEY_FILE_NAME = constants.KEY_FILE
DATA_FILE_NAME = constants.DATA_FILE
ENCRYPTION_ALGORITHM = "fernet"

# SSL
VERIFY_SSL = False  # Set to False for development, True for production

# Platform-specific settings
class PlatformSettings:
    @staticmethod
    def get_icon_extension():
        """Get appropriate icon extension for current platform."""
        if sys.platform == "win32":
            return ".ico"
        elif sys.platform == "darwin":
            return ".icns"
        else:
            return ".png"

    @staticmethod
    def get_gui_backend():
        """Get appropriate GUI backend for current platform."""
        if sys.platform == "win32":
            return "edgechromium"
        elif sys.platform == "darwin":
            return "cef"
        else:
            return "qt"

    @staticmethod
    def get_installer_name():
        """Get platform-specific installer name."""
        if sys.platform == "win32":
            return "WorkTreInstaller.exe"
        elif sys.platform == "darwin":
            return "WorkTreInstaller.dmg"
        else:
            return "WorkTreInstaller.AppImage"


# Asset paths
class AssetPaths:
    """Centralized asset path management."""

    @staticmethod
    def get_base_path():
        """Get base assets directory."""
        return BASE_DIR / "src" / "assets"

    @staticmethod
    def get_html_path(filename="index.html"):
        """Get HTML file path."""
        path = AssetPaths.get_base_path() / filename
        return str(path)

    @staticmethod
    def get_css_path(filename):
        """Get CSS file path."""
        return str(AssetPaths.get_base_path() / "css" / filename)

    @staticmethod
    def get_js_path(filename):
        """Get JavaScript file path."""
        return str(AssetPaths.get_base_path() / "js" / filename)

    @staticmethod
    def get_image_path(filename):
        """Get image file path."""
        return str(AssetPaths.get_base_path() / "images" / filename)

    @staticmethod
    def get_font_path(filename):
        """Get font file path."""
        return str(AssetPaths.get_base_path() / "fonts" / filename)

    @staticmethod
    def get_webfont_path(filename):
        """Get webfont file path."""
        return str(AssetPaths.get_base_path() / "webfonts" / filename)

    @staticmethod
    def get_icon_path(icon_name="icon"):
        """Get icon file path for current platform."""
        base_path = AssetPaths.get_base_path() / "icons"
        ext = PlatformSettings.get_icon_extension()

        # Try platform-specific icon first
        icon_path = base_path / f"{icon_name}{ext}"
        if icon_path.exists():
            return str(icon_path)

        # Fallback to PNG
        png_path = base_path / f"{icon_name}.png"
        if png_path.exists():
            return str(png_path)

        # Fallback to any icon
        for file in base_path.iterdir():
            if file.suffix in ['.ico', '.icns', '.png', '.jpg']:
                return str(file)

        return None

    @staticmethod
    def get_version_path():
        """Get version.txt file path."""
        path = AssetPaths.get_base_path() / "version.txt"
        return str(path)

    @staticmethod
    def get_logo_path():
        """Get logo path."""
        return AssetPaths.get_image_path("logo.png")


# Logging configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        },
        'simple': {
            'format': '%(asctime)s [%(levelname)s] %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'simple',
            'stream': 'ext://sys.stdout'
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True
        },
        'WorkTre': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False
        },
    }
}


# Function to set version after import
def set_version(version):
    """Set APP_VERSION after it's loaded."""
    global APP_VERSION
    APP_VERSION = version