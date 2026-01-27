import threading
import os
import sys
import pystray
from PIL import Image, ImageDraw

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MB_YESNO = 0x04
MB_ICONQUESTION = 0x20
MB_TASKMODAL = 0x2000
MB_TOPMOST = 0x40000

IDYES = 6


def force_foreground(hwnd):
    """
    Force a window to the foreground and give it input focus.
    """
    fg_thread = user32.GetWindowThreadProcessId(
        user32.GetForegroundWindow(), None
    )
    this_thread = kernel32.GetCurrentThreadId()

    # Temporarily attach input threads
    user32.AttachThreadInput(fg_thread, this_thread, True)

    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.SetFocus(hwnd)

    user32.AttachThreadInput(fg_thread, this_thread, False)


def windows_confirm(title, message):
    hwnd = user32.GetForegroundWindow()

    force_foreground(hwnd)

    result = user32.MessageBoxW(
        hwnd,
        message,
        title,
        MB_YESNO | MB_ICONQUESTION | MB_TASKMODAL | MB_TOPMOST
    )

    return result == IDYES


class TrayManager:
    def __init__(
            self,
            app_name: str,
            window_getter,
            icon_path: str = None,
            on_quit=None,
            on_restore=None,
            notifier=None,
            logger=None,
            is_updating_checker=None,  # ✅ NEW
    ):
        """
        :param app_name: App name shown in tray
        :param window_getter: Callable that returns the current pywebview window
        :param icon_path: Path to .ico or .png
        :param on_quit: Optional callback before quitting
        :param on_restore: Optional callback on restore
        :param notifier: Optional notification manager
        :param logger: Optional logger
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

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def start(self):
        """Start system tray icon (safe to call once)."""
        if self._running:
            return

        image = self._load_icon()
        menu = self._build_menu()

        self._icon = pystray.Icon(
            name=self.app_name.lower(),
            icon=image,
            title=self.app_name,
            menu=menu,
            on_activate=self._on_activate,  # ✅ THIS is the key
        )

        self._thread = threading.Thread(
            target=self._icon.run,
            daemon=True
        )
        self._thread.start()
        self._running = True

        self._log("Tray icon started")

    def stop(self):
        """Stop tray icon."""
        if self._icon:
            self._icon.stop()
            self._icon = None
            self._running = False
            self._log("Tray icon stopped")

    def minimize_to_tray(self, notify=True):
        """Hide window and keep app running."""
        window = self.window_getter()
        if window:
            window.hide()

        if notify and self.notifier:
            # Show startup notification
            self.notifier.add_notification(
                self.app_name,
                "WorkTre timer is running in background",
                "info",
                4
            )
            self.notifier.add_notification(
                self.app_name,
                "Application is running in the system tray",
                "info",
                4,
            )

        self._log("Minimized to tray")

    def restore(self):
        """Restore window from tray."""
        window = self.window_getter()
        if window:
            window.show()
            window.restore()

        if self.on_restore:
            self.on_restore()

        self._log("Window restored")

    def _on_activate(self, icon):
        """
        Called on tray icon double-click (Windows default action)
        """
        self.restore()

    def quit(self):
        window = self.window_getter()

        if not window:
            os._exit(0)

        # Block quit during update
        if self.is_updating_checker and self.is_updating_checker():
            windows_confirm(
                "Update in progress",
                "WorkTre is currently updating. Please wait."
            )
            return

        # IMPORTANT: window must be visible
        window.show()
        window.restore()

        confirmed = windows_confirm(
            "Quit WorkTre",
            "Are you sure you want to quit WorkTre?"
        )

        if not confirmed:
            self._log("User canceled quit")
            return

        self._log("User confirmed quit")
        self.stop()
        os._exit(0)

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                "Restore",
                self._on_restore,
                default=True  # ✅ THIS is the key
            ),
            pystray.MenuItem(
                "Quit",
                self._on_quit
            ),
        )

    def _on_restore(self, icon=None, item=None):
        self.restore()

    def _on_quit(self, icon=None, item=None):
        self.quit()

    def _load_icon(self):
        """Load app icon or generate fallback."""
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                return Image.open(self.icon_path)
            except Exception:
                pass

        # Fallback icon
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill="#01a78d")
        return image

    def _log(self, msg):
        if self.logger:
            self.logger.info(msg)
