"""
platform_utils.py
Cross-platform utilities for WorkTre Desktop App
"""

import os
import sys
import subprocess
import platform
import tkinter as tk
from tkinter import messagebox
import logging
from pathlib import Path
import tempfile


# ==================== PATH & DIRECTORY UTILITIES ====================

def get_app_data_dir(app_name="WorkTre"):
    """
    Get cross-platform application data directory.

    Windows: %APPDATA%\WorkTre
    macOS: ~/Library/Application Support/WorkTre
    Linux: ~/.config/WorkTre
    """
    if sys.platform == "win32":
        # Windows
        base_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), app_name)
    elif sys.platform == "darwin":
        # macOS
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", app_name)
    else:
        # Linux and other Unix-like
        # Try XDG_CONFIG_HOME first, then fallback to ~/.config
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            base_dir = os.path.join(xdg_config, app_name)
        else:
            base_dir = os.path.join(os.path.expanduser("~"), ".config", app_name)

    # Create directory if it doesn't exist
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def get_cache_dir(app_name="WorkTre"):
    """
    Get cross-platform cache directory.
    """
    if sys.platform == "win32":
        # Windows: Local AppData
        base_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), app_name, "Cache")
    elif sys.platform == "darwin":
        # macOS: ~/Library/Caches
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Caches", app_name)
    else:
        # Linux: XDG_CACHE_HOME or ~/.cache
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            base_dir = os.path.join(xdg_cache, app_name)
        else:
            base_dir = os.path.join(os.path.expanduser("~"), ".cache", app_name)

    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def get_log_file_path(app_name="WorkTre"):
    """Get cross-platform log file path."""
    base_dir = get_app_data_dir(app_name)
    return os.path.join(base_dir, "app.log")


