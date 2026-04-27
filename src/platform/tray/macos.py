"""
src/platform/tray/macos.py
macOS-specific tray manager.
"""

import sys
from PIL import Image, ImageDraw
import pystray
from .base import CrossPlatformTrayManager


class MacTrayManager(CrossPlatformTrayManager):
    """macOS-specific tray manager."""

    def _setup_platform_specific(self):
        super()._setup_platform_specific()
        # macOS-specific setup
        self.tray_name = self.app_name

    def _build_menu(self):
        """Build macOS-style menu."""
        menu_items = []

        # macOS convention: About first
        menu_items.append(
            pystray.MenuItem(
                f"About {self.app_name}",
                self._on_about
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Restore (macOS uses "Show App Name")
        menu_items.append(
            pystray.MenuItem(
                f"Show {self.app_name}",
                self._on_restore_menu
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Quit (with Command+Q convention in mind)
        menu_items.append(
            pystray.MenuItem(
                f"Quit {self.app_name}",
                self._on_quit_menu
            )
        )

        return pystray.Menu(*menu_items)

    def _create_fallback_icon(self):
        """Create macOS-style fallback icon."""
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # macOS-style rounded icon
        draw.ellipse((4, 4, 28, 28), fill="#01a78d")

        # Draw "WT" text
        from PIL import ImageFont
        try:
            # Try to load a macOS font
            font = ImageFont.truetype("Helvetica", 12)
            draw.text((10, 8), "WT", fill="white", font=font)
        except:
            # Fallback to simple drawing
            draw.text((10, 8), "WT", fill="white")

        return image