"""
src/utils/activity_queue.py
Persist last-activity heartbeats when offline and flush when online.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .file_utils import load_from_app_data, save_to_app_data

QUEUE_FILE = "activity_queue.json"
MAX_ITEMS = 50


class ActivityQueue:
    """Disk-backed queue for lastactivitydate payloads."""

    def __init__(self, app_name: str = "WorkTre", logger=None):
        self.app_name = app_name
        self.logger = logger
        self._lock = threading.Lock()

    def _log(self, msg: str, level: str = "info"):
        if self.logger:
            getattr(self.logger, level, self.logger.info)(f"[ActivityQueue] {msg}")

    def _load(self) -> List[Dict[str, Any]]:
        data = load_from_app_data(QUEUE_FILE, self.app_name, default=[])
        if not isinstance(data, list):
            return []
        return data

    def _save(self, items: List[Dict[str, Any]]) -> None:
        # Keep newest MAX_ITEMS
        if len(items) > MAX_ITEMS:
            items = items[-MAX_ITEMS:]
        save_to_app_data(QUEUE_FILE, items, self.app_name)

    def enqueue(self, user_id: str, break_flag: str = "False",
                idle_time_start: str = "", idle_time_end: str = "") -> None:
        with self._lock:
            items = self._load()
            items.append({
                "user_id": str(user_id),
                "break_flag": break_flag,
                "idle_time_start": idle_time_start or "",
                "idle_time_end": idle_time_end or "",
                "queued_at": time.time(),
            })
            self._save(items)
            self._log(f"Queued heartbeat for user {user_id} (queue={len(items)})")

    def size(self) -> int:
        with self._lock:
            return len(self._load())

    def flush(self, send_fn: Callable[..., Dict[str, Any]]) -> int:
        """
        Flush queued items using send_fn(user_id, break_flag, idle_start, idle_end).
        Returns number of successfully sent items.
        """
        with self._lock:
            items = self._load()
            if not items:
                return 0

            remaining: List[Dict[str, Any]] = []
            sent = 0
            for item in items:
                try:
                    result = send_fn(
                        item.get("user_id"),
                        item.get("break_flag", "False"),
                        item.get("idle_time_start", ""),
                        item.get("idle_time_end", ""),
                    )
                    ok = bool(result and result.get("status"))
                    skipped = bool(result and result.get("skipped"))
                    if ok or skipped:
                        sent += 1
                    else:
                        remaining.append(item)
                except Exception as e:
                    self._log(f"Flush item failed: {e}", "error")
                    remaining.append(item)

            self._save(remaining)
            if sent:
                self._log(f"Flushed {sent} heartbeat(s); remaining={len(remaining)}")
            return sent


_queue: Optional[ActivityQueue] = None


def get_activity_queue(app_name: str = "WorkTre", logger=None) -> ActivityQueue:
    global _queue
    if _queue is None:
        _queue = ActivityQueue(app_name, logger)
    return _queue
