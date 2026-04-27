"""
src/platform/tray/linux.py
Linux-specific tray manager.
"""

import sys
from PIL import Image, ImageDraw
import pystray
from .base import CrossPlatformTrayManager


class LinuxTrayManager(CrossPlatformTrayManager):
    """Linux-specific tray manager."""

    def _setup_platform_specific(self):
        super()._setup_platform_specific()
        # Linux-specific setup
        self.tray_name = self.app_name

    def _build_menu(self):
        """Build Linux-style menu."""
        menu_items = []

        # Restore option
        menu_items.append(
            pystray.MenuItem(
                "Restore",
                self._on_restore_menu
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
        """Create Linux-style fallback icon."""
        image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Linux-style simple icon
        draw.ellipse((2, 2, 22, 22), fill="#01a78d")

        # Draw "WT" text
        from PIL import ImageFont
        try:
            # Try to load a Linux font
            font = ImageFont.truetype("DejaVuSans", 10)
            draw.text((6, 5), "WT", fill="white", font=font)
        except:
            # Fallback to simple drawing
            draw.text((6, 5), "WT", fill="white")

        return image