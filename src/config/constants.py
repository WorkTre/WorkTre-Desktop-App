"""
src/config/constants.py
Application constants.
"""

# URLs
UPDATE_URL = "https://raw.githubusercontent.com/WorkTre/WorkTre-Desktop-App/main/version.json"
SOAP_BASE_URL = "https://worktre.com:443/webservices/worktre_soap_2.1.1/services.php"
SS_UPLOAD_URL = "https://worktre.com/ss_upload/index"

# Application info
APP_NAME = "WorkTre"
APP_DESCRIPTION = "WorkTre Desktop Application"
APP_AUTHOR = "WorkTre Team"

# Time constants (in seconds)
SECOND = 1
MINUTE = 60
HOUR = 3600
DAY = 86400

# Default timeouts
DEFAULT_INACTIVITY_WARN = 300    # 5 minutes
DEFAULT_INACTIVITY_LOGOUT = 600  # 10 minutes
DEFAULT_INTERVAL = 300           # 5 minutes
CONNECTION_TIMEOUT = 30          # 30 seconds
REQUEST_TIMEOUT = 10             # 10 seconds

# File constants
KEY_FILE = "remember_me.key"
DATA_FILE = "remember_me.json"
LOG_FILE = "worktre.log"
LOCK_FILE = "worktre.lock"

# Screenshot settings
SCREENSHOT_QUALITY = 85
SCREENSHOT_FORMAT = "PNG"

# Notification constants
NOTIFICATION_INFO = "info"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_ERROR = "error"
NOTIFICATION_SUCCESS = "success"
NOTIFICATION_BREAK = "break"
NOTIFICATION_CONNECTION = "connection"

# API Response statuses
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_WARNING = "warning"

# Break types
BREAK_TYPE_INACTIVITY = "inactivity"
BREAK_TYPE_LUNCH = "lunch"
BREAK_TYPE_TEA = "tea"
BREAK_TYPE_TRAINING = "training"
BREAK_TYPE_MEETING = "meeting"

# Error messages
ERROR_NETWORK = "Network error. Please check your internet connection."
ERROR_SERVER = "Server error. Please try again later."
ERROR_CREDENTIALS = "Invalid username or password."
ERROR_TIMEOUT = "Request timed out. Please try again."
ERROR_UNKNOWN = "An unknown error occurred."

# Success messages
SUCCESS_LOGIN = "Login successful!"
SUCCESS_LOGOUT = "Logout successful!"
SUCCESS_BREAK_START = "Break started successfully."
SUCCESS_BREAK_END = "Break ended successfully."
SUCCESS_UPDATE = "Update completed successfully."

# Colors (WorkTre theme)
COLOR_PRIMARY = "#01a78d"
COLOR_PRIMARY_DARK = "#017a68"
COLOR_SECONDARY = "#002f34"
COLOR_SUCCESS = "#27ae60"
COLOR_WARNING = "#f39c12"
COLOR_ERROR = "#e74c3c"
COLOR_INFO = "#3498db"
COLOR_LIGHT = "#f8f9fa"
COLOR_DARK = "#2c3e50"

# Window dimensions
WINDOW_WIDTH = 1092
WINDOW_HEIGHT = 650
MIN_WINDOW_WIDTH = 800
MIN_WINDOW_HEIGHT = 600

# Update check interval (in seconds)
UPDATE_CHECK_INTERVAL = 3600  # 1 hour

# Logging levels
LOG_DEBUG = "DEBUG"
LOG_INFO = "INFO"
LOG_WARNING = "WARNING"
LOG_ERROR = "ERROR"
LOG_CRITICAL = "CRITICAL"