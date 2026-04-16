"""
API Rate Limiter
────────────────
Simple sliding-window rate limiter for Zerodha API calls.

Zerodha limits:
- 10 requests/second per API key (general)
- 3 requests/second for historical data
"""

import threading
import time


class RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self, max_calls: int, period: float = 1.0):
        """
        Args:
            max_calls: Maximum number of calls allowed within the period
            period: Time window in seconds (default 1.0)
        """
        self.max_calls = max_calls
        self.period = period
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def wait(self):
        """Block until a call is allowed within the rate limit."""
        with self._lock:
            now = time.monotonic()
            # Remove calls outside the current window
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) >= self.max_calls:
                # Wait until the oldest call falls outside the window
                sleep_time = self.period - (now - self._calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self._calls.append(time.monotonic())
