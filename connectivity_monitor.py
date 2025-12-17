# connectivity_monitor.py

import threading
import time
import urllib.request

CHECK_INTERVAL = 5  # seconds
DEFAULT_NOTIFY_AFTER_SECONDS = 15 * 60  # 15 minutes

timer_thread = None
timer_lock = threading.Lock()
stop_timer = False


def is_online():
    try:
        urllib.request.urlopen("https://www.google.com", timeout=5)
        return True
    except:
        return False


def notify_js_if_offline(api_object):
    try:
        api_object.notify_no_connection()
    except Exception as e:
        print("Failed to notify JS:", e)


def notify_online(api_object):
    try:
        api_object.notify_online()
    except Exception as e:
        print("Failed to notify JS:", e)


def notify_offline(api_object):
    try:
        api_object.notify_offline()
    except Exception as e:
        print("Failed to notify JS:", e)


def start_offline_timer(api_object, notify_after_seconds=DEFAULT_NOTIFY_AFTER_SECONDS):
    def timer():
        global stop_timer
        print(f"Offline detected, starting {notify_after_seconds // 60} minute timer...")

        start_time = time.time()
        while time.time() - start_time < notify_after_seconds:
            if stop_timer:
                print("Internet restored before timer expired, canceling timer.")
                return
            time.sleep(1)

        print(f"No internet for {notify_after_seconds // 60} minutes. Notifying JS...")
        notify_js_if_offline(api_object)

    global timer_thread, stop_timer
    with timer_lock:
        if timer_thread is None or not timer_thread.is_alive():
            stop_timer = False
            timer_thread = threading.Thread(target=timer, daemon=True)
            timer_thread.start()


def cancel_offline_timer():
    global stop_timer
    stop_timer = True


def start_connectivity_monitor(api_object, notify_after_seconds=DEFAULT_NOTIFY_AFTER_SECONDS):
    def monitor():
        was_online = True

        while True:
            online = is_online()

            if online:
                if not was_online:
                    print("Back online.")
                    notify_online(api_object)
                    cancel_offline_timer()
                was_online = True
            else:
                if was_online:
                    print("Internet went offline.")
                    # notify_offline(api_object) // temporary on hold
                    start_offline_timer(api_object, notify_after_seconds)
                was_online = False

            time.sleep(CHECK_INTERVAL)

    threading.Thread(target=monitor, daemon=True).start()
