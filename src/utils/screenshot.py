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
    from PIL import ImageGrab, Image, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ PIL/Pillow not installed. Screenshot functionality disabled.")

import requests
import certifi
from ..config import constants, settings
from .preferences import get_blur_radius

# Live post_max_size is not known and may be PHP's default 8M. 6 MB of
# base64 is a conservative backstop so a capture is re-encoded before upload.
MAX_UPLOAD_BASE64_CHARS = 6 * 1024 * 1024
# One retry after a size rejection, aimed under half of that backstop.
SIZE_RETRY_BASE64_CHARS = 3 * 1024 * 1024
JPEG_FALLBACK_QUALITY = 80
MAX_DOWNSCALE_STEPS = 24
MIN_DOWNSCALE_EDGE = 1
_SIZE_ERROR_CODES = frozenset({
    "too_large",
    "payload_too_large",
    "file_too_large",
})
_UPLOAD_LOG_CODES = frozenset({
    "invalid_credentials",
    "rate_limited",
    "bad_request",
    "token_expired",
    "token_invalid",
    "reauth_required",
    "too_large",
    "payload_too_large",
    "file_too_large",
})


def _upload_error_code(response) -> Optional[str]:
    """Read ``error`` or ``code`` from an upload response without logging the body."""
    try:
        from .desk_token import error_code_from_body
        body = response.json()
    except Exception:
        return None
    return error_code_from_body(body)


def _image_from_base64(b64_string: str):
    """Decode a screenshot payload into a detached PIL image."""
    raw = base64.b64decode(b64_string)
    with BytesIO(raw) as handle:
        image = Image.open(handle)
        image.load()
        return image.copy()


def _encode_jpeg_base64(image, quality: int) -> str:
    """JPEG base64 at the given quality. Callers log the length, not the bytes."""
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _jpeg_resample():
    resampling = getattr(Image, "Resampling", Image)
    return resampling.LANCZOS


