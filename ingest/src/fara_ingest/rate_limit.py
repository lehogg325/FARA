from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """Sliding-window rate limiter, jurisdiction-agnostic — any future source with
    its own rate limit reuses this. Sized for FARA's confirmed live limit (5
    requests / 10 seconds, rolling — see docs/api-notes.md): acquire() blocks
    until a slot within the last `refill_seconds` is free, rather than resetting
    on a fixed clock-aligned window boundary.
    """

    def __init__(
        self,
        max_tokens: int,
        refill_seconds: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ):
        self.max_tokens = max_tokens
        self.refill_seconds = refill_seconds
        self._sleep = sleep
        self._now = now
        self._lock = threading.Lock()
        self._request_times: list[float] = []

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self._now()
                cutoff = now - self.refill_seconds
                self._request_times = [t for t in self._request_times if t > cutoff]
                if len(self._request_times) < self.max_tokens:
                    self._request_times.append(now)
                    return
                wait = (self._request_times[0] + self.refill_seconds) - now
                self._sleep(max(wait, 0.0))
