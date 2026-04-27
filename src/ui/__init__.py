"""
src/ui/__init__.py
User interface components for WorkTre Desktop Application.
"""

from .window import AppWindow
from .dialogs import (
    # Standard dialogs
    show_error_dialog,
    show_info_dialog,
    show_warning_dialog,
    show_confirmation_dialog,
    show_input_dialog,

    # Custom dialogs
    UpdateDialog,
    ProgressDialog,
    AboutDialog,
    SettingsDialog,

    # Legacy compatibility
    show_update_dialog,
)

__all__ = [
    # Window
    'AppWindow',

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

    # Legacy
    'show_update_dialog',
]