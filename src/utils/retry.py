"""
Retry with Exponential Backoff
──────────────────────────────
Wraps broker API calls to handle transient network glitches without
creating duplicate orders. Uses an optional idempotency tag so repeated
attempts for the same logical request can be deduplicated server-side
when supported.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from src.utils.logger import logger

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    label: str = "broker call",
) -> T | None:
    """
    Execute a zero-arg callable with exponential backoff on failure.

    Returns the function's result on success, or None if all attempts fail.
    Non-retryable exceptions (anything not in `retryable_exceptions`) are
    raised immediately.
    """
    delay = initial_delay
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retryable_exceptions as e:
            last_error = e
            if attempt >= max_attempts:
                logger.error(f"[retry] {label} failed after {attempt} attempts: {e}")
                return None
            logger.warning(
                f"[retry] {label} attempt {attempt}/{max_attempts} failed "
                f"({e}); retrying in {delay:.1f}s"
            )
            time.sleep(delay)
            delay *= backoff_factor
    if last_error:
        logger.error(f"[retry] {label} exhausted: {last_error}")
    return None