def get_temp_dir(app_name="WorkTre"):
    """Get cross-platform temp directory within app data."""
    temp_dir = os.path.join(get_app_data_dir(app_name), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def get_desktop_path():
    """Get desktop directory path for current platform."""
    if sys.platform == "win32":
        # Windows
        return os.path.join(os.path.expanduser("~"), "Desktop")
    elif sys.platform == "darwin":
        # macOS
        return os.path.join(os.path.expanduser("~"), "Desktop")
    else:
        # Linux - check common desktop environment variables
        desktop = os.environ.get("XDG_DESKTOP_DIR")
        if desktop:
            return desktop
        # Fallback
        return os.path.join(os.path.expanduser("~"), "Desktop")


# ==================== ICON & RESOURCE UTILITIES ====================

def get_icon_path(icon_name="icon", base_dir=None):
    """
    Get appropriate icon path for current platform.
    Searches for platform-specific icons first, then fallbacks.
    """
    if base_dir is None:
        # Try to find icons relative to script location
        if getattr(sys, 'frozen', False):
            # Running as bundled executable
            base_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            base_dir = os.path.dirname(os.path.abspath(__file__))

    # Platform-specific icon preferences
    icon_preferences = {
        "win32": [".ico", ".png", ".jpg", ".bmp"],
        "darwin": [".icns", ".png", ".jpg", ".tiff"],
        "linux": [".png", ".svg", ".xpm", ".jpg"]
    }

    extensions = icon_preferences.get(sys.platform, [".png", ".ico", ".svg"])

    # Search for icons
    for ext in extensions:
        icon_path = os.path.join(base_dir, f"{icon_name}{ext}")
        if os.path.exists(icon_path):
            return icon_path

        # Also check in assets subdirectory
        assets_path = os.path.join(base_dir, "assets", f"{icon_name}{ext}")
        if os.path.exists(assets_path):
            return assets_path

    # If no specific icon found, look for any image file
    for file in os.listdir(base_dir):
        if file.startswith(icon_name) and any(
                file.endswith(ext) for ext in ['.ico', '.icns', '.png', '.svg', '.jpg', '.jpeg', '.bmp', '.tiff']):
            return os.path.join(base_dir, file)

    # Check assets directory
    assets_dir = os.path.join(base_dir, "assets")
    if os.path.exists(assets_dir):
        for file in os.listdir(assets_dir):
            if file.startswith(icon_name) and any(
                    file.endswith(ext) for ext in ['.ico', '.icns', '.png', '.svg', '.jpg', '.jpeg', '.bmp', '.tiff']):
                return os.path.join(assets_dir, file)

    return None


def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and PyInstaller.
    Replaces the one in main.py for cross-platform compatibility.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Normal execution
        base_path = os.path.abspath(".")

    # Handle nested paths
    return os.path.join(base_path, *relative_path.split('/'))


# ==================== DIALOG & UI UTILITIES ====================

def show_confirmation_dialog(title, message, parent_window=None):
    """
    Cross-platform confirmation dialog.
    Returns True if user clicks Yes/OK, False otherwise.
    """
    if sys.platform == "win32":
        # Use Windows API for better integration on Windows
        try:
            return _windows_confirmation_dialog(title, message)
        except Exception:
            # Fallback to tkinter
            return _tkinter_confirmation_dialog(title, message, parent_window)
    else:
        # Use tkinter for macOS and Linux
        return _tkinter_confirmation_dialog(title, message, parent_window)


def _windows_confirmation_dialog(title, message):
    """Windows-specific confirmation dialog using native API."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    MB_YESNO = 0x04
    MB_ICONQUESTION = 0x20
    MB_TASKMODAL = 0x2000
    MB_TOPMOST = 0x40000
    IDYES = 6

    # Get foreground window
    hwnd = user32.GetForegroundWindow()
    result = user32.MessageBoxW(
        hwnd,
        message,
        title,
        MB_YESNO | MB_ICONQUESTION | MB_TASKMODAL | MB_TOPMOST
    )
    return result == IDYES


def _tkinter_confirmation_dialog(title, message, parent_window=None):
    """Tkinter-based confirmation dialog (cross-platform)."""
    # Create a hidden root window if none exists
    root = None
    if parent_window is None:
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        root.attributes('-topmost', True)  # Make dialog appear on top

    try:
        result = messagebox.askyesno(title, message)
    finally:
        if root:
            root.destroy()

    return result


def show_info_dialog(title, message):
    """Show information dialog."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    messagebox.showinfo(title, message)
    root.destroy()


def show_error_dialog(title, message):
    """Show error dialog."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    messagebox.showerror(title, message)
    root.destroy()


# ==================== SYSTEM UTILITIES ====================

def open_file_in_explorer(path):
    """
    Open file/folder in system file explorer.
    """
    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Path does not exist: {path}")

    try:
        if sys.platform == "win32":
            # Windows
            os.startfile(path)
        elif sys.platform == "darwin":
            # macOS
            subprocess.run(["open", path])
        else:
            # Linux
            subprocess.run(["xdg-open", path])
    except Exception as e:
        # Fallback: print the path
        print(f"Failed to open path '{path}': {e}")
        raise


def is_dark_mode():
    """
    Detect if system is in dark mode.
    Returns True if dark mode is enabled, False otherwise.
    """
    if sys.platform == "darwin":
        # macOS
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0 and "Dark" in result.stdout
        except:
            return False

    elif sys.platform == "win32":
        # Windows 10/11
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0  # 0 = Dark, 1 = Light
        except:
            return False

    elif sys.platform.startswith("linux"):
        # Linux - check various desktop environments
        try:
            # GNOME
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                theme = result.stdout.lower()
                return "dark" in theme

            # KDE Plasma
            result = subprocess.run(
                ["kreadconfig5", "--group", "Colors:Window", "--key", "BackgroundNormal"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Parse RGB values - dark theme typically has lower values
                try:
                    r, g, b = map(int, result.stdout.split(','))
                    return (r + g + b) < 384  # If average < 128 per channel
                except:
                    pass
        except:
            pass

        return False

    return False


def get_system_info():
    """
    Get basic system information.
    """
    return {
        "platform": sys.platform,
        "platform_version": platform.version(),
        "platform_release": platform.release(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


# ==================== LOGGING UTILITIES ====================

def setup_logging(app_name="WorkTre", level=logging.INFO):
    """
    Setup comprehensive cross-platform logging.
    """
    log_dir = get_app_data_dir(app_name)
    log_file = os.path.join(log_dir, "app.log")

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    )

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear any existing handlers
    logger.handlers.clear()

    # File handler (detailed)
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    # Console handler (simple)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    # Return a named logger for the app
    return logging.getLogger(app_name)


def get_logger(name=None):
    """
    Get a logger instance.
    If no name is provided, returns the root logger.
    """
    if name:
        return logging.getLogger(name)
    return logging.getLogger()


# ==================== APPLICATION LIFECYCLE ====================

def create_single_instance_lock(app_name="WorkTre"):
    """
    Create a single instance lock file.
    Returns (lock_successful, lock_file_path)
    """
    import portalocker

    lock_dir = get_temp_dir(app_name)
    lock_file = os.path.join(lock_dir, f"{app_name}.lock")

    try:
        lock_handle = open(lock_file, 'w')
        portalocker.lock(lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return True, lock_file
    except (portalocker.exceptions.LockException, IOError):
        return False, lock_file
    except Exception as e:
        print(f"Lock error: {e}")
        return False, lock_file


def cleanup_temp_files(app_name="WorkTre"):
    """
    Clean up temporary files.
    """
    temp_dir = get_temp_dir(app_name)
    try:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"Cleanup error: {e}")


# ==================== TEST FUNCTIONS ====================

def test_platform_utils():
    """
    Test function to verify platform utilities work correctly.
    """
    print("=" * 50)
    print("Testing Platform Utilities")
    print("=" * 50)

    print(f"\n1. Platform: {sys.platform}")
    print(f"   System Info: {get_system_info()}")

    print(f"\n2. Application Directories:")
    print(f"   App Data: {get_app_data_dir()}")
    print(f"   Cache: {get_cache_dir()}")
    print(f"   Log File: {get_log_file_path()}")
    print(f"   Temp: {get_temp_dir()}")

    print(f"\n3. Icon Detection:")
    icon_path = get_icon_path()
    if icon_path:
        print(f"   Found icon: {icon_path}")
    else:
        print(f"   No icon found")

    print(f"\n4. Dark Mode Detection:")
    print(f"   Dark Mode: {is_dark_mode()}")

    print(f"\n5. Desktop Path:")
    print(f"   Desktop: {get_desktop_path()}")

    print(f"\n6. Single Instance Lock:")
    locked, lock_file = create_single_instance_lock()
    print(f"   Lock Successful: {locked}")
    print(f"   Lock File: {lock_file}")

    print("\n" + "=" * 50)
    print("Platform Utilities Test Complete")
    print("=" * 50)


if __name__ == "__main__":
    # Run tests if script is executed directly
    test_platform_utils()