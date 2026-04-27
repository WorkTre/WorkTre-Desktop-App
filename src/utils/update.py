"""
src/utils/update.py
Update management utilities for WorkTre Desktop Application.
"""

import os
import sys
import ssl
import shutil
import tempfile
import subprocess
import time
import threading
from typing import Optional, Dict, Any, Callable
from urllib.request import urlopen, Request
from pathlib import Path

import requests

from ..config import constants
from .logging import get_logger
from .file_utils import ensure_directory


class UpdateManager:
    """Manager for application updates."""

    def __init__(self, logger=None):
        self.logger = logger or get_logger(__name__)
        self.is_downloading = False
        self.download_progress = 0
        self._cancel_requested = False

    def _log(self, message: str, level: str = "info"):
        """Log message."""
        log_func = getattr(self.logger, level, self.logger.info)
        log_func(f"[Update] {message}")

    def check_for_updates(self, current_version: str, update_url: str = constants.UPDATE_URL) -> Dict[str, Any]:
        """
        Check for available updates.

        Args:
            current_version: Current application version
            update_url: URL to check for updates

        Returns:
            Dictionary with update information
        """
        try:
            self._log(f"Checking for updates at {update_url}")
            response = requests.get(update_url, timeout=10)
            response.raise_for_status()

            data = response.json()
            remote_version = data.get("version")
            download_url = data.get("download_url")

            if not remote_version or not download_url:
                return {"update": False, "error": "Invalid update data"}

            # Compare versions
            from packaging import version
            if version.parse(remote_version) > version.parse(current_version):
                self._log(f"Update available: {current_version} -> {remote_version}")
                return {
                    "update": True,
                    "latest_version": remote_version,
                    "download_url": download_url,
                    "release_notes": data.get("release_notes", ""),
                    "required": data.get("required", False)
                }
            else:
                self._log(f"No update available (current: {current_version})")
                return {"update": False}

        except requests.exceptions.RequestException as e:
            self._log(f"Update check failed: {e}", "error")
            return {"update": False, "error": str(e)}
        except Exception as e:
            self._log(f"Update check error: {e}", "error")
            return {"update": False, "error": str(e)}

    def download_file(self, url: str, destination: str,
                      progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """
        Download file with progress tracking.

        Args:
            url: URL to download
            destination: Destination file path
            progress_callback: Callback for progress updates (0-100)

        Returns:
            True if download successful
        """
        try:
            self._log(f"Downloading from {url}")
            self.is_downloading = True
            self.download_progress = 0
            self._cancel_requested = False

            # Create SSL context
            ssl_context = ssl._create_unverified_context()

            # Open URL
            req = Request(url, headers={'User-Agent': 'WorkTre-Desktop/1.0'})
            response = urlopen(req, context=ssl_context, timeout=30)

            # Get file size
            total_size = int(response.headers.get('Content-Length', 0))
            block_size = 8192  # 8KB chunks

            self._log(f"Download size: {total_size} bytes")

            # Ensure destination directory exists
            ensure_directory(os.path.dirname(destination))

            downloaded = 0
            with open(destination, 'wb') as file:
                while not self._cancel_requested:
                    buffer = response.read(block_size)
                    if not buffer:
                        break

                    file.write(buffer)
                    downloaded += len(buffer)

                    # Calculate progress
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                    else:
                        progress = 0

                    self.download_progress = progress

                    if progress_callback:
                        progress_callback(progress)

                    if downloaded % (block_size * 100) == 0:  # Log every ~800KB
                        self._log(f"Downloaded: {downloaded}/{total_size} bytes ({progress:.1f}%)")

            if self._cancel_requested:
                self._log("Download cancelled", "warning")
                return False

            self._log(f"Download complete: {downloaded} bytes")
            return True

        except Exception as e:
            self._log(f"Download failed: {e}", "error")
            return False
        finally:
            self.is_downloading = False

    def cancel_download(self):
        """Cancel ongoing download."""
        self._cancel_requested = True
        self._log("Download cancellation requested")

    def install_update(self, installer_path: str, app_name: str = "WorkTre") -> bool:
        """
        Install downloaded update.

        Args:
            installer_path: Path to installer file
            app_name: Application name

        Returns:
            True if installation started
        """
        try:
            self._log(f"Installing update from {installer_path}")

            if not os.path.exists(installer_path):
                self._log(f"Installer not found: {installer_path}", "error")
                return False

            # Platform-specific installation
            if sys.platform == "win32":
                # Windows: run installer
                subprocess.Popen([installer_path], shell=True)
                self._log("Windows installer launched")

            elif sys.platform == "darwin":
                # macOS: open DMG
                subprocess.Popen(["open", installer_path])
                self._log("macOS installer opened")

            else:
                # Linux: make executable and run
                os.chmod(installer_path, 0o755)
                subprocess.Popen([installer_path])
                self._log("Linux installer launched")

            return True

        except Exception as e:
            self._log(f"Installation failed: {e}", "error")
            return False

    def download_and_install(self, download_url: str, latest_version: str,
                              progress_callback: Optional[Callable[[float], None]] = None,
                              window=None) -> bool:
        """
        Download and install update.

        Args:
            download_url: URL to download
            latest_version: Latest version string
            progress_callback: Progress callback
            window: WebView window for JS callbacks

        Returns:
            True if successful
        """
        temp_dir = None
        try:
            # Create temp directory
            temp_dir = tempfile.mkdtemp(prefix="worktre_update_")

            # Platform-specific installer name
            if sys.platform == "win32":
                installer_name = f"WorkTre_Setup_{latest_version}.exe"
            elif sys.platform == "darwin":
                installer_name = f"WorkTre_{latest_version}.dmg"
            else:
                installer_name = f"WorkTre_{latest_version}.AppImage"

            installer_path = os.path.join(temp_dir, installer_name)

            # Define progress wrapper
            def progress_wrapper(progress):
                if progress_callback:
                    progress_callback(progress)
                if window:
                    try:
                        window.evaluate_js(f"window.updateDownloadProgress && window.updateDownloadProgress({progress});")
                    except:
                        pass

            # Download file
            success = self.download_file(download_url, installer_path, progress_wrapper)

            if not success:
                self._log("Download failed", "error")
                return False

            # Notify completion
            if window:
                try:
                    window.evaluate_js("window.updateDownloadProgress && window.updateDownloadProgress(100);")
                except:
                    pass

            # Small delay for UI update
            time.sleep(1)

            # Install update
            return self.install_update(installer_path)

        except Exception as e:
            self._log(f"Update failed: {e}", "error")
            return False
        finally:
            # Clean up temp dir after installation (wait a bit)
            if temp_dir and os.path.exists(temp_dir):
                def cleanup():
                    time.sleep(5)
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self._log(f"Cleaned up temp directory: {temp_dir}")
                    except:
                        pass
                threading.Thread(target=cleanup, daemon=True).start()


# ==================== CONVENIENCE FUNCTIONS ====================

# Global update manager instance
_update_manager = None


def get_update_manager(logger=None) -> UpdateManager:
    """Get or create global update manager."""
    global _update_manager
    if _update_manager is None:
        _update_manager = UpdateManager(logger)
    return _update_manager


def check_for_updates(current_version: str, update_url: str = constants.UPDATE_URL) -> Dict[str, Any]:
    """Check for available updates."""
    manager = get_update_manager()
    return manager.check_for_updates(current_version, update_url)


def download_and_install_update(download_url: str, latest_version: str,
                                 progress_callback: Optional[Callable[[float], None]] = None,
                                 window=None) -> bool:
    """Download and install update."""
    manager = get_update_manager()
    return manager.download_and_install(download_url, latest_version, progress_callback, window)


def download_file(url: str, destination: str,
                  progress_callback: Optional[Callable[[float], None]] = None) -> bool:
    """Download file with progress."""
    manager = get_update_manager()
    return manager.download_file(url, destination, progress_callback)


def cancel_download():
    """Cancel ongoing download."""
    manager = get_update_manager()
    manager.cancel_download()


# ==================== EXPORTS ====================

__all__ = [
    'UpdateManager',
    'check_for_updates',
    'download_and_install_update',
    'download_file',
    'cancel_download',
    'get_update_manager',
]