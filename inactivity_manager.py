import ctypes
import time
import threading
import os

# --- Windows idle time check ---
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_duration():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0

# --- Logging ---
def get_log_file_path():
    log_dir = os.path.join(os.getenv("APPDATA"), "MyAppLogs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "inactivity.log")

def log(text):
    try:
        with open(get_log_file_path(), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception as e:
        print(f"[Logging Error] {e}")

# === Globals ===
_inactivity_thread = None
_stop_flag = None
_reset_flag = None
_lock_after_min = False
_locked_time_start = None


# === Inactivity Timer ===
def start_inactivity_timer(min_minutes: float, max_minutes: float, on_warn=None, on_exit=None):
    global _inactivity_thread, _stop_flag, _reset_flag, _lock_after_min, _locked_time_start

    if min_minutes <= 0:
        log("Inactivity timer not started because min_minutes is 0.")
        print("Inactivity timer not started because min_minutes is 0.")
        return

    print("inactivity interval started")

    # Create flags if they don't exist
    if _stop_flag is None:
        _stop_flag = threading.Event()
    else:
        _stop_flag.clear()

    if _reset_flag is None:
        _reset_flag = threading.Event()
    else:
        _reset_flag.clear()

    _lock_after_min = False
    _locked_time_start = None

    min_seconds = min_minutes * 60
    max_seconds = max_minutes * 60

    log(f"Inactivity monitor started: min={min_minutes}min, max={max_minutes}min")

    def monitor():
        global _lock_after_min, _locked_time_start

        while not _stop_flag.is_set():
            idle_time = get_idle_duration()
            log(f"Idle for {int(idle_time)}s | Locked: {_lock_after_min}")

            if idle_time >= min_seconds and not _lock_after_min:
                _lock_after_min = True
                _locked_time_start = time.time()
                log(f"Minimum inactivity reached ({min_minutes}m). Locking timer.")
                if on_warn:
                    try:
                        on_warn()
                    except Exception as e:
                        log(f"Error in on_warn callback: {e}")

            if _lock_after_min:
                if _locked_time_start is None:
                    _locked_time_start = time.time()
                    log("Inactivity marked. Tracking max time from now.")

                elapsed_since_lock = time.time() - _locked_time_start
                if elapsed_since_lock >= (max_seconds - min_seconds):
                    log("Maximum inactivity time reached. Exiting.")
                    if on_exit:
                        try:
                            on_exit()
                        except Exception as e:
                            log(f"Error in on_exit callback: {e}")
                    stop_inactivity_timer()  # 👈 Stop flag set
                    break  # 👈 Exit the loop/thread

            if _reset_flag.is_set():
                log("Manual reset called. Unlocking inactivity state.")
                _reset_flag.clear()
                _lock_after_min = False
                _locked_time_start = None

            if not _lock_after_min and idle_time < min_seconds:
                log("User activity detected before min. Timer stays fresh.")

            time.sleep(1)

    _inactivity_thread = threading.Thread(target=monitor, daemon=True)
    _inactivity_thread.start()


def stop_inactivity_timer():
    global _stop_flag

    if _stop_flag is None:
        log("Inactivity timer was never started. Nothing to stop.")
        return

    _stop_flag.set()
    print("inactivity interval stopped")
    log("Inactivity monitor stopped.")


def reset_idle_timer():
    global _reset_flag

    if _reset_flag is None:
        log("Inactivity timer not started. Cannot reset.")
        return

    _reset_flag.set()
    log("Inactivity timer reset requested.")
