"""Per-IP failed-login throttle (sliding window, in memory).

Account lockout lives in the database (see auth service); this throttle additionally stops
one address from spraying guesses across many accounts.
"""

import threading
import time
from collections import defaultdict, deque

WINDOW_SECONDS = 15 * 60


class LoginThrottle:
    def __init__(self, max_failures: int, window_seconds: int = WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._failures[key]
        while events and now - events[0] > self.window:
            events.popleft()
        return events

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again, or 0 if it's allowed now."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            if len(events) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - events[0])))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)
