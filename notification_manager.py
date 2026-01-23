import sys
import threading
import time
import queue
import tkinter as tk
from tkinter import font as tkfont

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


class NotificationManager:
    """Manages all notifications with queuing and theming"""

    def __init__(self, app_name, window_getter=None, logger=None):
        """
        :param app_name: App name shown in notifications
        :param window_getter: Optional callable returning pywebview window
        :param logger: Optional logger
        """
        self.app_name = app_name
        self.window_getter = window_getter
        self.logger = logger
        self.notification_queue = queue.Queue()
        self.active_notifications = []
        self.is_running = False
        self.max_concurrent = 3
        self.notification_spacing = 100

        self._init_backend()

    def start(self):
        """Start the notification manager"""
        if not self.is_running:
            self.is_running = True
            thread = threading.Thread(target=self._worker, daemon=True)
            thread.start()
            self._log("Notification manager started")

    def stop(self):
        """Stop the notification manager"""
        self.is_running = False

    def notify(self, title, message, timeout=4):
        """
        Show a system notification safely from any thread.
        """
        threading.Thread(
            target=self._notify_internal,
            args=(title, message, timeout),
            daemon=True
        ).start()

    def add_notification(self, title, message, notification_type="info", duration=5):
        """Add a notification to the queue"""
        notification = {
            "title": title,
            "message": message,
            "type": notification_type,
            "duration": duration,
            "timestamp": time.time()
        }
        self.notification_queue.put(notification)
        self._log(f"Notification queued: {title}")

    def show_professional_notification(self, title, message, notification_type="info", duration=5):
        """Main function to show professional notifications"""
        # Determine notification category
        if "login" in title.lower() or "logged" in title.lower():
            category = "login"
        elif "break" in title.lower():
            category = "break"
        elif "connection" in title.lower() or "internet" in message.lower():
            category = "connection"
        elif "update" in title.lower():
            category = "update"
        else:
            category = notification_type

        # Add to notification manager
        self.add_notification(title, message, category, duration)

        # Also show in-app notification
        # show_notification(title, message, notification_type, duration * 1000)

    def show_combined_notification(self, title, message, notification_type="info", duration=3000, windows_duration=5):
        """Show both in-app and Windows notifications"""
        # Show professional Windows notification
        self.show_professional_notification(title, message, notification_type, windows_duration)

        # Show in-app notification
        # show_notification(title, message, notification_type, duration)

    def show_windows_notification(self, title, message, duration=5, notification_type="info"):
        """
        Show professional Windows notification matching WorkTre theme
        Types: success, info, warning, error
        """
        try:
            import tkinter as tk
            from tkinter import font as tkfont
            import threading

            def create_notification():
                # Create the notification window
                root = tk.Tk()
                root.title("WorkTre Notification")
                root.overrideredirect(True)  # Remove window decorations
                root.attributes('-topmost', True)
                root.attributes('-alpha', 0.95)

                # Get screen dimensions
                screen_width = root.winfo_screenwidth()
                screen_height = root.winfo_screenheight()

                # Position in bottom-right corner
                window_width = 350
                window_height = 120
                x = screen_width - window_width - 20
                y = screen_height - window_height - 50

                root.geometry(f"{window_width}x{window_height}+{x}+{y}")

                # Define colors based on notification type
                colors = {
                    "success": {
                        "bg": "#27ae60",
                        "light_bg": "#d5f4e6",
                        "icon": "#229954",
                        "accent": "#229954"
                    },
                    "info": {
                        "bg": "#3498db",
                        "light_bg": "#d6eaf8",
                        "icon": "#2980b9",
                        "accent": "#2980b9"
                    },
                    "warning": {
                        "bg": "#f39c12",
                        "light_bg": "#fdebd0",
                        "icon": "#e67e22",
                        "accent": "#e67e22"
                    },
                    "error": {
                        "bg": "#e74c3c",
                        "light_bg": "#fadbd8",
                        "icon": "#c0392b",
                        "accent": "#c0392b"
                    }
                }

                color_set = colors.get(notification_type, colors["info"])

                # Create gradient background frame
                main_frame = tk.Frame(
                    root,
                    bg=color_set["bg"],
                    highlightthickness=0
                )
                main_frame.pack(fill="both", expand=True)

                # Inner content frame
                content_frame = tk.Frame(
                    main_frame,
                    bg=color_set["light_bg"],
                    highlightthickness=0
                )
                content_frame.place(relx=0.02, rely=0.02, relwidth=0.96, relheight=0.96)

                # Icon frame (left side)
                icon_frame = tk.Frame(
                    content_frame,
                    bg=color_set["bg"],
                    width=60,
                    height=60
                )
                icon_frame.place(relx=0.05, rely=0.5, anchor="w", y=0)
                icon_frame.propagate(False)

                # Add icon based on type
                icons = {
                    "success": "✓",
                    "info": "ℹ",
                    "warning": "⚠",
                    "error": "✗"
                }

                icon_label = tk.Label(
                    icon_frame,
                    text=icons.get(notification_type, "ℹ"),
                    font=("Segoe UI", 24, "bold"),
                    fg="white",
                    bg=color_set["bg"]
                )
                icon_label.pack(expand=True)

                # Content area
                content_area = tk.Frame(
                    content_frame,
                    bg=color_set["light_bg"]
                )
                content_area.place(relx=0.25, rely=0.1, relwidth=0.7, relheight=0.8)

                # Title
                title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
                title_label = tk.Label(
                    content_area,
                    text=title,
                    font=title_font,
                    fg="#2c3e50",
                    bg=color_set["light_bg"],
                    anchor="w",
                    justify="left"
                )
                title_label.pack(fill="x", pady=(0, 5))

                # Message
                message_font = tkfont.Font(family="Segoe UI", size=10)
                message_label = tk.Label(
                    content_area,
                    text=message,
                    font=message_font,
                    fg="#5d6d7e",
                    bg=color_set["light_bg"],
                    anchor="w",
                    justify="left",
                    wraplength=220
                )
                message_label.pack(fill="x")

                # Close button
                close_btn = tk.Label(
                    content_frame,
                    text="✕",
                    font=("Segoe UI", 10),
                    fg="#95a5a6",
                    bg=color_set["light_bg"],
                    cursor="hand2"
                )
                close_btn.place(relx=0.95, rely=0.1, anchor="ne")

                def close_notification():
                    root.destroy()

                close_btn.bind("<Button-1>", lambda e: close_notification())

                # WorkTre branding
                brand_label = tk.Label(
                    content_frame,
                    text="WorkTre",
                    font=("Segoe UI", 8),
                    fg=color_set["accent"],
                    bg=color_set["light_bg"]
                )
                brand_label.place(relx=0.05, rely=0.9)

                # Progress bar (shows time remaining)
                progress_frame = tk.Frame(
                    content_frame,
                    bg="#e0e0e0",
                    height=3
                )
                progress_frame.place(relx=0.25, rely=0.95, relwidth=0.7)
                progress_frame.propagate(False)

                progress_bar = tk.Frame(
                    progress_frame,
                    bg=color_set["accent"],
                    width=0
                )
                progress_bar.place(relheight=1)

                # Animation for sliding in
                def slide_in():
                    for i in range(10):
                        try:
                            x = screen_width - window_width - 20
                            y = screen_height - window_height - 50 + (10 - i) * 5
                            root.geometry(f"{window_width}x{window_height}+{x}+{y}")
                            root.update()
                            time.sleep(0.02)
                        except:
                            break

                # Progress animation
                def update_progress(step):
                    try:
                        width = int(step * 0.7 * window_width / 100)
                        progress_bar.configure(width=width)
                        root.update()
                    except:
                        pass

                # Auto-close after duration
                def auto_close():
                    for i in range(100):
                        try:
                            update_progress(i)
                            time.sleep(duration / 100)
                        except:
                            break
                    try:
                        close_notification()
                    except:
                        pass

                # Start animations
                threading.Thread(target=slide_in, daemon=True).start()
                threading.Thread(target=auto_close, daemon=True).start()

                # Hover effects
                def on_enter(e):
                    try:
                        root.attributes('-alpha', 1.0)
                        progress_frame.configure(bg="#d0d0d0")
                    except:
                        pass

                def on_leave(e):
                    try:
                        root.attributes('-alpha', 0.95)
                        progress_frame.configure(bg="#e0e0e0")
                    except:
                        pass

                content_frame.bind("<Enter>", on_enter)
                content_frame.bind("<Leave>", on_leave)

                # Make window click-through (optional)
                try:
                    import ctypes
                    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
                    ctypes.windll.user32.SetWindowLongW(hwnd, -20, 0x80000 | 0x20)
                except:
                    pass

                root.mainloop()

            # Run notification in separate thread
            thread = threading.Thread(target=create_notification, daemon=True)
            thread.start()

            self.info(f"Professional Windows notification shown: {title}")

        except Exception as e:
            self.error(f"Error showing professional notification: {e}")
            # Fallback to simpler method
            self.show_simple_windows_notification(title, message, duration)

    def show_simple_windows_notification(title, message, duration=5):
        """Simple fallback notification"""
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0)
        except:
            pass  # Silently fail if all methods fail

    def show_combined_notification(self, title, message, notification_type="info", duration=3000, windows_duration=5):
        """
        Show both in-app notification and Windows toast notification
        """
        # Show in-app notification
        # show_notification(title, message, notification_type, duration)

        # Show Windows notification (for background/bring to attention)
        self.show_windows_notification(title, message, windows_duration)

    def _init_backend(self):
        self._backend = None

        if IS_WINDOWS:
            try:
                from win10toast import ToastNotifier
                self._backend = ToastNotifier()
                self._log("Using win10toast backend")
                return
            except Exception:
                pass

        # Fallback: pywebview dialog
        self._backend = "pywebview"
        self._log("Using pywebview notification fallback")

    def _notify_internal(self, title, message, timeout):
        try:
            # Windows native toast
            if IS_WINDOWS and self._backend != "pywebview":
                self._backend.show_toast(
                    self.app_name,
                    message,
                    duration=timeout,
                    threaded=True
                )
                return

            # pywebview fallback (non-blocking)
            window = self.window_getter() if self.window_getter else None
            if window:
                window.gui.invoke(
                    lambda: window.create_alert_dialog(
                        title=title,
                        message=message
                    )
                )

        except Exception as e:
            self._log(f"Notification failed: {e}")

    def _worker(self):
        """Worker thread to process notifications"""
        while self.is_running:
            try:
                # Limit concurrent notifications
                if len(self.active_notifications) < self.max_concurrent:
                    notification = self.notification_queue.get(timeout=0.5)
                    self._show_notification(notification)

                # Clean up old notifications
                self._cleanup_notifications()
                time.sleep(0.1)

            except queue.Empty:
                continue
            except Exception as e:
                self.error(f"Error in notification worker: {e}")
                time.sleep(1)

    def _show_notification(self, notification):
        """Show a single notification"""
        try:
            # Calculate position based on active notifications
            position = len(self.active_notifications)

            # Create notification window in separate thread
            thread = threading.Thread(
                target=self._create_notification_window,
                args=(notification, position),
                daemon=True
            )
            thread.start()

            # Track this notification
            self.active_notifications.append({
                "id": id(notification),
                "thread": thread,
                "start_time": time.time(),
                "duration": notification["duration"]
            })

        except Exception as e:
            self.error(f"Error showing notification: {e}")

    def _create_notification_window(self, notification, position):
        """Create the actual notification window"""
        try:
            import tkinter as tk
            from tkinter import font as tkfont

            # Window setup
            root = tk.Tk()
            root.title("WorkTre")
            root.overrideredirect(True)
            root.attributes('-topmost', True)
            root.attributes('-alpha', 0.0)  # Start invisible

            # Window size
            width = 350
            height = 100

            # Position (bottom-right, stacked)
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            x = screen_width - width - 20
            y = screen_height - (position + 1) * (height + 10) - 50

            root.geometry(f"{width}x{height}+{x}+{y}")

            # Define theme
            theme = self._get_theme(notification["type"])

            # Create gradient effect with frames
            self._create_styled_window(root, notification, theme)

            # Animate in
            self._animate_in(root)

            # Auto-close
            root.after(notification["duration"] * 1000, root.destroy)

            # Mouse hover handling
            self._setup_hover_effects(root, theme)

            root.mainloop()

        except Exception as e:
            self.error(f"Error creating notification window: {e}")

    def _get_theme(self, notification_type):
        """Get color theme for notification type"""
        themes = {
            "success": {
                "primary": "#27ae60",
                "secondary": "#2ecc71",
                "light": "#d5f4e6",
                "text": "#145a32",
                "icon": "✓"
            },
            "info": {
                "primary": "#3498db",
                "secondary": "#5dade2",
                "light": "#d6eaf8",
                "text": "#1b4f72",
                "icon": "ℹ"
            },
            "warning": {
                "primary": "#f39c12",
                "secondary": "#f7dc6f",
                "light": "#fdebd0",
                "text": "#7d6608",
                "icon": "⚠"
            },
            "error": {
                "primary": "#e74c3c",
                "secondary": "#ec7063",
                "light": "#fadbd8",
                "text": "#78281f",
                "icon": "✗"
            },
            "login": {
                "primary": "#9b59b6",
                "secondary": "#bb8fce",
                "light": "#e8daef",
                "text": "#512e5f",
                "icon": "👤"
            },
            "break": {
                "primary": "#1abc9c",
                "secondary": "#76d7c4",
                "light": "#d1f2eb",
                "text": "#0e6251",
                "icon": "☕"
            },
            "connection": {
                "primary": "#3498db",
                "secondary": "#5dade2",
                "light": "#d6eaf8",
                "text": "#1b4f72",
                "icon": "🌐"
            },
            "update": {
                "primary": "#e67e22",
                "secondary": "#f0b27a",
                "light": "#fef5e7",
                "text": "#784212",
                "icon": "🔄"
            }
        }
        return themes.get(notification_type, themes["info"])

    def _create_styled_window(self, root, notification, theme):
        """Create styled notification window"""
        import tkinter as tk
        from tkinter import font as tkfont

        # Main container with shadow effect
        main_frame = tk.Frame(root, bg=theme["primary"], bd=0)
        main_frame.pack(fill="both", expand=True, padx=1, pady=1)

        # Content frame with rounded corners effect
        content_frame = tk.Frame(main_frame, bg="white", bd=0)
        content_frame.place(relx=0.01, rely=0.01, relwidth=0.98, relheight=0.98)

        # Left accent bar
        accent_frame = tk.Frame(content_frame, bg=theme["primary"], width=5)
        accent_frame.pack(side="left", fill="y")

        # Icon circle
        icon_canvas = tk.Canvas(
            content_frame,
            width=40,
            height=40,
            bg="white",
            highlightthickness=0
        )
        icon_canvas.place(relx=0.05, rely=0.5, anchor="w")

        # Draw icon circle
        icon_canvas.create_oval(
            5, 5, 35, 35,
            fill=theme["primary"],
            outline=theme["secondary"],
            width=2
        )

        # Draw icon text
        icon_canvas.create_text(
            20, 20,
            text=theme["icon"],
            font=("Segoe UI", 16, "bold"),
            fill="white"
        )

        # Content area
        text_frame = tk.Frame(content_frame, bg="white")
        text_frame.place(relx=0.25, rely=0.1, relwidth=0.68, relheight=0.8)

        # Title
        title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        title_label = tk.Label(
            text_frame,
            text=notification["title"],
            font=title_font,
            fg="#2c3e50",
            bg="white",
            anchor="w"
        )
        title_label.pack(fill="x", pady=(0, 2))

        # Message
        message_font = tkfont.Font(family="Segoe UI", size=9)
        message_label = tk.Label(
            text_frame,
            text=notification["message"],
            font=message_font,
            fg="#5d6d7e",
            bg="white",
            anchor="w",
            justify="left",
            wraplength=200
        )
        message_label.pack(fill="x")

        # WorkTre branding
        brand_label = tk.Label(
            content_frame,
            text="• WorkTre",
            font=("Segoe UI", 7),
            fg=theme["primary"],
            bg="white"
        )
        brand_label.place(relx=0.05, rely=0.9)

        # Time indicator
        time_label = tk.Label(
            content_frame,
            text="now",
            font=("Segoe UI", 7),
            fg="#95a5a6",
            bg="white"
        )
        time_label.place(relx=0.85, rely=0.9)

        # Close button
        close_btn = tk.Label(
            content_frame,
            text="×",
            font=("Segoe UI", 12),
            fg="#95a5a6",
            bg="white",
            cursor="hand2"
        )
        close_btn.place(relx=0.95, rely=0.1, anchor="ne")

        def close_window():
            root.destroy()

        close_btn.bind("<Button-1>", lambda e: close_window())

    def _animate_in(self, root):
        """Animate notification sliding in"""

        def animate():
            for alpha in range(0, 100, 5):
                try:
                    root.attributes('-alpha', alpha / 100)
                    root.update()
                    time.sleep(0.01)
                except:
                    break

        threading.Thread(target=animate, daemon=True).start()

    def _setup_hover_effects(self, root, theme):
        """Setup hover effects for notification"""

        def on_enter(e):
            try:
                root.attributes('-alpha', 1.0)
                for widget in root.winfo_children():
                    if isinstance(widget, tk.Frame):
                        for child in widget.winfo_children():
                            if child.winfo_class() == 'Frame':
                                child.configure(bg="#f8f9fa")
            except:
                pass

        def on_leave(e):
            try:
                root.attributes('-alpha', 0.95)
                for widget in root.winfo_children():
                    if isinstance(widget, tk.Frame):
                        for child in widget.winfo_children():
                            if child.winfo_class() == 'Frame':
                                child.configure(bg="white")
            except:
                pass

        try:
            root.bind("<Enter>", on_enter)
            root.bind("<Leave>", on_leave)
        except:
            pass

    def _cleanup_notifications(self):
        """Clean up old notifications"""
        current_time = time.time()
        self.active_notifications = [
            n for n in self.active_notifications
            if current_time - n["start_time"] < n["duration"] + 2
        ]

    def _log(self, msg):
        if self.logger:
            self.logger.info(msg)
