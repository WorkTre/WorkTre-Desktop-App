"""
src/utils/__init__.py
Utility functions and classes.
"""

from .security import (
    SecurityManager,
    save_remembered_user,
    get_remembered_user,
    clear_remembered_user,
    encrypt_data,
    decrypt_data,
    get_security_manager
)
from .logging import setup_logging, get_logger
from .file_utils import (
    resource_path,
    get_asset_path,
    ensure_directory,
    get_local_version,
    read_json_file,
    write_json_file,
    FileLock
)
from .network import get_dynamic_ip, check_internet_connection
from .screenshot import take_screenshot, capture_screenshot_base64, ScreenshotManager
from .update import (
    UpdateManager,
    check_for_updates,
    download_and_install_update,
    download_file,
    cancel_download,
    get_update_manager
)

__all__ = [
    # Security
    'SecurityManager',
    'save_remembered_user',
    'get_remembered_user',
    'clear_remembered_user',
    'encrypt_data',
    'decrypt_data',
    'get_security_manager',

    # Logging
    'setup_logging',
    'get_logger',

    # File utils
    'resource_path',
    'get_asset_path',
    'ensure_directory',
    'get_local_version',
    'read_json_file',
    'write_json_file',
    'FileLock',

    # Network
    'get_dynamic_ip',
    'check_internet_connection',

    # Screenshot
    'take_screenshot',
    'capture_screenshot_base64',
    'ScreenshotManager',

    # Update
    'UpdateManager',
    'check_for_updates',
    'download_and_install_update',
    'download_file',
    'cancel_download',
    'get_update_manager',
]