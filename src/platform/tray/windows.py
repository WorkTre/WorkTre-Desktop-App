"""
src/platform/tray/windows.py
Windows-specific tray manager.
"""

import sys
from PIL import Image, ImageDraw
import pystray
from .base import CrossPlatformTrayManager


class WindowsTrayManager(CrossPlatformTrayManager):
    """Windows-specific tray manager."""

    def _setup_platform_specific(self):
        super()._setup_platform_specific()
        # Windows-specific setup
        self.tray_name = f"{self.app_name} Tray"

    def _build_menu(self):
        """Build Windows-style menu."""
        menu_items = []

        # Restore option
        menu_items.append(
            pystray.MenuItem(
                "Restore",
                self._on_restore_menu
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Settings option (Windows convention)
        menu_items.append(
            pystray.MenuItem(
                "Settings",
                self._on_settings
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Quit option
        menu_items.append(
            pystray.MenuItem(
                "Quit",
                self._on_quit_menu
            )
        )

        return pystray.Menu(*menu_items)

    def _create_fallback_icon(self):
        """Create Windows-specific fallback icon."""
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Windows-style icon
        draw.rectangle((6, 6, 26, 26), fill="#01a78d")

        # Draw "WT" text
        from PIL import ImageFont
        try:
            # Try to load a font
            font = ImageFont.truetype("arial.ttf", 12)
            draw.text((10, 8), "WT", fill="white", font=font)
        except:
            # Fallback to simple drawing
            draw.text((10, 8), "WT", fill="white")

        return image

    def _on_settings(self, icon=None, item=None):
        """Windows settings handler."""
        self._log("Windows settings clicked")
        # In Windows, settings might open a configuration dialog
        # For now, just restore the window
        self.restore()