import webview
import time
import threading
from datetime import datetime


def detect_sleep():
    last_wall_time = datetime.now().timestamp()  # System clock
    last_thread_time = time.time()  # Thread runtime clock

    while True:
        time.sleep(5)  # Check every 5 seconds

        current_wall_time = datetime.now().timestamp()
        current_thread_time = time.time()

        # Calculate gaps
        wall_gap = current_wall_time - last_wall_time
        thread_gap = current_thread_time - last_thread_time

        # If wall time advanced much faster than thread time, sleep likely occurred
        if wall_gap > thread_gap * 1.5:  # Adjust threshold as needed
            print(f"System slept! Wall gap: {wall_gap:.1f}s | Thread gap: {thread_gap:.1f}s")

        last_wall_time = current_wall_time
        last_thread_time = current_thread_time


# Start thread
thread = threading.Thread(target=detect_sleep, daemon=True)
thread.start()

window = webview.create_window('Sleep Detector')
webview.start()