class ScreenshotManager:
    """Manager for screenshot capture and upload."""

    def __init__(self, logger=None, token_manager=None):
        self.logger = logger
        self._token_manager = token_manager
        self._upload_queue = []
        self._upload_thread = None
        self._running = False
        self._upload_url = constants.SS_UPLOAD_URL

    def _log(self, message: str, level: str = "info"):
        """Log message if logger exists. Never include upload tokens."""
        safe = self._redact(str(message))
        if self.logger:
            log_func = getattr(self.logger, level, self.logger.info)
            log_func(f"[Screenshot] {safe}")
        else:
            print(f"[Screenshot] {safe}")

    def _redact(self, message: str) -> str:
        token = getattr(self, "_last_token", None)
        if token and token in message:
            return message.replace(token, "[redacted]")
        return message

    def _token_api(self):
        if self._token_manager is not None:
            return self._token_manager
        try:
            from .desk_token import get_token_manager
            return get_token_manager(self.logger)
        except Exception:
            return None

    def _apply_privacy_blur(self, image):
        """Apply Gaussian blur based on local privacy preferences."""
        try:
            radius = get_blur_radius()
        except Exception:
            radius = settings.SCREENSHOT_BLUR_RADIUS if settings.SCREENSHOT_BLUR_ENABLED else 0

        if radius and radius > 0:
            self._log(f"Applying privacy blur (radius={radius})")
            return image.filter(ImageFilter.GaussianBlur(radius=radius))
        return image

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
            screenshot = ImageGrab.grab(all_screens=True)
            screenshot = self._apply_privacy_blur(screenshot)

            buffer = BytesIO()

            if format.upper() == "JPEG":
                if screenshot.mode != 'RGB':
                    screenshot = screenshot.convert('RGB')
                screenshot.save(buffer, format="JPEG", quality=quality)
            else:
                screenshot.save(buffer, format="PNG")

            buffer.seek(0)
            return buffer.getvalue()

        except Exception as e:
            self._log(f"Failed to capture screenshot: {e}", "error")
            return None

    def capture_to_base64(self, quality: int = 85, format: str = "PNG") -> Optional[str]:
        """Capture screenshot and convert to base64."""
        image_data = self.capture(quality, format)
        if image_data:
            return base64.b64encode(image_data).decode('utf-8')
        return None

    def upload(self, user_id: str, image_data: Optional[bytes] = None,
               base64_data: Optional[str] = None) -> bool:
        """Upload screenshot to server."""
        if base64_data:
            b64_string = base64_data
        elif image_data:
            b64_string = base64.b64encode(image_data).decode('utf-8')
        else:
            b64_string = self.capture_to_base64()
            if not b64_string:
                return False

        try:
            fitted = self._fit_upload_payload(b64_string)
            if not fitted:
                self._log("Screenshot upload skipped after the size check", "error")
                return False
            b64_string, image_format = fitted
            token = self._current_upload_token(user_id)
            status, code = self._post_upload(user_id, b64_string, token, image_format)
            if status == 401 and code in ("token_invalid", "token_expired"):
                fresh = self._recover_upload_token(user_id)
                token = fresh
                status, code = self._post_upload(user_id, b64_string, fresh, image_format)
            if _size_rejected(status, code):
                smaller = self._jpeg_under_retry_limit(b64_string)
                if smaller:
                    logged = code if code in _UPLOAD_LOG_CODES else "other"
                    self._log(
                        f"Upload rejected status {status} code={logged} "
                        f"at base64 size {len(b64_string)}; "
                        f"retrying JPEG base64 size {len(smaller)}"
                    )
                    status, code = self._post_upload(user_id, smaller, token, "JPEG")
            if status == 200:
                self._log(f"Screenshot uploaded successfully for user {user_id}")
                return True
            self._log(f"Upload failed with status {status}", "error")
            return False

        except requests.exceptions.RequestException as e:
            self._log(f"Upload request failed: {type(e).__name__}", "error")
            return False
        except Exception as e:
            self._log(f"Upload failed: {type(e).__name__}", "error")
            return False

    def _current_upload_token(self, user_id) -> Optional[str]:
        manager = self._token_api()
        if manager is None:
            return None
        try:
            token = manager.get_upload_token(user_id)
        except Exception:
            return None
        self._last_token = token
        return token

    def _recover_upload_token(self, user_id) -> Optional[str]:
        manager = self._token_api()
        if manager is None:
            return None
        try:
            token = manager.recover_after_rejected_token(user_id)
        except Exception:
            token = None
        self._last_token = token
        return token

    def _fit_upload_payload(self, b64_string: str):
        """
        Keep the base64 payload at or under MAX_UPLOAD_BASE64_CHARS.

        A PNG over the limit is re-encoded as JPEG quality 80. If that is still
        over the limit, the same image is downscaled proportionally until it fits.
        Logs sizes only.
        """
        limit = MAX_UPLOAD_BASE64_CHARS
        original_size = len(b64_string)
        if original_size <= limit:
            return b64_string, "PNG"

        self._log(
            f"Screenshot base64 size {original_size} exceeds {limit}; "
            f"re-encoding as JPEG quality {JPEG_FALLBACK_QUALITY}"
        )
        if not PIL_AVAILABLE:
            self._log(f"Cannot shrink screenshot; base64 size {original_size}", "error")
            return None
        try:
            image = _image_from_base64(b64_string)
        except Exception:
            self._log(
                f"Cannot read screenshot for resize; base64 size {original_size}",
                "error",
            )
            return None

        jpeg_b64 = _encode_jpeg_base64(image, JPEG_FALLBACK_QUALITY)
        jpeg_size = len(jpeg_b64)
        self._log(f"Re-encoded JPEG base64 size {jpeg_size}")
        if jpeg_size <= limit:
            return jpeg_b64, "JPEG"

        self._log(
            f"JPEG base64 size {jpeg_size} still exceeds {limit}; "
            f"downscaling from {image.size[0]}x{image.size[1]}"
        )
        shrunk = self._downscale_until_fit(image, limit, jpeg_b64)
        return shrunk, "JPEG"

    def _jpeg_under_retry_limit(self, rejected_b64: str) -> Optional[str]:
        """One JPEG downscaled to SIZE_RETRY_BASE64_CHARS after a size rejection."""
        if not PIL_AVAILABLE:
            self._log("Cannot shrink a rejected screenshot", "error")
            return None
        try:
            image = _image_from_base64(rejected_b64)
        except Exception:
            self._log(
                f"Cannot read rejected screenshot; base64 size {len(rejected_b64)}",
                "error",
            )
            return None
        limit = SIZE_RETRY_BASE64_CHARS
        jpeg_b64 = _encode_jpeg_base64(image, JPEG_FALLBACK_QUALITY)
        if len(jpeg_b64) > limit:
            jpeg_b64 = self._downscale_until_fit(image, limit, jpeg_b64)
        if not jpeg_b64 or jpeg_b64 == rejected_b64:
            return None
        if len(jpeg_b64) <= limit or len(jpeg_b64) < len(rejected_b64):
            return jpeg_b64
        return None

    def _downscale_until_fit(self, image, limit: int, jpeg_b64: str) -> str:
        """Shrink until the JPEG fits, then send the smallest result either way."""
        resample = _jpeg_resample()
        width, height = image.size
        aspect = (height / float(width)) if width else 1.0
        seen = set()
        steps = 0
        while len(jpeg_b64) > limit and steps < MAX_DOWNSCALE_STEPS:
            if width <= MIN_DOWNSCALE_EDGE and height <= MIN_DOWNSCALE_EDGE:
                break
            steps += 1
            scale = (limit / float(len(jpeg_b64))) ** 0.5
            # Stay under 1 so each pass actually shrinks, including when JPEG
            # overhead dwarfs the pixel count.
            scale = min(0.85, max(0.25, scale * 0.9))
            new_w = max(MIN_DOWNSCALE_EDGE, int(width * scale))
            new_h = max(MIN_DOWNSCALE_EDGE, int(round(new_w * aspect)))
            if (new_w, new_h) == (width, height) or (new_w, new_h) in seen:
                new_w = max(MIN_DOWNSCALE_EDGE, width // 2)
                new_h = max(MIN_DOWNSCALE_EDGE, int(round(new_w * aspect)))
            if (new_w, new_h) == (width, height):
                break
            seen.add((new_w, new_h))
            self._log(
                f"Downscaling screenshot from {width}x{height} to {new_w}x{new_h}, "
                f"base64 size {len(jpeg_b64)}"
            )
            image = image.resize((new_w, new_h), resample)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            width, height = image.size
            jpeg_b64 = _encode_jpeg_base64(image, JPEG_FALLBACK_QUALITY)
            self._log(f"Downscaled screenshot base64 size {len(jpeg_b64)} at {width}x{height}")
        if len(jpeg_b64) > limit:
            self._log(
                f"Sending smallest screenshot base64 size {len(jpeg_b64)} "
                f"at {width}x{height} after {steps} steps"
            )
        return jpeg_b64

    def _post_upload(self, user_id: str, b64_string: str, token: Optional[str],
                     image_format: str = "PNG"):
        """POST the screenshot. userid stays on the URL; token stays in the body.

        ``data=`` must stay a dict so requests form-encodes it. Base64 ``+``
        has to leave as ``%2B``; a raw ``+`` is decoded as a space.
        """
        url = f"{self._upload_url}?userid={user_id}"
        payload = {
            "userid": user_id,
            "file": b64_string,
            "timestamp": str(int(time.time())),
            "format": image_format,
        }
        if token:
            payload["token"] = token
            self._last_token = token

        response = requests.post(
            url,
            data=payload,
            timeout=constants.REQUEST_TIMEOUT,
            verify=(certifi.where() if settings.VERIFY_SSL else False),
            allow_redirects=False,
        )
        raw_code = _upload_error_code(response)
        logged = raw_code if raw_code in _UPLOAD_LOG_CODES else ("other" if raw_code else "-")
        self._log(f"Upload status {response.status_code} code={logged}")
        # Token refresh uses 401. A size retry uses 413, or a 400 whose code
        # names a size reject. Any other 400 is final.
        if response.status_code in (401, 413):
            return response.status_code, raw_code
        if response.status_code == 400 and raw_code in _SIZE_ERROR_CODES:
            return response.status_code, raw_code
        return response.status_code, None


def _size_rejected(status, code) -> bool:
    """HTTP 413, or HTTP 400 with a size error code. One retry, then stop."""
    if status == 413:
        return True
    return status == 400 and code in _SIZE_ERROR_CODES

    def upload_async(self, user_id: str, callback: Optional[callable] = None):
        """Upload screenshot asynchronously."""
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

        if not self._running:
            self._start_queue_processor()

    def _start_queue_processor(self):
        """Start background queue processor."""
        self._running = True

        def processor():
            while self._running and self._upload_queue:
                item = self._upload_queue.pop(0)
                self.upload(item['user_id'])
                time.sleep(1)
            self._running = False

        self._upload_thread = threading.Thread(target=processor, daemon=True)
        self._upload_thread.start()

    def stop(self):
        """Stop queue processor."""
        self._running = False
        if self._upload_thread:
            self._upload_thread.join(timeout=2)


# ==================== CONVENIENCE FUNCTIONS ====================

_screenshot_manager = None


def get_screenshot_manager(logger=None) -> ScreenshotManager:
    """Get or create global screenshot manager."""
    global _screenshot_manager
    if _screenshot_manager is None:
        _screenshot_manager = ScreenshotManager(logger)
    return _screenshot_manager


def take_screenshot(user_id: str, logger=None, async_mode: bool = True) -> bool:
    """Take and upload a screenshot."""
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
    """Capture screenshot and return as base64."""
    manager = get_screenshot_manager()
    return manager.capture_to_base64(quality, format)


def capture_screenshot_bytes(quality: int = 85, format: str = "PNG") -> Optional[bytes]:
    """Capture screenshot and return as bytes."""
    manager = get_screenshot_manager()
    return manager.capture(quality, format)


__all__ = [
    'ScreenshotManager',
    'take_screenshot',
    'take_screenshot_sync',
    'capture_screenshot_base64',
    'capture_screenshot_bytes',
    'get_screenshot_manager',
]
