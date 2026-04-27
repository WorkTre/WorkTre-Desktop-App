"""
src/utils/screenshot.py
Screenshot capture and upload utilities.
"""

import os
import base64
import threading
import time
from io import BytesIO
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from PIL import ImageGrab, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ PIL/Pillow not installed. Screenshot functionality disabled.")

import requests
from ..config import constants


class ScreenshotManager:
    """Manager for screenshot capture and upload."""

    def __init__(self, logger=None):
        self.logger = logger
        self._upload_queue = []
        self._upload_thread = None
        self._running = False
        self._upload_url = constants.SS_UPLOAD_URL

    def _log(self, message: str, level: str = "info"):
        """Log message if logger exists."""
        if self.logger:
            log_func = getattr(self.logger, level, self.logger.info)
            log_func(f"[Screenshot] {message}")
        else:
            print(f"[Screenshot] {message}")

    def capture(self, quality: int = 85, format: str = "PNG") -> Optional[bytes]:
        """
        Capture a screenshot.

        Args:
            quality: JPEG quality (1-100, only applies to JPEG)
            format: Image format (PNG, JPEG)

        Returns:
            Screenshot as bytes, or None if failed
        """
        if not PIL_AVAILABLE:
            self._log("PIL/Pillow not available", "error")
            return None

        try:
            # Capture screenshot
            screenshot = ImageGrab.grab(all_screens=True)

            # Convert to bytes
            buffer = BytesIO()

            if format.upper() == "JPEG":
                # Convert to RGB for JPEG
                if screenshot.mode != 'RGB':
                    screenshot = screenshot.convert('RGB')
                screenshot.save(buffer, format="JPEG", quality=quality)
            else:
                # PNG format
                screenshot.save(buffer, format="PNG")

            buffer.seek(0)
            return buffer.getvalue()

        except Exception as e:
            self._log(f"Failed to capture screenshot: {e}", "error")
            return None

    def capture_to_base64(self, quality: int = 85, format: str = "PNG") -> Optional[str]:
        """
        Capture screenshot and convert to base64.

        Args:
            quality: JPEG quality
            format: Image format

        Returns:
            Base64 encoded string, or None if failed
        """
        image_data = self.capture(quality, format)
        if image_data:
            return base64.b64encode(image_data).decode('utf-8')
        return None

    def upload(self, user_id: str, image_data: Optional[bytes] = None,
               base64_data: Optional[str] = None) -> bool:
        """
        Upload screenshot to server.

        Args:
            user_id: User ID
            image_data: Raw image bytes
            base64_data: Base64 encoded image data

        Returns:
            True if upload successful
        """
        # Get image data from either source
        if base64_data:
            b64_string = base64_data
        elif image_data:
            b64_string = base64.b64encode(image_data).decode('utf-8')
        else:
            # Capture new screenshot
            b64_string = self.capture_to_base64()
            if not b64_string:
                return False

        try:
            # Prepare upload data
            url = f"{self._upload_url}?userid={user_id}"
            payload = {
                "userid": user_id,
                "file": b64_string,
                "timestamp": str(int(time.time())),
                "format": "PNG"
            }

            # Upload to server
            response = requests.post(url, data=payload, timeout=10)

            if response.status_code == 200:
                self._log(f"Screenshot uploaded successfully for user {user_id}")
                return True
            else:
                self._log(f"Upload failed with status {response.status_code}", "error")
                return False

        except requests.exceptions.RequestException as e:
            self._log(f"Upload request failed: {e}", "error")
            return False
        except Exception as e:
            self._log(f"Upload failed: {e}", "error")
            return False

    def upload_async(self, user_id: str, callback: Optional[callable] = None):
        """
        Upload screenshot asynchronously.

        Args:
            user_id: User ID
            callback: Optional callback function on completion
        """
        def _upload_thread():
            result = self.upload(user_id)
            if callback:
                callback(result)

        thread = threading.Thread(target=_upload_thread, daemon=True)
        thread.start()
        return thread

    def queue_upload(self, user_id: str):
        """Queue screenshot for upload."""
        self._upload_queue.append({
            'user_id': user_id,
            'timestamp': time.time()
        })

        # Start processing thread if not running
        if not self._running:
            self._start_queue_processor()

    def _start_queue_processor(self):
        """Start background queue processor."""
        self._running = True

        def processor():
            while self._running and self._upload_queue:
                item = self._upload_queue.pop(0)
                self.upload(item['user_id'])
                time.sleep(1)  # Rate limiting
            self._running = False

        self._upload_thread = threading.Thread(target=processor, daemon=True)
        self._upload_thread.start()

    def stop(self):
        """Stop queue processor."""
        self._running = False
        if self._upload_thread:
            self._upload_thread.join(timeout=2)


# ==================== CONVENIENCE FUNCTIONS ====================

# Global screenshot manager instance
_screenshot_manager = None


def get_screenshot_manager(logger=None) -> ScreenshotManager:
    """Get or create global screenshot manager."""
    global _screenshot_manager
    if _screenshot_manager is None:
        _screenshot_manager = ScreenshotManager(logger)
    return _screenshot_manager


def take_screenshot(user_id: str, logger=None, async_mode: bool = True) -> bool:
    """
    Take and upload a screenshot.

    This is the main function called from main.py.

    Args:
        user_id: User ID to associate with screenshot
        logger: Optional logger instance
        async_mode: Whether to upload asynchronously

    Returns:
        True if upload started/successful
    """
    manager = get_screenshot_manager(logger)

    if async_mode:
        manager.upload_async(user_id)
        return True
    else:
        return manager.upload(user_id)


def take_screenshot_sync(user_id: str, logger=None) -> bool:
    """Take and upload screenshot synchronously."""
    return take_screenshot(user_id, logger, async_mode=False)


def capture_screenshot_base64(quality: int = 85, format: str = "PNG") -> Optional[str]:
    """
    Capture screenshot and return as base64.

    Returns:
        Base64 encoded screenshot or None
    """
    manager = get_screenshot_manager()
    return manager.capture_to_base64(quality, format)


def capture_screenshot_bytes(quality: int = 85, format: str = "PNG") -> Optional[bytes]:
    """
    Capture screenshot and return as bytes.

    Returns:
        Screenshot bytes or None
    """
    manager = get_screenshot_manager()
    return manager.capture(quality, format)


# ==================== EXPORTS ====================

__all__ = [
    'ScreenshotManager',
    'take_screenshot',
    'take_screenshot_sync',
    'capture_screenshot_base64',
    'capture_screenshot_bytes',
    'get_screenshot_manager',
]