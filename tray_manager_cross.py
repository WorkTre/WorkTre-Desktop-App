"""
tray_manager_cross.py
Cross-platform system tray manager for WorkTre Desktop App
"""

import sys
import os
import threading
import pystray
from PIL import Image, ImageDraw

# Import our platform utilities
from platform_utils import (
    show_confirmation_dialog,
    get_icon_path,
    is_dark_mode
)


class CrossPlatformTrayManager:
    def __init__(
            self,
            app_name: str,
            window_getter,
            icon_path: str = None,
            on_quit=None,
            on_restore=None,
            notifier=None,
            logger=None,
            is_updating_checker=None,
    ):
        """
        Cross-platform tray manager constructor.

        :param app_name: App name shown in tray
        :param window_getter: Callable that returns the current pywebview window
        :param icon_path: Path to icon file (.ico, .icns, .png)
        :param on_quit: Optional callback before quitting
        :param on_restore: Optional callback on restore
        :param notifier: Optional notification manager
        :param logger: Optional logger
        :param is_updating_checker: Callable that returns True if update is in progress
        """
        self.app_name = app_name
        self.window_getter = window_getter
        self.icon_path = icon_path
        self.on_quit = on_quit
        self.on_restore = on_restore
        self.notifier = notifier
        self.logger = logger
        self.is_updating_checker = is_updating_checker

        self._icon = None
        self._thread = None
        self._running = False

        # Platform-specific attributes
        self._setup_platform_specific()

    def _setup_platform_specific(self):
        """Setup platform-specific configurations."""
        self.platform = sys.platform

        # Platform-specific default icon names
        if self.platform == "win32":
            self.default_icon_name = "icon.ico"
            self.tray_name = f"{self.app_name} Tray"
        elif self.platform == "darwin":
            self.default_icon_name = "icon.icns"
            self.tray_name = self.app_name
        else:  # Linux and other Unix-like
            self.default_icon_name = "icon.png"
            self.tray_name = self.app_name

    def start(self):
        """Start system tray icon."""
        if self._running:
            return

        image = self._load_icon()
        menu = self._build_menu()

        # Create tray icon
        self._icon = pystray.Icon(
            name=self.tray_name,
            icon=image,
            title=self.app_name,
            menu=menu,
        )

        # Platform-specific setup
        if self.platform == "darwin":
            # macOS: Set up activation handler for double-click
            self._icon._menu = menu  # Ensure menu is set
        elif self.platform.startswith("linux"):
            # Linux: Some desktop environments need specific setup
            # pystray handles most things, but we set title for clarity
            pass

        # Start tray icon in a separate thread
        self._thread = threading.Thread(
            target=self._icon.run,
            daemon=True
        )
        self._thread.start()
        self._running = True

        self._log("Tray icon started")

    def _build_menu(self):
        """Build tray menu with platform-specific adjustments."""
        menu_items = []

        # Platform-specific menu structure
        if self.platform == "darwin":
            # macOS convention: App name first, then actions
            menu_items.append(
                pystray.MenuItem(
                    f"About {self.app_name}",
                    self._on_about
                )
            )
            menu_items.append(pystray.Menu.SEPARATOR)  # FIXED: Use pystray.Menu.SEPARATOR

        # Restore option (available on all platforms)
        menu_items.append(
            pystray.MenuItem(
                "Restore",
                self._on_restore_menu
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)  # FIXED: Use pystray.Menu.SEPARATOR

        # Platform-specific additional items
        if self.platform == "win32":
            # Windows might have different conventions
            menu_items.append(
                pystray.MenuItem(
                    "Settings",
                    self._on_settings
                )
            )
            menu_items.append(pystray.Menu.SEPARATOR)  # FIXED: Use pystray.Menu.SEPARATOR

        # Quit option
        menu_items.append(
            pystray.MenuItem(
                "Quit",
                self._on_quit_menu
            )
        )

        return pystray.Menu(*menu_items)

    def _load_icon(self):
        """Load icon with platform-specific handling."""
        # Try to load provided icon path
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                return self._process_icon_for_platform(self.icon_path)
            except Exception as e:
                self._log(f"Failed to load icon {self.icon_path}: {e}")

        # Try to find icon using platform utilities
        found_icon = get_icon_path("icon")
        if found_icon and os.path.exists(found_icon):
            try:
                return self._process_icon_for_platform(found_icon)
            except Exception as e:
                self._log(f"Failed to load found icon {found_icon}: {e}")

        # Generate fallback icon
        return self._create_fallback_icon()

    def _process_icon_for_platform(self, icon_path):
        """Process icon for specific platform requirements."""
        image = Image.open(icon_path)

        # Platform-specific processing
        if self.platform == "darwin":
            # macOS: Ensure icon has transparency and proper size
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # Resize to common macOS tray icon size (32x32 is common)
            if image.width > 64 or image.height > 64:
                image = image.resize((32, 32), Image.Resampling.LANCZOS)

        elif self.platform.startswith("linux"):
            # Linux: Typically uses PNG with transparency
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # Resize for Linux tray (typically 24x24 or 32x32)
            if image.width > 48 or image.height > 48:
                image = image.resize((24, 24), Image.Resampling.LANCZOS)

        else:  # Windows
            # Windows: ICO format works well, but we might need to handle PNG
            if image.mode == 'P' and 'transparency' in image.info:
                # Convert palette with transparency to RGBA
                image = image.convert('RGBA')
            elif image.mode == 'P':
                image = image.convert('RGB')

            # Resize for Windows tray
            if image.width > 32 or image.height > 32:
                image = image.resize((32, 32), Image.Resampling.LANCZOS)

        return image

    def _create_fallback_icon(self):
        """Create a simple fallback icon with platform-specific styling."""
        # Determine size based on platform
        if self.platform == "darwin":
            size = 32
        elif self.platform.startswith("linux"):
            size = 24
        else:  # Windows
            size = 32

        # Check if system is in dark mode for appropriate colors
        dark_mode = is_dark_mode()

        # Create image with transparency
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Choose colors based on dark mode
        if dark_mode:
            primary_color = "#01a78d"  # WorkTre green
            text_color = "#ffffff"
        else:
            primary_color = "#01a78d"
            text_color = "#ffffff"

        # Draw a simple logo
        padding = 4
        draw.ellipse(
            (padding, padding, size - padding, size - padding),
            fill=primary_color
        )

        # Draw "WT" text (simplified - in production you might want to use ImageFont)
        # For now, just draw lines to represent WT
        line_width = 2
        mid_x = size // 2
        mid_y = size // 2

        # Draw 'W' shape (simplified)
        draw.line([(mid_x - 6, padding + 6), (mid_x - 3, size - padding - 6)],
                  fill=text_color, width=line_width)
        draw.line([(mid_x - 3, size - padding - 6), (mid_x, padding + 6)],
                  fill=text_color, width=line_width)
        draw.line([(mid_x, padding + 6), (mid_x + 3, size - padding - 6)],
                  fill=text_color, width=line_width)
        draw.line([(mid_x + 3, size - padding - 6), (mid_x + 6, padding + 6)],
                  fill=text_color, width=line_width)

        return image

    def _on_restore_menu(self, icon=None, item=None):
        """Handle restore from menu."""
        self.restore()

    def _on_quit_menu(self, icon=None, item=None):
        """Handle quit from menu."""
        self.quit()

    def _on_about(self, icon=None, item=None):
        """Handle about menu item (macOS convention)."""
        try:
            from tkinter import messagebox
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()

            messagebox.showinfo(
                f"About {self.app_name}",
                f"{self.app_name}\nVersion: 1.0.0\n\n"
                "Cross-platform desktop application\n"
                "© 2024 WorkTre. All rights reserved."
            )

            root.destroy()
        except Exception as e:
            self._log(f"Error showing about dialog: {e}")

    def _on_settings(self, icon=None, item=None):
        """Handle settings menu item."""
        self._log("Settings menu clicked")
        # You can implement settings dialog here
        # For now, just restore the window
        self.restore()

    def restore(self):
        """Restore window from tray."""
        window = self.window_getter()
        if window:
            try:
                window.show()
                window.restore()

                # Platform-specific window focusing
                if self.platform == "win32":
                    # Windows specific focusing
                    try:
                        window.bring_to_front()
                        window.focus()
                    except:
                        pass
                elif self.platform == "darwin":
                    # macOS specific focusing
                    try:
                        # Some macOS-specific focusing if needed
                        pass
                    except:
                        pass

                if self.on_restore:
                    self.on_restore()

                self._log("Window restored")
            except Exception as e:
                self._log(f"Failed to restore window: {e}")

    def minimize_to_tray(self, notify=True):
        """Hide window to tray."""
        window = self.window_getter()
        if window:
            try:
                window.hide()

                if notify and self.notifier:
                    # Platform-specific notification messages
                    if self.platform == "darwin":
                        message = f"{self.app_name} is running in the menu bar"
                    elif self.platform.startswith("linux"):
                        message = f"{self.app_name} is running in the system tray"
                    else:  # Windows
                        message = f"{self.app_name} is running in the system tray"

                    self.notifier.show_professional_notification(
                        self.app_name,
                        message,
                        "info",
                        4,
                    )

                self._log("Minimized to tray")
            except Exception as e:
                self._log(f"Failed to minimize to tray: {e}")

    def quit(self):
        """Quit application with confirmation."""
        window = self.window_getter()

        # Block during update
        if self.is_updating_checker and self.is_updating_checker():
            show_confirmation_dialog(
                "Update in progress",
                f"{self.app_name} is currently updating. Please wait."
            )
            return

        # Show confirmation dialog
        confirmed = show_confirmation_dialog(
            f"Quit {self.app_name}",
            f"Are you sure you want to quit {self.app_name}?"
        )

        if not confirmed:
            self._log("User canceled quit")
            return

        self._log("User confirmed quit")

        # Call optional quit callback
        if self.on_quit:
            self.on_quit()

        # Stop tray icon
        self.stop()

        # Exit application
        import os
        os._exit(0)

    def stop(self):
        """Stop tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception as e:
                self._log(f"Error stopping tray icon: {e}")
            finally:
                self._icon = None
                self._running = False
                self._log("Tray icon stopped")

    def _log(self, msg):
        """Log message using logger or print."""
        if self.logger:
            self.logger.info(f"[Tray] {msg}")
        else:
            print(f"[Tray] {msg}")


# Factory function to create appropriate tray manager
def create_tray_manager(app_name, window_getter, **kwargs):
    """
    Factory function to create platform-appropriate tray manager.

    Usage:
        tray_manager = create_tray_manager(
            app_name="WorkTre",
            window_getter=lambda: current_window,
            icon_path="icon.png",
            logger=logger,
            is_updating_checker=lambda: is_updating,
        )
    """
    platform = sys.platform

    if platform == "win32":
        # For now, use the base class for all platforms
        # You can create platform-specific subclasses later if needed
        return CrossPlatformTrayManager(app_name, window_getter, **kwargs)
    elif platform == "darwin":
        return CrossPlatformTrayManager(app_name, window_getter, **kwargs)
    else:  # Linux and other Unix-like
        return CrossPlatformTrayManager(app_name, window_getter, **kwargs)


# Test function
def test_tray_manager():
    """Test the tray manager functionality."""
    print("Testing CrossPlatformTrayManager...")

    # Create a mock window getter
    class MockWindow:
        def show(self):
            print("MockWindow: show()")

        def hide(self):
            print("MockWindow: hide()")

        def restore(self):
            print("MockWindow: restore()")

    mock_window = MockWindow()

    # Create tray manager
    tray = CrossPlatformTrayManager(
        app_name="TestApp",
        window_getter=lambda: mock_window,
        logger=None,
    )

    print(f"Platform: {sys.platform}")
    print(f"Tray manager created: {tray}")

    # Test methods
    tray._log("Test log message")

    # Note: We don't start the tray in test mode as it would run forever
    print("Test completed successfully!")


if __name__ == "__main__":
    test_tray_manager()