import os
import sys
import time
import json
import signal
import logging
import threading
import atexit
import tempfile
from pathlib import Path

try:
    import psutil
except ImportError:
    print("Install psutil first: pip install psutil")
    exit()

# Optional: Windows shutdown/logoff handler
if os.name == "nt":
    try:
        import win32api
        import win32con
    except ImportError:
        print("Install pywin32 for Windows shutdown detection: pip install pywin32")

# === Configuration ===
APP_NAME = "MyWebviewApp"
HEARTBEAT_INTERVAL = 10  # seconds
SLEEP_THRESHOLD = 120    # seconds
heartbeat_running = True


# === Path and Logging Setup ===
def get_app_data_dir(app_name=APP_NAME):
    try:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:
            base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

        app_dir = Path(base) / app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir
    except Exception:
        fallback = Path(tempfile.gettempdir()) / app_name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


APP_DIR = get_app_data_dir()
STATE_FILE = APP_DIR / "app_state.json"
LOG_FILE = APP_DIR / "app.log"

logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def log_event(message, level='info'):
    print(message)
    if level == 'info':
        logging.info(message)
    elif level == 'warning':
        logging.warning(message)
    elif level == 'error':
        logging.error(message)


# === Core Functions ===
def get_boot_time():
    return psutil.boot_time()

def get_current_time():
    return time.time()

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            log_event("Failed to load state file.", "warning")
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception:
        log_event("Failed to write to state file.", "error")

def heartbeat():
    while heartbeat_running:
        state = {
            "boot_time": get_boot_time(),
            "last_active": get_current_time(),
            "clean_exit": False
        }
        save_state(state)
        time.sleep(HEARTBEAT_INTERVAL)

def mark_clean_exit():
    state = load_state()
    state["clean_exit"] = True
    state["last_active"] = get_current_time()
    save_state(state)
    log_event("Application exited cleanly.")

def handle_signal(signum, frame):
    global heartbeat_running
    heartbeat_running = False
    mark_clean_exit()
    sys.exit(0)

def detect_last_session():
    now = get_current_time()
    current_boot = get_boot_time()
    state = load_state()

    if not state:
        log_event("First launch or no previous session data found.")
        return

    if state.get("boot_time") != current_boot:
        log_event("System was rebooted or shut down since last session.")

    last_active = state.get("last_active", now)
    time_gap = now - last_active
    if time_gap > HEARTBEAT_INTERVAL + SLEEP_THRESHOLD:
        log_event(f"System was likely asleep or hibernated. Time gap: {int(time_gap)} seconds.")

    if not state.get("clean_exit", False):
        log_event("Application did not exit cleanly. Possible crash, kill, or forced shutdown.")


# === Windows Shutdown Handling (Optional) ===
def windows_shutdown_handler(event):
    if event in (win32con.CTRL_SHUTDOWN_EVENT, win32con.CTRL_LOGOFF_EVENT):
        mark_clean_exit()
    return True

def setup_windows_handler():
    if os.name == "nt":
        try:
            win32api.SetConsoleCtrlHandler(windows_shutdown_handler, True)
        except Exception as e:
            log_event(f"Failed to set Windows shutdown handler: {e}", "warning")


# === Public Entry ===
def start_monitor():
    log_event(f"Log file location: {LOG_FILE}")
    detect_last_session()
    atexit.register(mark_clean_exit)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    setup_windows_handler()
    threading.Thread(target=heartbeat, daemon=True).start()


# === Main Entrypoint ===
def main():
    try:
        start_monitor()

        # Start your actual app loop or PyWebView window here
        while True:
            time.sleep(1)

    except Exception as e:
        log_event(f"Unhandled Exception: {e}", "error")
        mark_clean_exit()
        raise


if __name__ == "__main__":
    main()
