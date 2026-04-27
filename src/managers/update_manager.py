"""
src/managers/update_manager.py
Cross-platform update manager for WorkTre Desktop Application.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import time
import threading
import hashlib
import platform
from typing import Optional, Dict, Any, Callable, List, Tuple
from pathlib import Path
import ssl
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import concurrent.futures

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠️ requests module not available, using urllib fallback")

from packaging import version

# Try to import from src
try:
    from ..config import constants
    from ..utils.logging import get_logger
    from ..utils.file_utils import get_local_version
except ImportError:
    # Fallback for when running as standalone
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.config import constants
    from src.utils.logging import get_logger
    from src.utils.file_utils import get_local_version


class UpdateManager:
    """Cross-platform manager for handling application updates."""

    # Platform identifiers
    PLATFORM_WINDOWS = 'windows'
    PLATFORM_MACOS = 'macos'
    PLATFORM_LINUX = 'linux'

    def __init__(self, window_getter=None, logger=None):
        """
        Initialize update manager.

        Args:
            window_getter: Optional callable to get window reference (can be None)
            logger: Logger instance
        """
        self.window_getter = window_getter  # Can be None now
        self.logger = logger or get_logger(__name__)
        self.is_updating = False
        self._cancel_requested = False
        self.installer_path = None
        self.temp_dir = None
        self.current_platform = self._detect_platform()
        self.download_start_time = 0
        self.last_progress_time = 0

        # Download settings
        self.use_parallel_download = False  # Set to True to enable parallel downloads
        self.parallel_threads = 4  # Number of parallel threads
        self.buffer_size = 64 * 1024  # 64KB buffer
        self.timeout = 30  # Request timeout in seconds

        # Version cache
        self._version_cache = None
        self._version_cache_time = 0
        self._version_cache_ttl = 300  # 5 minutes

    def _detect_platform(self) -> str:
        """Detect current platform."""
        if sys.platform == "win32":
            return self.PLATFORM_WINDOWS
        elif sys.platform == "darwin":
            return self.PLATFORM_MACOS
        else:
            return self.PLATFORM_LINUX

    def _get_platform_display_name(self) -> str:
        """Get user-friendly platform name."""
        return {
            self.PLATFORM_WINDOWS: "Windows",
            self.PLATFORM_MACOS: "macOS",
            self.PLATFORM_LINUX: "Linux"
        }.get(self.current_platform, "Unknown")

    def _format_size(self, bytes_count: int) -> str:
        """Format file size for display."""
        if bytes_count < 0:
            return "Unknown"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} TB"

    def _format_speed(self, bytes_per_second: float) -> str:
        """Format download speed for display."""
        if bytes_per_second < 0:
            return "Unknown"
        elif bytes_per_second < 1024:
            return f"{bytes_per_second:.0f} B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"

    def _get_installer_filename(self, version: str) -> str:
        """Get platform-specific installer filename."""
        if self.current_platform == self.PLATFORM_WINDOWS:
            return f"WorkTre_Setup_{version}.exe"
        elif self.current_platform == self.PLATFORM_MACOS:
            return f"WorkTre_{version}.dmg"
        else:  # Linux
            return f"WorkTre_{version}.AppImage"

    # ==================== MIRROR SELECTION ====================

    def get_fastest_mirror(self, version: str) -> str:
        """
        Test multiple mirrors and return the fastest one.

        Args:
            version: Version to download

        Returns:
            Fastest mirror URL
        """
        # Define mirrors for each platform
        filename = self._get_installer_filename(version)

        if self.current_platform == self.PLATFORM_WINDOWS:
            mirrors = [
                f"https://github.com/WorkTre/WorkTre-Desktop-App/releases/download/v{version}/{filename}",
                f"https://worktre.com/downloads/{filename}",
                f"https://sourceforge.net/projects/worktre/files/v{version}/{filename}/download"
            ]
        elif self.current_platform == self.PLATFORM_MACOS:
            mirrors = [
                f"https://github.com/WorkTre/WorkTre-Desktop-App/releases/download/v{version}/{filename}",
                f"https://worktre.com/downloads/{filename}",
            ]
        else:  # Linux
            mirrors = [
                f"https://github.com/WorkTre/WorkTre-Desktop-App/releases/download/v{version}/{filename}",
                f"https://worktre.com/downloads/{filename}",
            ]

        self.logger.info("Testing mirror speeds...")

        fastest_url = mirrors[0]
        fastest_time = float('inf')

        for url in mirrors:
            try:
                start = time.time()

                if REQUESTS_AVAILABLE:
                    response = requests.head(url, timeout=3, allow_redirects=True)
                    if response.status_code == 200:
                        elapsed = time.time() - start
                        self.logger.debug(f"Mirror {url}: {elapsed * 1000:.0f}ms")

                        if elapsed < fastest_time:
                            fastest_time = elapsed
                            fastest_url = url
                else:
                    # Fallback to urllib
                    req = Request(url, method='HEAD')
                    with urlopen(req, timeout=3) as response:
                        if response.status == 200:
                            elapsed = time.time() - start
                            self.logger.debug(f"Mirror {url}: {elapsed * 1000:.0f}ms")

                            if elapsed < fastest_time:
                                fastest_time = elapsed
                                fastest_url = url

            except Exception as e:
                self.logger.debug(f"Mirror {url} failed: {e}")
                continue

        self.logger.info(f"Selected fastest mirror: {fastest_url} ({fastest_time * 1000:.0f}ms)")
        return fastest_url

    # ==================== PARALLEL DOWNLOAD ====================

    def download_parallel(self, url: str, latest_version: str,
                          progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """
        Download using multiple threads for faster speeds.

        Args:
            url: Download URL
            latest_version: Version being downloaded
            progress_callback: Optional callback for progress updates

        Returns:
            True if download successful, False otherwise
        """
        if not REQUESTS_AVAILABLE:
            self.logger.error("requests module required for parallel download")
            return False

        try:
            self.is_updating = True
            self._cancel_requested = False
            self.download_start_time = time.time()

            # Create temp directory
            self.temp_dir = tempfile.mkdtemp(prefix=f"worktre_parallel_{self.current_platform}_")
            self.logger.info(f"Created temp directory: {self.temp_dir}")

            # Platform-specific installer name
            installer_name = self._get_installer_filename(latest_version)
            self.installer_path = os.path.join(self.temp_dir, installer_name)

            # Get file size
            self.logger.info(f"Getting file size from {url}")
            response = requests.head(url, timeout=10, allow_redirects=True)
            total_size = int(response.headers.get('content-length', 0))

            if total_size == 0:
                self.logger.error("Could not determine file size")
                return False

            self.logger.info(f"Total size: {self._format_size(total_size)}")

            # Calculate chunks for parallel download
            num_threads = min(self.parallel_threads, 8)  # Max 8 threads
            chunk_size = total_size // num_threads
            ranges = []

            for i in range(num_threads):
                start = i * chunk_size
                if i == num_threads - 1:
                    end = total_size - 1  # Last chunk goes to end
                else:
                    end = (i + 1) * chunk_size - 1
                ranges.append((start, end, i))

            self.logger.info(f"Downloading with {num_threads} parallel threads...")

            # Progress tracking
            downloaded_chunks = [0] * num_threads
            completed_chunks = [False] * num_threads
            lock = threading.Lock()

            def download_chunk(start, end, chunk_num):
                """Download a single chunk."""
                chunk_file = f"{self.installer_path}.part{chunk_num}"
                headers = {'Range': f'bytes={start}-{end}'}

                try:
                    with requests.get(url, headers=headers, stream=True, timeout=self.timeout) as r:
                        r.raise_for_status()
                        with open(chunk_file, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=self.buffer_size):
                                if self._cancel_requested:
                                    return False
                                if chunk:
                                    f.write(chunk)
                                    with lock:
                                        downloaded_chunks[chunk_num] += len(chunk)
                    return True
                except Exception as e:
                    self.logger.error(f"Chunk {chunk_num} failed: {e}")
                    return False

            # Execute parallel downloads
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                future_to_chunk = {
                    executor.submit(download_chunk, start, end, i): i
                    for start, end, i in ranges
                }

                # Monitor progress
                while not self._cancel_requested:
                    time.sleep(0.5)

                    total_downloaded = sum(downloaded_chunks)
                    if total_size > 0:
                        progress = (total_downloaded / total_size) * 100

                        # Calculate speed
                        elapsed = time.time() - self.download_start_time
                        speed = total_downloaded / elapsed if elapsed > 0 else 0

                        # Throttle progress updates (max 10 per second)
                        current_time = time.time()
                        if current_time - self.last_progress_time > 0.1:
                            self.last_progress_time = current_time
                            self.logger.debug(
                                f"⬇️ Progress: {progress:.1f}% | "
                                f"Speed: {self._format_speed(speed)}"
                            )

                            if progress_callback:
                                progress_callback(progress)

                    # Check if all chunks are complete
                    if all(f.done() for f in future_to_chunk):
                        break

            if self._cancel_requested:
                self.logger.warning("Download cancelled")
                self.cleanup()
                return False

            # Check if all chunks succeeded
            all_success = all(f.result() for f in future_to_chunk)
            if not all_success:
                self.logger.error("Some chunks failed to download")
                return False

            # Combine chunks
            self.logger.info("Combining downloaded chunks...")
            with open(self.installer_path, 'wb') as outfile:
                for i in range(num_threads):
                    chunk_file = f"{self.installer_path}.part{i}"
                    with open(chunk_file, 'rb') as infile:
                        shutil.copyfileobj(infile, outfile)
                    os.remove(chunk_file)

            # Verify file size
            actual_size = os.path.getsize(self.installer_path)
            if actual_size != total_size:
                self.logger.error(f"File size mismatch: expected {total_size}, got {actual_size}")
                return False

            # Calculate final stats
            total_time = time.time() - self.download_start_time
            avg_speed = total_size / total_time if total_time > 0 else 0

            self.logger.info(
                f"✅ Parallel download complete: {self._format_size(total_size)} "
                f"in {total_time:.1f}s ({self._format_speed(avg_speed)})"
            )

            return True

        except Exception as e:
            self.logger.error(f"Parallel download failed: {e}")
            import traceback
            traceback.print_exc()
            self.cleanup()
            return False
        finally:
            self.is_updating = False

    # ==================== STANDARD DOWNLOAD ====================

    def download_update(self, download_url: str, latest_version: str,
                        progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """
        Download update with progress tracking.

        Args:
            download_url: URL to download from
            latest_version: Version being downloaded
            progress_callback: Optional callback for progress updates

        Returns:
            True if download successful, False otherwise
        """
        try:
            self.is_updating = True
            self._cancel_requested = False
            self.download_start_time = time.time()
            self.last_progress_time = 0

            self.logger.info(f"📥 download_update called with URL: {download_url}")
            self.logger.info(f"📥 Version: {latest_version}")

            # Create temp directory
            self.temp_dir = tempfile.mkdtemp(prefix="worktre_update_")
            self.logger.info(f"📁 Temp directory: {self.temp_dir}")

            # Platform-specific installer name
            installer_name = self._get_installer_filename(latest_version)
            self.installer_path = os.path.join(self.temp_dir, installer_name)
            self.logger.info(f"📁 Installer path: {self.installer_path}")

            # Use requests if available, otherwise fallback to urllib
            if REQUESTS_AVAILABLE:
                return self._download_with_requests(download_url, latest_version, progress_callback)
            else:
                return self._download_with_urllib(download_url, latest_version, progress_callback)

        except Exception as e:
            self.logger.error(f"❌ Download failed: {e}")
            import traceback
            traceback.print_exc()
            self.cleanup()
            return False
        finally:
            self.is_updating = False

    def _download_with_requests(self, download_url: str, latest_version: str,
                                 progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """Download using requests library."""
        try:
            import requests

            # Test URL first
            self.logger.info(f"🌐 Testing URL: {download_url}")
            try:
                test_response = requests.head(download_url, timeout=5, allow_redirects=True)
                if test_response.status_code == 200:
                    self.logger.info(f"✅ URL is accessible (Status: {test_response.status_code})")
                    total_size = int(test_response.headers.get('content-length', 0))
                    self.logger.info(f"📊 File size: {self._format_size(total_size)}")
                else:
                    self.logger.error(f"❌ URL returned status {test_response.status_code}")
                    return False
            except Exception as e:
                self.logger.error(f"❌ URL test failed: {e}")
                return False

            # Download file with progress
            self.logger.info(f"🌐 Starting download...")

            response = requests.get(download_url, stream=True, timeout=self.timeout)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            block_size = self.buffer_size
            downloaded = 0
            last_logged_progress = 0

            with open(self.installer_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=block_size):
                    if self._cancel_requested:
                        self.logger.warning("Download cancelled")
                        self.cleanup()
                        return False

                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = (downloaded / total_size) * 100

                            # Calculate speed
                            elapsed = time.time() - self.download_start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0

                            # Log progress every 5% or when significant time passes
                            current_progress_int = int(progress)
                            if current_progress_int >= last_logged_progress + 5 or current_progress_int == 100:
                                last_logged_progress = current_progress_int
                                self.logger.info(
                                    f"📊 Progress: {progress:.1f}% "
                                    f"({self._format_size(downloaded)}/{self._format_size(total_size)}) - "
                                    f"{self._format_speed(speed)}"
                                )

                            # Throttle callback updates
                            current_time = time.time()
                            if current_time - self.last_progress_time > 0.1 and progress_callback:
                                self.last_progress_time = current_time
                                progress_callback(progress)

            if self._cancel_requested:
                self.logger.warning("Download cancelled")
                self.cleanup()
                return False

            # Verify download
            if total_size > 0 and downloaded < total_size:
                self.logger.error(f"❌ Download incomplete: {downloaded}/{total_size} bytes")
                return False

            total_time = time.time() - self.download_start_time
            avg_speed = downloaded / total_time if total_time > 0 else 0
            self.logger.info(
                f"✅ Download complete: {self._format_size(downloaded)} "
                f"in {total_time:.1f}s ({self._format_speed(avg_speed)})"
            )

            return True

        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Download failed: {e}")
            return False

    def _download_with_urllib(self, download_url: str, latest_version: str,
                               progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """Download using urllib (fallback method)."""
        try:
            self.logger.info("Using urllib fallback for download")

            # Create SSL context that doesn't verify (for corporate networks)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Open URL
            req = Request(download_url, headers={'User-Agent': 'WorkTre-Desktop/UpdateManager'})

            with urlopen(req, timeout=self.timeout, context=ssl_context) as response:
                # Get file size if available
                total_size = int(response.headers.get('Content-Length', 0))
                self.logger.info(f"File size: {self._format_size(total_size)}")

                block_size = self.buffer_size
                downloaded = 0
                last_logged_progress = 0

                with open(self.installer_path, 'wb') as file:
                    while True:
                        if self._cancel_requested:
                            self.logger.warning("Download cancelled")
                            self.cleanup()
                            return False

                        chunk = response.read(block_size)
                        if not chunk:
                            break

                        file.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = (downloaded / total_size) * 100

                            # Calculate speed
                            elapsed = time.time() - self.download_start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0

                            # Log progress every 10%
                            current_progress_int = int(progress)
                            if current_progress_int >= last_logged_progress + 10:
                                last_logged_progress = current_progress_int
                                self.logger.info(
                                    f"Progress: {progress:.1f}% "
                                    f"({self._format_size(downloaded)}/{self._format_size(total_size)}) - "
                                    f"{self._format_speed(speed)}"
                                )

                            # Throttle callback updates
                            current_time = time.time()
                            if current_time - self.last_progress_time > 0.2 and progress_callback:
                                self.last_progress_time = current_time
                                progress_callback(progress)

            if total_size > 0 and downloaded < total_size:
                self.logger.error(f"Download incomplete: {downloaded}/{total_size} bytes")
                return False

            total_time = time.time() - self.download_start_time
            avg_speed = downloaded / total_time if total_time > 0 else 0
            self.logger.info(
                f"✅ Download complete: {self._format_size(downloaded)} "
                f"in {total_time:.1f}s ({self._format_speed(avg_speed)})"
            )

            return True

        except HTTPError as e:
            self.logger.error(f"HTTP Error: {e.code} - {e.reason}")
            return False
        except URLError as e:
            self.logger.error(f"URL Error: {e.reason}")
            return False
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False

    # ==================== CHECKSUM VERIFICATION ====================

    def verify_checksum(self, filepath: str, expected_checksum: Optional[str] = None) -> bool:
        """
        Verify file integrity using SHA256.

        Args:
            filepath: Path to file to verify
            expected_checksum: Expected SHA256 checksum (if None, skip verification)

        Returns:
            True if verification passes or skipped, False if mismatch
        """
        if not expected_checksum:
            self.logger.warning("No checksum provided, skipping verification")
            return True

        try:
            sha256 = hashlib.sha256()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256.update(chunk)

            actual = sha256.hexdigest().lower()
            expected = expected_checksum.lower()

            if actual == expected:
                self.logger.info("✅ Checksum verification passed")
                return True
            else:
                self.logger.error(f"❌ Checksum mismatch")
                self.logger.debug(f"Expected: {expected}")
                self.logger.debug(f"Actual: {actual}")
                return False

        except Exception as e:
            self.logger.error(f"Checksum verification failed: {e}")
            return False

    # ==================== UPDATE CHECK ====================

    def check_for_updates(self, force: bool = False) -> Dict[str, Any]:
        """
        Check for updates from GitHub with platform-specific URLs.

        Args:
            force: Force check even if cache is still valid

        Returns:
            Dictionary with update information
        """
        try:
            # Check cache
            current_time = time.time()
            if not force and self._version_cache and current_time - self._version_cache_time < self._version_cache_ttl:
                self.logger.debug("Using cached version info")
                return self._version_cache

            self.logger.info(f"Checking for updates ({self._get_platform_display_name()})...")

            local_version = get_local_version()

            # Use requests if available
            if REQUESTS_AVAILABLE:
                response = requests.get(
                    constants.UPDATE_URL,
                    timeout=5,
                    headers={'User-Agent': 'WorkTre-Desktop'}
                )
                data = response.json() if response.status_code == 200 else None
            else:
                # Fallback to urllib
                req = Request(constants.UPDATE_URL, headers={'User-Agent': 'WorkTre-Desktop'})
                with urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode('utf-8'))

            if data:
                remote_version = data.get("version")

                # Get platform-specific download info
                platform_key = self.current_platform
                platform_data = data.get(platform_key, {})
                download_url = platform_data.get("download_url")
                checksum = platform_data.get("checksum")

                self.logger.info(f"Platform: {platform_key}, Download URL: {download_url}")

                if remote_version and download_url:
                    self.logger.info(f"Local: {local_version}, Remote: {remote_version}")

                    if version.parse(remote_version) > version.parse(local_version):
                        result = {
                            "update_available": True,
                            "current_version": local_version,
                            "latest_version": remote_version,
                            "download_url": download_url,
                            "platform": self.current_platform,
                            "release_notes": data.get("release_notes", ""),
                            "checksum": checksum,
                            "release_date": data.get("release_date", ""),
                            "size": platform_data.get("size", 0)
                        }
                    else:
                        result = {
                            "update_available": False,
                            "current_version": local_version,
                            "latest_version": remote_version,
                            "message": "You're running the latest version"
                        }

                    # Cache the result
                    self._version_cache = result
                    self._version_cache_time = current_time

                    return result
                else:
                    self.logger.warning(f"No download URL for {self.current_platform}")
            else:
                self.logger.warning("Failed to get update info from server")

        except Exception as e:
            self.logger.error(f"Update check failed: {e}")

        result = {
            "update_available": False,
            "current_version": get_local_version(),
            "error": "Could not check for updates"
        }

        self._version_cache = result
        self._version_cache_time = current_time

        return result

    # ==================== INSTALLATION METHODS ====================

    def install_update(self) -> bool:
        """Install the downloaded update with platform-specific handling."""
        try:
            if not self.installer_path or not os.path.exists(self.installer_path):
                self.logger.error("No installer found")
                return False

            self.logger.info(f"Installing from {self.installer_path}")

            if self.current_platform == self.PLATFORM_WINDOWS:
                return self._install_windows()
            elif self.current_platform == self.PLATFORM_MACOS:
                return self._install_macos()
            else:
                return self._install_linux()

        except Exception as e:
            self.logger.error(f"Installation failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _install_windows(self) -> bool:
        """Windows-specific installation."""
        try:
            import ctypes
            from ctypes import wintypes

            # Check if running with admin privileges
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()

            if is_admin:
                self.logger.info("Running with admin privileges")
                # Removed silent flags so the installer appears
                subprocess.Popen(
                    [self.installer_path]
                )
            else:
                self.logger.info("Requesting admin privileges...")
                # Request elevation and show normal installer UI
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    self.installer_path,
                    "",
                    None,
                    1  # SW_SHOWNORMAL
                )

            self._schedule_cleanup()
            return True

        except Exception as e:
            self.logger.error(f"Windows installation failed: {e}")
            return False

    def _install_macos(self) -> bool:
        """macOS-specific installation."""
        try:
            # Verify DMG
            result = subprocess.run(
                ["hdiutil", "verify", self.installer_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                self.logger.error(f"DMG verification failed: {result.stderr}")
                return False

            self.logger.info("DMG verification passed")

            # Mount and install
            subprocess.Popen(["open", self.installer_path])

            self._schedule_cleanup()
            return True

        except subprocess.TimeoutExpired:
            self.logger.error("DMG verification timed out")
            return False
        except Exception as e:
            self.logger.error(f"macOS installation failed: {e}")
            return False

    def _install_linux(self) -> bool:
        """Linux-specific installation."""
        try:
            # Make AppImage executable
            os.chmod(self.installer_path, 0o755)

            # Verify AppImage
            result = subprocess.run(
                [self.installer_path, "--appimage-offset"],
                capture_output=True,
                timeout=10
            )

            if result.returncode != 0:
                self.logger.error("AppImage verification failed")
                return False

            self.logger.info("AppImage verification passed")

            # Launch AppImage
            subprocess.Popen([self.installer_path])

            self._schedule_cleanup()
            return True

        except subprocess.TimeoutExpired:
            self.logger.error("AppImage verification timed out")
            return False
        except Exception as e:
            self.logger.error(f"Linux installation failed: {e}")
            return False

    def _schedule_cleanup(self):
        """Schedule cleanup of temporary files after a delay."""
        def cleanup():
            time.sleep(10)  # Wait 10 seconds before cleaning
            self.cleanup()

        threading.Thread(target=cleanup, daemon=True).start()

    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                # Try multiple times with delay in case files are locked
                for attempt in range(3):
                    try:
                        shutil.rmtree(self.temp_dir, ignore_errors=True)
                        if not os.path.exists(self.temp_dir):
                            self.logger.info(f"✅ Cleaned up: {self.temp_dir}")
                            break
                    except Exception:
                        if attempt < 2:
                            time.sleep(1)  # Wait before retry
                        else:
                            raise
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")

    def cancel_download(self):
        """Cancel ongoing download."""
        self._cancel_requested = True
        self.logger.info("Download cancellation requested")

    def get_download_status(self) -> Dict[str, Any]:
        """Get current download status."""
        if not self.is_updating or not self.installer_path:
            return {"status": "idle"}

        elapsed = time.time() - self.download_start_time if self.download_start_time > 0 else 0

        if os.path.exists(self.installer_path):
            downloaded = os.path.getsize(self.installer_path)
        else:
            downloaded = 0

        return {
            "status": "downloading" if self.is_updating else "complete",
            "downloaded": downloaded,
            "elapsed": elapsed,
            "cancel_requested": self._cancel_requested
        }


# ==================== CONVENIENCE FUNCTIONS ====================

def check_for_updates_sync(logger=None) -> Dict[str, Any]:
    """
    Synchronous update check (convenience function).

    Args:
        logger: Optional logger instance

    Returns:
        Update information dictionary
    """
    manager = UpdateManager(logger=logger)
    return manager.check_for_updates()


def download_update_sync(url: str, version: str,
                         progress_callback: Optional[Callable[[float], None]] = None,
                         logger=None) -> bool:
    """
    Synchronous download (convenience function).

    Args:
        url: Download URL
        version: Version to download
        progress_callback: Optional progress callback
        logger: Optional logger instance

    Returns:
        True if successful, False otherwise
    """
    manager = UpdateManager(logger=logger)
    return manager.download_update(url, version, progress_callback)


# ==================== MAIN EXECUTION ====================

if __name__ == "__main__":
    # Test the update manager when run directly
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("UpdateManager")

    manager = UpdateManager(logger=logger)

    print(f"Platform: {manager._get_platform_display_name()}")

    # Check for updates
    print("\nChecking for updates...")
    result = manager.check_for_updates()

    if result.get("update_available"):
        print(f"✅ Update available: {result['current_version']} -> {result['latest_version']}")
        print(f"   Download URL: {result['download_url']}")

        # Test fastest mirror
        print("\nTesting mirrors...")
        fastest = manager.get_fastest_mirror(result['latest_version'])
        print(f"Fastest mirror: {fastest}")

    else:
        print(f"❌ {result.get('message', 'No updates available')}")