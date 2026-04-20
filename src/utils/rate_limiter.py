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

    # Hard ceiling: Zerodha rejects beyond 10 req/sec per API key (SEBI algo
    # framework also caps personal-use at 10/sec).
    ZERODHA_HARD_CAP = 10

    def __init__(self, max_calls: int, period: float = 1.0):
        """
        Args:
            max_calls: Maximum number of calls allowed within the period.
                Clamped to ZERODHA_HARD_CAP regardless of config.
            period: Time window in seconds (default 1.0)
        """
        if max_calls > self.ZERODHA_HARD_CAP:
            import warnings

            warnings.warn(
                f"RateLimiter max_calls={max_calls} exceeds Zerodha cap; "
                f"clamping to {self.ZERODHA_HARD_CAP}.",
                stacklevel=2,
            )
            max_calls = self.ZERODHA_HARD_CAP
        self.max_calls = max(1, max_calls)
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
