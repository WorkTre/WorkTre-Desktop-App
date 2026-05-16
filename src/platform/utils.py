"""
src/platform/utils.py
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
import portalocker

# ==================== PATH & DIRECTORY UTILITIES ====================

def get_app_data_dir(app_name="WorkTre"):
    """
    Get cross-platform application data directory.

    Windows: %APPDATA%\\WorkTre
    macOS: ~/Library/Application Support/WorkTre
    Linux: ~/.config/WorkTre
    """
    if sys.platform == "win32":
        base_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), app_name)
    elif sys.platform == "darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", app_name)
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            base_dir = os.path.join(xdg_config, app_name)
        else:
            base_dir = os.path.join(os.path.expanduser("~"), ".config", app_name)

    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def get_cache_dir(app_name="WorkTre"):
    """Get cross-platform cache directory."""
    if sys.platform == "win32":
        base_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), app_name, "Cache")
    elif sys.platform == "darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Caches", app_name)
    else:
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
        return os.path.join(os.path.expanduser("~"), "Desktop")
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Desktop")
    else:
        desktop = os.environ.get("XDG_DESKTOP_DIR")
        if desktop:
            return desktop
        return os.path.join(os.path.expanduser("~"), "Desktop")


# ==================== ICON & RESOURCE UTILITIES ====================

def get_icon_path(icon_name="icon", base_dir=None):
    """
    Get appropriate icon path for current platform.
    Searches for platform-specific icons first, then fallbacks.
    """
    if base_dir is None:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

    icon_preferences = {
        "win32": [".ico", ".png", ".jpg", ".bmp"],
        "darwin": [".icns", ".png", ".jpg", ".tiff"],
        "linux": [".png", ".svg", ".xpm", ".jpg"]
    }

    extensions = icon_preferences.get(sys.platform, [".png", ".ico", ".svg"])

    for ext in extensions:
        icon_path = os.path.join(base_dir, f"{icon_name}{ext}")
        if os.path.exists(icon_path):
            return icon_path

        assets_path = os.path.join(base_dir, "assets", "icons", f"{icon_name}{ext}")
        if os.path.exists(assets_path):
            return assets_path

        assets_path = os.path.join(base_dir, "..", "assets", "icons", f"{icon_name}{ext}")
        if os.path.exists(assets_path):
            return os.path.abspath(assets_path)

    return None


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, *relative_path.split('/'))


# ==================== DIALOG & UI UTILITIES ====================

def show_confirmation_dialog(title, message, parent_window=None):
    """Cross-platform confirmation dialog."""
    if sys.platform == "win32":
        try:
            return _windows_confirmation_dialog(title, message)
        except Exception:
            return _tkinter_confirmation_dialog(title, message, parent_window)
    else:
        return _tkinter_confirmation_dialog(title, message, parent_window)


def force_window_to_top(hwnd, topmost=True):
    """Force a window to the top and optionally set/unset topmost on Windows."""
    if sys.platform != "win32" or not hwnd:
        return

    import ctypes
    user32 = ctypes.windll.user32
    
    # Constants
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040
    
    target = HWND_TOPMOST if topmost else HWND_NOTOPMOST
    
    # Set topmost/notopmost
    user32.SetWindowPos(hwnd, target, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    
    if topmost:
        # Bring to foreground
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)

def _windows_confirmation_dialog(title, message):
    """Windows-specific confirmation dialog using native API."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    MB_YESNO = 0x04
    MB_ICONQUESTION = 0x20
    MB_SYSTEMMODAL = 0x1000
    MB_SETFOREGROUND = 0x10000
    MB_TOPMOST = 0x40000
    IDYES = 6

    # MB_SYSTEMMODAL ensures the dialog takes global focus and stays on top.
    # MB_SETFOREGROUND forces it to the foreground of the current thread.
    result = user32.MessageBoxW(
        0,
        message,
        title,
        MB_YESNO | MB_ICONQUESTION | MB_SYSTEMMODAL | MB_SETFOREGROUND | MB_TOPMOST
    )
    return result == IDYES


def _tkinter_confirmation_dialog(title, message, parent_window=None):
    """Tkinter-based confirmation dialog (cross-platform)."""
    root = None
    if parent_window is None:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

    try:
        result = messagebox.askyesno(title, message, parent=root)
    finally:
        if root:
            root.destroy()

    return result


def show_error_dialog(title, message, parent=None):
    """Show error dialog."""
    root = tk.Tk() if parent is None else parent
    try:
        if parent is None:
            root.withdraw()
        messagebox.showerror(title, message, parent=root)
    finally:
        if parent is None:
            root.destroy()


def show_info_dialog(title, message, parent=None):
    """Show information dialog."""
    root = tk.Tk() if parent is None else parent
    try:
        if parent is None:
            root.withdraw()
        messagebox.showinfo(title, message, parent=root)
    finally:
        if parent is None:
            root.destroy()


# ==================== SYSTEM UTILITIES ====================

def open_file_in_explorer(path):
    """Open file/folder in system file explorer."""
    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Path does not exist: {path}")

    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        print(f"Failed to open path '{path}': {e}")
        raise


def is_dark_mode():
    """Detect if system is in dark mode."""
    if sys.platform == "darwin":
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
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        except:
            return False

    elif sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                theme = result.stdout.lower()
                return "dark" in theme
        except:
            pass
        return False

    return False


def get_system_info():
    """Get basic system information."""
    return {
        "platform": sys.platform,
        "platform_version": platform.version(),
        "platform_release": platform.release(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


# ==================== APPLICATION LIFECYCLE ====================

def create_single_instance_lock(app_name="WorkTre"):
    """
    Create a single instance lock file.
    Returns (lock_successful, lock_file_path, lock_handle)
    """
    lock_dir = get_temp_dir(app_name)
    lock_file = os.path.join(lock_dir, f"{app_name}.lock")

    try:
        lock_handle = open(lock_file, 'w')
        portalocker.lock(lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return True, lock_file, lock_handle
    except (portalocker.exceptions.LockException, IOError):
        return False, lock_file, None
    except Exception as e:
        print(f"Lock error: {e}")
        return False, lock_file, None


def cleanup_temp_files(app_name="WorkTre"):
    """Clean up temporary files."""
    temp_dir = get_temp_dir(app_name)
    try:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"Cleanup error: {e}")


# ==================== LOGGING UTILITIES (FORWARDING) ====================

def setup_logging(app_name="WorkTre", level="DEBUG"):
    """
    Forward to src.utils.logging.setup_logging
    This is a compatibility wrapper.
    """
    try:
        from ..utils.logging import setup_logging as _setup_logging
        return _setup_logging(app_name, level)
    except ImportError:
        # Fallback if utils.logging is not available
        logging.basicConfig(
            level=getattr(logging, level),
            format='%(asctime)s [%(levelname)s] %(message)s'
        )
        return logging.getLogger(app_name)


def get_logger(name=None):
    """Forward to src.utils.logging.get_logger."""
    try:
        from ..utils.logging import get_logger as _get_logger
        return _get_logger(name)
    except ImportError:
        return logging.getLogger(name) if name else logging.getLogger()


# ==================== EXPORTS ====================

__all__ = [
    'get_app_data_dir',
    'get_cache_dir',
    'get_log_file_path',
    'get_temp_dir',
    'get_desktop_path',
    'get_icon_path',
    'resource_path',
    'show_confirmation_dialog',
    'show_error_dialog',
    'show_info_dialog',
    'open_file_in_explorer',
    'is_dark_mode',
    'get_system_info',
    'create_single_instance_lock',
    'cleanup_temp_files',
    'setup_logging',
    'get_logger',
]