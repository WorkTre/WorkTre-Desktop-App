"""
src/utils/preferences.py
Local user preferences (privacy / tracking settings).
"""

from typing import Any, Dict
from .file_utils import load_from_app_data, save_to_app_data

PREFS_FILE = "user_preferences.json"

DEFAULT_PREFS = {
    "screenshot_blur_enabled": True,
    "screenshot_blur_radius": 8,  # 0=off, 4=light, 8=medium, 16=strong
    "monitoring_notice_acked": False,
    "screenshot_consent_acked": False,
}


def get_preferences(app_name: str = "WorkTre") -> Dict[str, Any]:
    """Load preferences with defaults."""
    data = load_from_app_data(PREFS_FILE, app_name, default={})
    if not isinstance(data, dict):
        data = {}
    merged = dict(DEFAULT_PREFS)
    merged.update({k: v for k, v in data.items() if k in DEFAULT_PREFS or k.startswith("screenshot_")})
    # Keep unknown keys too for forward compatibility
    for k, v in data.items():
        if k not in merged:
            merged[k] = v
    return merged


def save_preferences(prefs: Dict[str, Any], app_name: str = "WorkTre") -> bool:
    """Save preferences (merged with defaults)."""
    current = get_preferences(app_name)
    current.update(prefs or {})
    # Normalize blur
    try:
        radius = int(current.get("screenshot_blur_radius", 8))
    except (TypeError, ValueError):
        radius = 8
    if radius < 0:
        radius = 0
    if radius > 32:
        radius = 32
    current["screenshot_blur_radius"] = radius
    current["screenshot_blur_enabled"] = bool(current.get("screenshot_blur_enabled", True)) and radius > 0
    current["monitoring_notice_acked"] = bool(current.get("monitoring_notice_acked", False))
    current["screenshot_consent_acked"] = bool(current.get("screenshot_consent_acked", False))
    path = save_to_app_data(PREFS_FILE, current, app_name)
    return path is not None


def get_blur_radius(app_name: str = "WorkTre") -> int:
    """Effective Gaussian blur radius (0 = no blur)."""
    prefs = get_preferences(app_name)
    if not prefs.get("screenshot_blur_enabled", True):
        return 0
    try:
        return max(0, int(prefs.get("screenshot_blur_radius", 8)))
    except (TypeError, ValueError):
        return 8
