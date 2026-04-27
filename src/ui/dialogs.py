"""
src/ui/dialogs.py
Complete dialog boxes for the WorkTre Desktop Application.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional, Any, Dict, List, Tuple, Callable
import webbrowser
from datetime import datetime
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import constants
from src.platform.utils import get_icon_path

# Try to import PIL for image support in dialogs
try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from ..config import constants
from ..platform.utils import get_icon_path


class DialogStyle:
    """Dialog styling constants."""

    # Colors
    PRIMARY = "#01a78d"
    PRIMARY_DARK = "#017a68"
    SECONDARY = "#002f34"
    SUCCESS = "#27ae60"
    WARNING = "#f39c12"
    ERROR = "#e74c3c"
    INFO = "#3498db"
    LIGHT = "#f8f9fa"
    DARK = "#2c3e50"
    WHITE = "#ffffff"
    GRAY = "#95a5a6"
    LIGHT_GRAY = "#ecf0f1"

    # Fonts
    TITLE_FONT = ("Segoe UI", 14, "bold")
    HEADER_FONT = ("Segoe UI", 12, "bold")
    NORMAL_FONT = ("Segoe UI", 10)
    SMALL_FONT = ("Segoe UI", 9)

    # Dimensions
    PADDING = 20
    BUTTON_WIDTH = 100
    BUTTON_HEIGHT = 30

    @classmethod
    def get_icon_path(cls, icon_name: str) -> Optional[str]:
        """Get path to dialog icon."""
        try:
            return get_icon_path(icon_name)
        except:
            return None


class BaseDialog:
    """Base class for custom dialogs."""

    def __init__(self, parent: Optional[Any] = None, title: str = "WorkTre"):
        self.parent = parent
        self.title = title
        self.result = None

        # Create dialog window
        if parent is None:
            self.root = tk.Tk()
            self.root.withdraw()
            self.dialog = tk.Toplevel(self.root)
        else:
            self.dialog = tk.Toplevel(parent)

        self.dialog.title(title)
        self.dialog.configure(bg=DialogStyle.WHITE)
        self.dialog.resizable(False, False)

        # Make dialog modal
        self.dialog.transient(parent if parent else self.root)
        self.dialog.grab_set()

        # Center the dialog
        self._center_window()

        # Main container
        self.main_frame = ttk.Frame(self.dialog, padding=DialogStyle.PADDING)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

    def _center_window(self):
        """Center dialog on screen or parent."""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()

        if self.parent:
            x = self.parent.winfo_rootx() + (self.parent.winfo_width() - width) // 2
            y = self.parent.winfo_rooty() + (self.parent.winfo_height() - height) // 2
        else:
            x = (self.dialog.winfo_screenwidth() - width) // 2
            y = (self.dialog.winfo_screenheight() - height) // 2

        self.dialog.geometry(f'{width}x{height}+{x}+{y}')

    def _create_button(self, parent: Any, text: str, command: callable,
                       style: str = "normal", **kwargs) -> ttk.Button:
        """Create styled button."""
        btn = ttk.Button(parent, text=text, command=command, **kwargs)

        # Apply custom styling
        style_name = f"{style}.TButton"

        # Configure button style
        style = ttk.Style()

        if style == "accent":
            style.configure(style_name,
                            background=DialogStyle.PRIMARY,
                            foreground=DialogStyle.WHITE,
                            font=DialogStyle.NORMAL_FONT,
                            padding=(10, 5))
            style.map(style_name,
                      background=[('active', DialogStyle.PRIMARY_DARK),
                                  ('pressed', DialogStyle.SECONDARY)],
                      foreground=[('active', DialogStyle.WHITE)])
        elif style == "danger":
            style.configure(style_name,
                            background=DialogStyle.ERROR,
                            foreground=DialogStyle.WHITE,
                            font=DialogStyle.NORMAL_FONT,
                            padding=(10, 5))
            style.map(style_name,
                      background=[('active', '#c0392b'),
                                  ('pressed', '#a93226')],
                      foreground=[('active', DialogStyle.WHITE)])
        else:
            style.configure(style_name,
                            background=DialogStyle.LIGHT_GRAY,
                            foreground=DialogStyle.DARK,
                            font=DialogStyle.NORMAL_FONT,
                            padding=(10, 5))
            style.map(style_name,
                      background=[('active', DialogStyle.GRAY),
                                  ('pressed', DialogStyle.DARK)],
                      foreground=[('active', DialogStyle.WHITE),
                                  ('pressed', DialogStyle.WHITE)])

        btn.configure(style=style_name)
        return btn

    def show(self) -> Any:
        """Show dialog and wait for result."""
        self.dialog.wait_window()
        if hasattr(self, 'root'):
            self.root.destroy()
        return self.result


# ==================== STANDARD DIALOGS ====================

def show_error_dialog(title: str, message: str, parent: Any = None,
                      details: Optional[str] = None) -> None:
    """
    Show error dialog with optional details.

    Args:
        title: Dialog title
        message: Error message
        parent: Parent window (optional)
        details: Detailed error information (optional)
    """
    root = tk.Tk() if parent is None else parent

    try:
        if parent is None:
            root.withdraw()

        if details:
            # Custom dialog with details expander
            dialog = tk.Toplevel(root)
            dialog.title(title)
            dialog.geometry("500x400")
            dialog.resizable(False, False)
            dialog.configure(bg=DialogStyle.WHITE)

            # Center window
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
            y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
            dialog.geometry(f'+{x}+{y}')

            # Main frame
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Error icon
            icon_label = ttk.Label(main_frame, text="❌", font=("Segoe UI", 48))
            icon_label.pack(pady=(0, 10))

            # Title
            title_label = ttk.Label(main_frame, text=title,
                                    font=DialogStyle.HEADER_FONT,
                                    foreground=DialogStyle.ERROR)
            title_label.pack(pady=(0, 10))

            # Message
            msg_label = ttk.Label(main_frame, text=message,
                                  font=DialogStyle.NORMAL_FONT,
                                  wraplength=400, justify="center")
            msg_label.pack(pady=(0, 20))

            # Details expander
            details_frame = ttk.Frame(main_frame)
            details_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

            show_details = tk.BooleanVar(value=False)

            def toggle_details():
                if show_details.get():
                    details_text.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
                    toggle_btn.config(text="▼ Hide Details")
                else:
                    details_text.pack_forget()
                    toggle_btn.config(text="▶ Show Details")

            toggle_btn = ttk.Button(details_frame, text="▶ Show Details",
                                    command=toggle_details)
            toggle_btn.pack()

            # Details text area
            details_text = tk.Text(details_frame, height=8, wrap=tk.WORD,
                                   font=("Consolas", 9))
            details_text.insert(tk.END, details)
            details_text.config(state=tk.DISABLED)

            # Scrollbar for details
            scrollbar = ttk.Scrollbar(details_frame, orient=tk.VERTICAL,
                                      command=details_text.yview)
            details_text.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Button frame
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)

            ok_btn = ttk.Button(button_frame, text="OK",
                                command=dialog.destroy)
            ok_btn.pack(side=tk.RIGHT)

            dialog.transient(parent if parent else root)
            dialog.grab_set()
            dialog.wait_window()

        else:
            # Standard messagebox
            messagebox.showerror(title, message, parent=root)

    finally:
        if parent is None:
            root.destroy()


def show_info_dialog(title: str, message: str, parent: Any = None) -> None:
    """
    Show information dialog.

    Args:
        title: Dialog title
        message: Information message
        parent: Parent window (optional)
    """
    root = tk.Tk() if parent is None else parent

    try:
        if parent is None:
            root.withdraw()
        messagebox.showinfo(title, message, parent=root)
    finally:
        if parent is None:
            root.destroy()


def show_warning_dialog(title: str, message: str, parent: Any = None,
                        details: Optional[str] = None) -> None:
    """
    Show warning dialog.

    Args:
        title: Dialog title
        message: Warning message
        parent: Parent window (optional)
        details: Detailed warning information (optional)
    """
    root = tk.Tk() if parent is None else parent

    try:
        if parent is None:
            root.withdraw()

        if details:
            # Custom warning dialog with details
            dialog = tk.Toplevel(root)
            dialog.title(title)
            dialog.geometry("500x400")
            dialog.resizable(False, False)
            dialog.configure(bg=DialogStyle.WHITE)

            # Center window
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
            y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
            dialog.geometry(f'+{x}+{y}')

            # Main frame
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Warning icon
            icon_label = ttk.Label(main_frame, text="⚠️", font=("Segoe UI", 48))
            icon_label.pack(pady=(0, 10))

            # Title
            title_label = ttk.Label(main_frame, text=title,
                                    font=DialogStyle.HEADER_FONT,
                                    foreground=DialogStyle.WARNING)
            title_label.pack(pady=(0, 10))

            # Message
            msg_label = ttk.Label(main_frame, text=message,
                                  font=DialogStyle.NORMAL_FONT,
                                  wraplength=400, justify="center")
            msg_label.pack(pady=(0, 20))

            # Details
            details_label = ttk.Label(main_frame, text=details,
                                      font=DialogStyle.SMALL_FONT,
                                      foreground=DialogStyle.GRAY,
                                      wraplength=400, justify="left")
            details_label.pack(pady=(0, 20))

            # Button frame
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)

            ok_btn = ttk.Button(button_frame, text="OK",
                                command=dialog.destroy)
            ok_btn.pack(side=tk.RIGHT)

            dialog.transient(parent if parent else root)
            dialog.grab_set()
            dialog.wait_window()
        else:
            messagebox.showwarning(title, message, parent=root)

    finally:
        if parent is None:
            root.destroy()


def show_confirmation_dialog(title: str, message: str, parent: Any = None,
                             default: bool = False,
                             show_cancel: bool = False) -> bool:
    """
    Show confirmation dialog.

    Args:
        title: Dialog title
        message: Confirmation message
        parent: Parent window (optional)
        default: Default value (True for Yes, False for No)
        show_cancel: Whether to show Cancel button

    Returns:
        True if user confirmed, False otherwise
    """
    root = tk.Tk() if parent is None else parent

    try:
        if parent is None:
            root.withdraw()

        if show_cancel:
            # Custom dialog with Cancel button
            dialog = tk.Toplevel(root)
            dialog.title(title)
            dialog.geometry("450x200")
            dialog.resizable(False, False)
            dialog.configure(bg=DialogStyle.WHITE)

            # Center window
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
            y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
            dialog.geometry(f'+{x}+{y}')

            # Main frame
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Question icon
            icon_label = ttk.Label(main_frame, text="❓", font=("Segoe UI", 48))
            icon_label.pack(pady=(0, 10))

            # Message
            msg_label = ttk.Label(main_frame, text=message,
                                  font=DialogStyle.NORMAL_FONT,
                                  wraplength=400, justify="center")
            msg_label.pack(pady=(0, 20))

            # Button frame
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)

            result = {"value": default}

            def on_yes():
                result["value"] = True
                dialog.destroy()

            def on_no():
                result["value"] = False
                dialog.destroy()

            def on_cancel():
                result["value"] = None
                dialog.destroy()

            yes_btn = ttk.Button(button_frame, text="Yes",
                                 command=on_yes)
            yes_btn.pack(side=tk.RIGHT, padx=(10, 0))

            no_btn = ttk.Button(button_frame, text="No",
                                command=on_no)
            no_btn.pack(side=tk.RIGHT, padx=(10, 0))

            if show_cancel:
                cancel_btn = ttk.Button(button_frame, text="Cancel",
                                        command=on_cancel)
                cancel_btn.pack(side=tk.RIGHT)

            dialog.transient(parent if parent else root)
            dialog.grab_set()
            dialog.wait_window()

            return result["value"] if result["value"] is not None else False
        else:
            return messagebox.askyesno(title, message, parent=root)

    finally:
        if parent is None:
            root.destroy()


def show_input_dialog(title: str, prompt: str, parent: Any = None,
                      initial_value: str = "",
                      password: bool = False) -> Optional[str]:
    """
    Show input dialog.

    Args:
        title: Dialog title
        prompt: Prompt message
        parent: Parent window (optional)
        initial_value: Initial value for input
        password: Whether input is password (masked)

    Returns:
        User input or None if cancelled
    """
    root = tk.Tk() if parent is None else parent

    try:
        if parent is None:
            root.withdraw()

        if password:
            # Custom password dialog
            dialog = tk.Toplevel(root)
            dialog.title(title)
            dialog.geometry("400x200")
            dialog.resizable(False, False)
            dialog.configure(bg=DialogStyle.WHITE)

            # Center window
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
            y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
            dialog.geometry(f'+{x}+{y}')

            # Main frame
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Prompt
            prompt_label = ttk.Label(main_frame, text=prompt,
                                     font=DialogStyle.NORMAL_FONT)
            prompt_label.pack(anchor=tk.W, pady=(0, 5))

            # Password entry
            password_var = tk.StringVar(value=initial_value)
            password_entry = ttk.Entry(main_frame, textvariable=password_var,
                                       show="•", font=("Consolas", 11))
            password_entry.pack(fill=tk.X, pady=(0, 20))
            password_entry.focus_set()
            password_entry.select_range(0, tk.END)

            # Button frame
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)

            result = {"value": None}

            def on_ok():
                result["value"] = password_var.get()
                dialog.destroy()

            def on_cancel():
                dialog.destroy()

            ok_btn = ttk.Button(button_frame, text="OK",
                                command=on_ok)
            ok_btn.pack(side=tk.RIGHT, padx=(10, 0))

            cancel_btn = ttk.Button(button_frame, text="Cancel",
                                    command=on_cancel)
            cancel_btn.pack(side=tk.RIGHT)

            # Bind Enter key
            dialog.bind('<Return>', lambda e: on_ok())
            dialog.bind('<Escape>', lambda e: on_cancel())

            dialog.transient(parent if parent else root)
            dialog.grab_set()
            dialog.wait_window()

            return result["value"]
        else:
            return simpledialog.askstring(title, prompt, parent=root,
                                          initialvalue=initial_value)

    finally:
        if parent is None:
            root.destroy()


# ==================== CUSTOM DIALOGS ====================

class UpdateDialog(BaseDialog):
    """Professional update dialog."""

    def __init__(self, current_version: str, latest_version: str,
                 changelog: str = "", parent: Optional[Any] = None):

        # Handle None parent gracefully
        if parent is None:
            # Create a temporary root
            self.temp_root = tk.Tk()
            self.temp_root.withdraw()
            parent = self.temp_root

        super().__init__(parent, "Update Available")
        self.current_version = current_version
        self.latest_version = latest_version
        self.changelog = changelog
        self.result = False
        self.temp_root = getattr(self, 'temp_root', None)

        self._build_ui()
        self._center_window()

    def __del__(self):
        """Cleanup temp root if created."""
        if hasattr(self, 'temp_root') and self.temp_root:
            try:
                self.temp_root.destroy()
            except:
                pass

    def _build_ui(self):
        """Build update dialog UI."""
        self.dialog.geometry("550x500")

        # Header with gradient effect
        header_frame = tk.Frame(self.main_frame, bg=DialogStyle.PRIMARY,
                                height=80)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        header_frame.pack_propagate(False)

        # Logo or icon
        icon_label = tk.Label(header_frame, text="🔄", font=("Segoe UI", 32),
                              bg=DialogStyle.PRIMARY, fg=DialogStyle.WHITE)
        icon_label.pack(side=tk.LEFT, padx=20)

        # Title
        title_label = tk.Label(header_frame, text="Update Available",
                               font=("Segoe UI", 18, "bold"),
                               bg=DialogStyle.PRIMARY, fg=DialogStyle.WHITE)
        title_label.pack(side=tk.LEFT, padx=10)

        # Version info card
        version_frame = ttk.Frame(self.main_frame)
        version_frame.pack(fill=tk.X, pady=(0, 20))

        # Current version
        current_card = ttk.Frame(version_frame, relief=tk.GROOVE, padding=15)
        current_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        ttk.Label(current_card, text="Current Version",
                  font=DialogStyle.SMALL_FONT,
                  foreground=DialogStyle.GRAY).pack()
        ttk.Label(current_card, text=f"v{self.current_version}",
                  font=("Segoe UI", 16, "bold"),
                  foreground=DialogStyle.ERROR).pack()

        # Latest version
        latest_card = ttk.Frame(version_frame, relief=tk.GROOVE, padding=15)
        latest_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        ttk.Label(latest_card, text="Latest Version",
                  font=DialogStyle.SMALL_FONT,
                  foreground=DialogStyle.GRAY).pack()
        ttk.Label(latest_card, text=f"v{self.latest_version}",
                  font=("Segoe UI", 16, "bold"),
                  foreground=DialogStyle.SUCCESS).pack()

        # Changelog section
        if self.changelog:
            ttk.Label(self.main_frame, text="What's New:",
                      font=DialogStyle.HEADER_FONT).pack(anchor=tk.W, pady=(0, 10))

            # Scrollable changelog
            changelog_frame = ttk.Frame(self.main_frame)
            changelog_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

            scrollbar = ttk.Scrollbar(changelog_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            changelog_text = tk.Text(changelog_frame, height=10,
                                     font=("Segoe UI", 10),
                                     wrap=tk.WORD,
                                     yscrollcommand=scrollbar.set,
                                     relief=tk.FLAT,
                                     borderwidth=1,
                                     padx=10, pady=10)
            changelog_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            changelog_text.insert(tk.END, self.changelog)
            changelog_text.config(state=tk.DISABLED)

            scrollbar.config(command=changelog_text.yview)

        # Release notes link
        link_frame = ttk.Frame(self.main_frame)
        link_frame.pack(fill=tk.X, pady=(0, 20))

        link_label = tk.Label(link_frame,
                              text="View full release notes",
                              font=DialogStyle.SMALL_FONT,
                              fg=DialogStyle.INFO,
                              cursor="hand2")
        link_label.pack()
        link_label.bind("<Button-1>",
                        lambda e: webbrowser.open("https://github.com/WorkTre/WorkTre-Desktop-App/releases"))
        link_label.bind("<Enter>", lambda e: link_label.configure(fg=DialogStyle.PRIMARY_DARK))
        link_label.bind("<Leave>", lambda e: link_label.configure(fg=DialogStyle.INFO))

        # Button frame
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X)

        # Later button
        later_btn = self._create_button(button_frame, "Later",
                                        self._on_later, "normal")
        later_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Update now button (accent)
        update_btn = self._create_button(button_frame, "Update Now",
                                         self._on_update, "accent")
        update_btn.pack(side=tk.RIGHT)

        # Make window modal
        self.dialog.transient(self.parent if self.parent else self.root)
        self.dialog.grab_set()

    def _on_update(self):
        self.result = True
        self.dialog.destroy()

    def _on_later(self):
        self.result = False
        self.dialog.destroy()


class ProgressDialog(BaseDialog):
    """Progress dialog with detailed status."""

    def __init__(self, parent: Optional[Any] = None,
                 title: str = "Progress",
                 message: str = "Processing...",
                 maximum: int = 100,
                 indeterminate: bool = False):
        # Handle None parent gracefully
        if parent is None:
            # Create a temporary root
            self.temp_root = tk.Tk()
            self.temp_root.withdraw()
            parent = self.temp_root

        super().__init__(parent, title)
        self.message = message
        self.maximum = maximum
        self.indeterminate = indeterminate
        self._cancelled = False
        self.temp_root = getattr(self, 'temp_root', None)
        self._build_ui()

    def __del__(self):
        """Cleanup temp root if created."""
        if hasattr(self, 'temp_root') and self.temp_root:
            try:
                self.temp_root.destroy()
            except:
                pass

    def _build_ui(self):
        """Build progress dialog UI."""
        self.dialog.geometry("450x200")
        self.dialog.resizable(False, False)

        # Icon
        icon_label = ttk.Label(self.main_frame, text="⏳", font=("Segoe UI", 48))
        icon_label.pack(pady=(0, 10))

        # Message
        self.message_label = ttk.Label(self.main_frame, text=self.message,
                                       font=DialogStyle.NORMAL_FONT,
                                       wraplength=400)
        self.message_label.pack(pady=(0, 10))

        # Progress bar
        if self.indeterminate:
            self.progress = ttk.Progressbar(self.main_frame,
                                            mode='indeterminate',
                                            length=350)
            self.progress.pack(pady=(0, 10))
            self.progress.start(10)
        else:
            self.progress = ttk.Progressbar(self.main_frame,
                                            mode='determinate',
                                            length=350,
                                            maximum=self.maximum)
            self.progress.pack(pady=(0, 10))

        # Percentage label
        self.percent_label = ttk.Label(self.main_frame, text="0%",
                                       font=DialogStyle.SMALL_FONT,
                                       foreground=DialogStyle.GRAY)
        self.percent_label.pack()

        # Status label
        self.status_label = ttk.Label(self.main_frame, text="",
                                      font=DialogStyle.SMALL_FONT,
                                      foreground=DialogStyle.GRAY)
        self.status_label.pack(pady=(5, 0))

        # Cancel button
        self.cancel_btn = self._create_button(self.main_frame, "Cancel",
                                              self._on_cancel, "danger")
        self.cancel_btn.pack(pady=(20, 0))

    def _on_cancel(self):
        self._cancelled = True
        self.cancel_btn.config(state=tk.DISABLED, text="Cancelling...")

    def update_progress(self, value: int, status: Optional[str] = None):
        """Update progress value and status."""
        if self._cancelled:
            return

        self.progress['value'] = value
        percent = (value / self.maximum) * 100
        self.percent_label.config(text=f"{percent:.1f}%")

        if status:
            self.status_label.config(text=status)

        self.dialog.update()

    def update_message(self, message: str):
        """Update main message."""
        self.message_label.config(text=message)
        self.dialog.update()

    def is_cancelled(self) -> bool:
        """Check if user cancelled the operation."""
        return self._cancelled


class AboutDialog(BaseDialog):
    """About dialog with application information."""

    def __init__(self, parent: Optional[Any] = None,
                 app_name: str = "WorkTre",
                 version: str = "1.0.1",
                 copyright_year: str = "2026"):
        super().__init__(parent, f"About {app_name}")
        self.app_name = app_name
        self.version = version
        self.copyright_year = copyright_year
        self._build_ui()

    def _build_ui(self):
        """Build about dialog UI."""
        self.dialog.geometry("500x600")

        # Logo
        logo_frame = ttk.Frame(self.main_frame)
        logo_frame.pack(pady=(0, 20))

        # Try to load logo image
        if PIL_AVAILABLE:
            try:
                logo_path = get_icon_path("icon")
                if logo_path and os.path.exists(logo_path):
                    img = Image.open(logo_path)
                    img = img.resize((96, 96), Image.Resampling.LANCZOS)
                    logo_img = ImageTk.PhotoImage(img)
                    logo_label = ttk.Label(logo_frame, image=logo_img)
                    logo_label.image = logo_img  # Keep reference
                    logo_label.pack()
                else:
                    ttk.Label(logo_frame, text="🏢", font=("Segoe UI", 64)).pack()
            except:
                ttk.Label(logo_frame, text="🏢", font=("Segoe UI", 64)).pack()
        else:
            ttk.Label(logo_frame, text="🏢", font=("Segoe UI", 64)).pack()

        # App name
        ttk.Label(self.main_frame, text=self.app_name,
                  font=("Segoe UI", 20, "bold"),
                  foreground=DialogStyle.PRIMARY).pack()

        # Version
        ttk.Label(self.main_frame, text=f"Version {self.version}",
                  font=DialogStyle.HEADER_FONT,
                  foreground=DialogStyle.GRAY).pack(pady=(5, 20))

        # Separator
        ttk.Separator(self.main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Info frame
        info_frame = ttk.Frame(self.main_frame)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        info_items = [
            ("📝", "Description", "WorkTre Desktop Application"),
            ("👥", "Author", "WorkTre Team"),
            ("📅", "Copyright", f"© {self.copyright_year} WorkTre. All rights reserved."),
            ("🔧", "Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
            ("🖥️", "Platform", f"{sys.platform} {sys.version_info.releaselevel}"),
        ]

        for icon, label, value in info_items:
            item_frame = ttk.Frame(info_frame)
            item_frame.pack(fill=tk.X, pady=5)

            ttk.Label(item_frame, text=icon,
                      font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Label(item_frame, text=label,
                      font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(item_frame, text=value,
                      font=("Segoe UI", 10)).pack(side=tk.LEFT)

        # Separator
        ttk.Separator(self.main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=20)

        # Links frame
        links_frame = ttk.Frame(self.main_frame)
        links_frame.pack(fill=tk.X, pady=(0, 20))

        def open_github():
            webbrowser.open("https://github.com/WorkTre/WorkTre-Desktop-App")

        def open_website():
            webbrowser.open("https://worktre.com")

        # GitHub link
        github_link = tk.Label(links_frame, text="GitHub Repository",
                               font=DialogStyle.SMALL_FONT,
                               fg=DialogStyle.INFO,
                               cursor="hand2")
        github_link.pack(side=tk.LEFT, padx=10)
        github_link.bind("<Button-1>", lambda e: open_github())
        github_link.bind("<Enter>", lambda e: github_link.configure(fg=DialogStyle.PRIMARY_DARK))
        github_link.bind("<Leave>", lambda e: github_link.configure(fg=DialogStyle.INFO))

        # Separator
        ttk.Label(links_frame, text="|").pack(side=tk.LEFT)

        # Website link
        website_link = tk.Label(links_frame, text="WorkTre.com",
                                font=DialogStyle.SMALL_FONT,
                                fg=DialogStyle.INFO,
                                cursor="hand2")
        website_link.pack(side=tk.LEFT, padx=10)
        website_link.bind("<Button-1>", lambda e: open_website())
        website_link.bind("<Enter>", lambda e: website_link.configure(fg=DialogStyle.PRIMARY_DARK))
        website_link.bind("<Leave>", lambda e: website_link.configure(fg=DialogStyle.INFO))

        # Close button
        close_btn = self._create_button(self.main_frame, "Close",
                                        self.dialog.destroy, "accent")
        close_btn.pack(pady=(20, 0))


class SettingsDialog(BaseDialog):
    """Settings dialog for application preferences."""

    def __init__(self, parent: Optional[Any] = None,
                 settings: Optional[Dict[str, Any]] = None):
        super().__init__(parent, "Settings")
        self.settings = settings or {}
        self.result = {}
        self._build_ui()

    def _build_ui(self):
        """Build settings dialog UI."""
        self.dialog.geometry("600x500")

        # Notebook for tabs
        notebook = ttk.Notebook(self.main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

        # General tab
        general_frame = ttk.Frame(notebook, padding=20)
        notebook.add(general_frame, text="General")
        self._build_general_tab(general_frame)

        # Notifications tab
        notifications_frame = ttk.Frame(notebook, padding=20)
        notebook.add(notifications_frame, text="Notifications")
        self._build_notifications_tab(notifications_frame)

        # Inactivity tab
        inactivity_frame = ttk.Frame(notebook, padding=20)
        notebook.add(inactivity_frame, text="Inactivity")
        self._build_inactivity_tab(inactivity_frame)

        # Button frame
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X)

        cancel_btn = self._create_button(button_frame, "Cancel",
                                         self._on_cancel, "normal")
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))

        save_btn = self._create_button(button_frame, "Save",
                                       self._on_save, "accent")
        save_btn.pack(side=tk.RIGHT)

    def _build_general_tab(self, parent):
        """Build general settings tab."""
        # Auto-start
        autostart_var = tk.BooleanVar(value=self.settings.get('autostart', False))
        ttk.Checkbutton(parent, text="Start WorkTre when system starts",
                        variable=autostart_var).pack(anchor=tk.W, pady=5)
        self.result['autostart'] = autostart_var

        # Minimize to tray
        minimize_var = tk.BooleanVar(value=self.settings.get('minimize_to_tray', True))
        ttk.Checkbutton(parent, text="Minimize to system tray when closed",
                        variable=minimize_var).pack(anchor=tk.W, pady=5)
        self.result['minimize_to_tray'] = minimize_var

        # Remember me
        remember_var = tk.BooleanVar(value=self.settings.get('remember_me', True))
        ttk.Checkbutton(parent, text="Remember me on startup",
                        variable=remember_var).pack(anchor=tk.W, pady=5)
        self.result['remember_me'] = remember_var

    def _build_notifications_tab(self, parent):
        """Build notifications settings tab."""
        # Enable notifications
        enable_var = tk.BooleanVar(value=self.settings.get('notifications_enabled', True))
        ttk.Checkbutton(parent, text="Enable desktop notifications",
                        variable=enable_var).pack(anchor=tk.W, pady=5)
        self.result['notifications_enabled'] = enable_var

        # Sound
        sound_var = tk.BooleanVar(value=self.settings.get('notification_sound', True))
        ttk.Checkbutton(parent, text="Play sound for notifications",
                        variable=sound_var).pack(anchor=tk.W, pady=5)
        self.result['notification_sound'] = sound_var

        # Duration
        ttk.Label(parent, text="Notification duration (seconds):",
                  font=DialogStyle.NORMAL_FONT).pack(anchor=tk.W, pady=(15, 5))

        duration_var = tk.IntVar(value=self.settings.get('notification_duration', 5))
        duration_spinbox = ttk.Spinbox(parent, from_=1, to=10,
                                       textvariable=duration_var,
                                       width=10)
        duration_spinbox.pack(anchor=tk.W)
        self.result['notification_duration'] = duration_var

    def _build_inactivity_tab(self, parent):
        """Build inactivity settings tab."""
        # Enable inactivity timer
        enable_var = tk.BooleanVar(value=self.settings.get('inactivity_enabled', True))
        ttk.Checkbutton(parent, text="Enable inactivity tracking",
                        variable=enable_var).pack(anchor=tk.W, pady=5)
        self.result['inactivity_enabled'] = enable_var

        # Warning time
        ttk.Label(parent, text="Show warning after (minutes):",
                  font=DialogStyle.NORMAL_FONT).pack(anchor=tk.W, pady=(15, 5))

        warn_var = tk.IntVar(value=self.settings.get('inactivity_warn', 5))
        warn_spinbox = ttk.Spinbox(parent, from_=1, to=30,
                                   textvariable=warn_var,
                                   width=10)
        warn_spinbox.pack(anchor=tk.W)
        self.result['inactivity_warn'] = warn_var

        # Logout time
        ttk.Label(parent, text="Logout after (minutes):",
                  font=DialogStyle.NORMAL_FONT).pack(anchor=tk.W, pady=(15, 5))

        logout_var = tk.IntVar(value=self.settings.get('inactivity_logout', 10))
        logout_spinbox = ttk.Spinbox(parent, from_=1, to=60,
                                     textvariable=logout_var,
                                     width=10)
        logout_spinbox.pack(anchor=tk.W)
        self.result['inactivity_logout'] = logout_var

    def _on_save(self):
        """Save settings and close dialog."""
        # Convert tkinter variables to values
        for key, var in self.result.items():
            if hasattr(var, 'get'):
                self.result[key] = var.get()

        self.dialog.destroy()

    def _on_cancel(self):
        """Cancel and close dialog."""
        self.result = None
        self.dialog.destroy()


# ==================== EXPORTS ====================

__all__ = [
    # Standard dialogs
    'show_error_dialog',
    'show_info_dialog',
    'show_warning_dialog',
    'show_confirmation_dialog',
    'show_input_dialog',

    # Custom dialogs
    'UpdateDialog',
    'ProgressDialog',
    'AboutDialog',
    'SettingsDialog',

    # Legacy compatibility
    'show_update_dialog',
]


# Legacy compatibility wrapper
def show_update_dialog(current_version: str, latest_version: str,
                       changelog: str = "", parent: Any = None) -> bool:
    """Legacy wrapper for UpdateDialog."""
    dialog = UpdateDialog(current_version, latest_version, changelog, parent)
    return dialog.show()
