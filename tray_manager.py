import threading
import os
import sys
import pystray
from PIL import Image, ImageDraw


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
        """Quit application cleanly."""
        self._log("Quitting application")

        try:
            if self.on_quit:
                self.on_quit()
        except Exception:
            pass

        self.stop()
        os._exit(0)

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Restore", self._on_restore),
            pystray.MenuItem("Quit", self._on_quit),
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
