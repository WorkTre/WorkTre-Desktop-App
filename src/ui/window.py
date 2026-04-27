"""
src/ui/window.py
Window management for the application.
"""

import sys
import os
import webview
import tkinter as tk
from pathlib import Path
from typing import Optional, Any, Callable

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.platform.utils import get_icon_path


class AppWindow:
    """Main application window manager."""

    def __init__(self, title: str, html_path: str, api: Any = None,
                 width: int = 1092, height: int = 650):
        """
        Initialize the application window.

        Args:
            title: Window title
            html_path: Path to HTML file
            api: JavaScript API object
            width: Window width
            height: Window height
        """
        self.title = title
        self.html_path = Path(html_path)
        self.api = api
        self.width = width
        self.height = height
        self.window: Optional[webview.Window] = None

        # Event handlers
        self._on_loaded_handlers: list[Callable] = []
        self._on_closing_handlers: list[Callable] = []

        if not self.html_path.exists():
            raise FileNotFoundError(f"HTML file not found: {html_path}")

    def create_window(self) -> webview.Window:
        """Create the main window."""
        # Get screen dimensions
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()

        # Calculate center position
        left = (screen_width - self.width) // 2
        top = (screen_height - self.height) // 2

        # Get GUI backend
        gui_backend = settings.PlatformSettings.get_gui_backend()

        # Create window
        self.window = webview.create_window(
            title=self.title,
            url=f"file://{self.html_path}",
            js_api=self.api,
            width=self.width,
            height=self.height,
            x=left,
            y=top,
            resizable=False,
            confirm_close=False,
        )

        # Setup event handlers
        self._setup_event_handlers()

        return self.window

    def _setup_event_handlers(self) -> None:
        """Setup window event handlers."""
        if not self.window:
            return

        # Loaded event
        def on_loaded():
            self.set_window_icon()
            for handler in self._on_loaded_handlers:
                try:
                    handler()
                except Exception as e:
                    print(f"Error in loaded handler: {e}")

        self.window.events.loaded += on_loaded

        # Closing event
        def on_closing():
            result = True
            for handler in self._on_closing_handlers:
                try:
                    handler_result = handler()
                    if handler_result is False:
                        result = False
                except Exception as e:
                    print(f"Error in closing handler: {e}")
            return result

        self.window.events.closing += on_closing

    def set_window_icon(self) -> None:
        """Set window icon based on platform."""
        if not self.window:
            return

        try:
            icon_path = get_icon_path("icon")
            if icon_path and Path(icon_path).exists():
                if self.window.gui == 'tkinter':
                    tk_window = self.window.gui.window
                    tk_window.iconbitmap(icon_path)

                    # Set window constraints
                    tk_window.resizable(False, False)
                    tk_window.maxsize(self.width, self.height)
                    tk_window.minsize(self.width, self.height)
        except Exception as e:
            print(f"Warning: Could not set window icon: {e}")

    def add_loaded_handler(self, handler: Callable) -> None:
        """Add handler for window loaded event."""
        self._on_loaded_handlers.append(handler)

    def add_closing_handler(self, handler: Callable) -> None:
        """Add handler for window closing event."""
        self._on_closing_handlers.append(handler)

    def evaluate_js(self, code: str) -> Optional[Any]:
        """Execute JavaScript code in the window."""
        if self.window:
            try:
                return self.window.evaluate_js(code)
            except Exception as e:
                print(f"Error executing JS: {e}")
        return None

    def show(self) -> None:
        """Show the window."""
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception as e:
                print(f"Error showing window: {e}")

    def hide(self) -> None:
        """Hide the window."""
        if self.window:
            try:
                self.window.hide()
            except Exception as e:
                print(f"Error hiding window: {e}")

    def restore(self) -> None:
        """Restore the window."""
        if self.window:
            try:
                self.window.restore()
            except Exception as e:
                print(f"Error restoring window: {e}")

    def bring_to_front(self) -> None:
        """Bring window to front."""
        if self.window:
            try:
                self.window.bring_to_front()
                self.window.focus()
            except Exception as e:
                print(f"Error bringing window to front: {e}")

    def destroy(self) -> None:
        """Destroy the window."""
        if self.window:
            try:
                self.window.destroy()
            except Exception as e:
                print(f"Error destroying window: {e}")

    def run(self, debug=False):  # Add debug parameter with default False
        """Run the window."""
        self.create_window()
        self.set_window_icon()

        # Start webview with debug option
        gui_backend = settings.PlatformSettings.get_gui_backend()
        webview.start(
            debug=debug,  # This enables the debug window
            gui=gui_backend,
            func=self.set_window_icon,
        )

    @property
    def events(self) -> Optional[Any]:
        """Get window events."""
        return self.window.events if self.window else None
