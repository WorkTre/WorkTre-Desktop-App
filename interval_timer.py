# interval_timer.py

import threading

interval_timer = None
interval_lock = threading.Lock()
repeat_interval_seconds = 0
is_running = False


def on_interval_complete():
    global interval_timer, is_running

    print("Interval completed!")

    with interval_lock:
        interval_timer = None
        if is_running and repeat_interval_seconds > 0:
            print("Restarting interval...")
            interval_timer = threading.Timer(repeat_interval_seconds, on_interval_complete)
            interval_timer.start()


def start_interval(duration=300):
    """
    Start the repeating interval.
    :param duration: Duration in seconds. If 0 or less, timer won't start.
    :return: status message
    """
    global interval_timer, repeat_interval_seconds, is_running

    with interval_lock:
        if duration <= 0:
            return "Timer duration is 0 or less. Timer not started."

        if is_running:
            return "Interval is already running."

        repeat_interval_seconds = duration
        is_running = True
        interval_timer = threading.Timer(duration, on_interval_complete)
        interval_timer.start()

        minutes = duration / 60
        if minutes >= 1:
            return f"Repeating interval started for {minutes:.2f} minutes."
        else:
            return f"Repeating interval started for {duration:.0f} seconds."


def stop_interval():
    """
    Stop the repeating interval.
    :return: status message
    """
    global interval_timer, is_running

    with interval_lock:
        if interval_timer is not None:
            interval_timer.cancel()
            interval_timer = None
        is_running = False
        return "Interval stopped and will no longer repeat."
