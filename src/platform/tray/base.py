"""
src/platform/tray/base.py
Base cross-platform tray manager.
"""

import sys
import os
import threading
import pystray
from PIL import Image, ImageDraw, ImageFont

# Import our platform utilities
from ..utils import (
    show_confirmation_dialog,
    get_icon_path,
    is_dark_mode
)


class CrossPlatformTrayManager:
    """Base cross-platform tray manager."""

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

        Args:
            app_name: App name shown in tray
            window_getter: Callable that returns the current pywebview window
            icon_path: Path to icon file (.ico, .icns, .png)
            on_quit: Optional callback before quitting
            on_restore: Optional callback on restore
            notifier: Optional notification manager
            logger: Optional logger
            is_updating_checker: Callable that returns True if update is in progress
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

        self._icon = pystray.Icon(
            name=self.tray_name,
            icon=image,
            title=self.app_name,
            menu=menu,
        )

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
            menu_items.append(
                pystray.MenuItem(
                    f"About {self.app_name}",
                    self._on_about
                )
            )
            menu_items.append(pystray.Menu.SEPARATOR)

        # Restore option
        menu_items.append(
            pystray.MenuItem(
                "Restore",
                self._on_restore_menu,
                default=True
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Platform-specific additional items
        if self.platform == "win32":
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

    def _load_icon(self):
        """Load icon with platform-specific handling."""
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                return self._process_icon_for_platform(self.icon_path)
            except Exception as e:
                self._log(f"Failed to load icon {self.icon_path}: {e}")

        found_icon = get_icon_path("icon")
        if found_icon and os.path.exists(found_icon):
            try:
                return self._process_icon_for_platform(found_icon)
            except Exception as e:
                self._log(f"Failed to load found icon {found_icon}: {e}")

        return self._create_fallback_icon()

    def _process_icon_for_platform(self, icon_path):
        """Process icon for specific platform requirements."""
        image = Image.open(icon_path)

        if self.platform == "darwin":
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            if image.width > 64 or image.height > 64:
                image = image.resize((32, 32), Image.Resampling.LANCZOS)

        elif self.platform.startswith("linux"):
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            if image.width > 48 or image.height > 48:
                image = image.resize((24, 24), Image.Resampling.LANCZOS)

        else:  # Windows
            if image.mode == 'P' and 'transparency' in image.info:
                image = image.convert('RGBA')
            elif image.mode == 'P':
                image = image.convert('RGB')
            if image.width > 32 or image.height > 32:
                image = image.resize((32, 32), Image.Resampling.LANCZOS)

        return image

    def _create_fallback_icon(self):
        """Create a simple fallback icon."""
        if self.platform == "darwin":
            size = 32
        elif self.platform.startswith("linux"):
            size = 24
        else:
            size = 32

        dark_mode = is_dark_mode()

        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        primary_color = "#01a78d"
        text_color = "#ffffff"

        padding = 4
        draw.ellipse(
            (padding, padding, size - padding, size - padding),
            fill=primary_color
        )

        # Add "WT" text
        try:
            font_size = size // 2
            font = ImageFont.truetype("arial.ttf", font_size)
            draw.text((size//2 - font_size//2, size//2 - font_size//2), "WT",
                     fill=text_color, font=font)
        except:
            # Fallback to simple text
            draw.text((size//2 - 8, size//2 - 8), "WT", fill=text_color)

        return image

    def _on_restore_menu(self, icon=None, item=None):
        """Handle restore from menu."""
        self.restore()

    def _on_quit_menu(self, icon=None, item=None):
        """Handle quit from menu."""
        self.quit()

    def _on_about(self, icon=None, item=None):
        """Handle about menu item."""
        try:
            from tkinter import messagebox
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()

            messagebox.showinfo(
                f"About {self.app_name}",
                f"{self.app_name}\nVersion: 1.0.1\n\n"
                "Cross-platform desktop application\n"
                "© 2026 WorkTre. All rights reserved."
            )

            root.destroy()
        except Exception as e:
            self._log(f"Error showing about dialog: {e}")

    def _on_settings(self, icon=None, item=None):
        """Handle settings menu item."""
        self._log("Settings menu clicked")
        self.restore()

    def restore(self):
        """Restore window from tray."""
        window = self.window_getter()
        if window:
            try:
                window.show()
                window.restore()

                if self.platform == "win32":
                    try:
                        window.bring_to_front()
                        window.focus()
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
                    if self.platform == "darwin":
                        message = f"{self.app_name} is running in the menu bar"
                    elif self.platform.startswith("linux"):
                        message = f"{self.app_name} is running in the system tray"
                    else:
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

    def notify(self, message, title=None):
        """Show a tray notification."""
        if self._icon:
            try:
                self._icon.notify(message, title or self.app_name)
                self._log(f"Tray notification shown: {message}")
            except Exception as e:
                self._log(f"Failed to show tray notification: {e}")

    def quit(self):
        """Quit application with confirmation."""
        if self.is_updating_checker and self.is_updating_checker():
            show_confirmation_dialog(
                "Update in progress",
                f"{self.app_name} is currently updating. Please wait."
            )
            return

        window = self.window_getter()
        
        # Use pywebview's built-in dialog if window is available, 
        # as it handles focus and parenting much better than a standalone dialog.
        if window:
            try:
                # Restore window to ensure the dialog is visible and focused
                window.show()
                window.restore()
                
                confirmed = window.create_confirmation_dialog(
                    f"Quit {self.app_name}",
                    f"Are you sure you want to quit {self.app_name}?"
                )
            except Exception as e:
                self._log(f"Built-in dialog failed: {e}")
                confirmed = show_confirmation_dialog(
                    f"Quit {self.app_name}",
                    f"Are you sure you want to quit {self.app_name}?"
                )
        else:
            confirmed = show_confirmation_dialog(
                f"Quit {self.app_name}",
                f"Are you sure you want to quit {self.app_name}?"
            )

        if not confirmed:
            self._log("User canceled quit")
            return

        self._log("User confirmed quit")

        if self.on_quit:
            self.on_quit()

        self.stop()

        import os
        os._exit(0)

    def stop(self):
        """Stop tray icon."""
        if self._icon:
            try:
                self._icon.stop()
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=1.0)
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


def create_tray_manager(app_name, window_getter, **kwargs):
    """
    Factory function to create platform-appropriate tray manager.

    Args:
        app_name: Application name
        window_getter: Callable that returns the current window
        **kwargs: Additional arguments for the tray manager

    Returns:
        Platform-specific tray manager instance
    """
    platform = sys.platform

    if platform == "win32":
        from .windows import WindowsTrayManager
        return WindowsTrayManager(app_name, window_getter, **kwargs)
    elif platform == "darwin":
        from .macos import MacTrayManager
        return MacTrayManager(app_name, window_getter, **kwargs)
    else:  # Linux and other Unix-like
        from .linux import LinuxTrayManager
        return LinuxTrayManager(app_name, window_getter, **kwargs)