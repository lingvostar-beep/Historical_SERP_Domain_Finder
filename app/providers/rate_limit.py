"""Token bucket rate limiter — TZ §15.9 (WhoisFreaks / GoDaddy)."""

from __future__ import annotations

import random
import threading
import time
from email.utils import parsedate_to_datetime


class TokenBucket:
    """Thread-safe token bucket. ``rate_per_minute`` refill speed; capacity = burst."""

    def __init__(self, rate_per_minute: float, *, capacity: float | None = None):
        rpm = max(0.1, float(rate_per_minute))
        self.rate_per_sec = rpm / 60.0
        self.capacity = float(capacity) if capacity is not None else max(1.0, rpm / 4.0)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_sec)
            self._updated = now

    def wait(self, tokens: float = 1.0) -> float:
        """Block until ``tokens`` available. Returns seconds slept."""
        slept = 0.0
        need = max(0.0, float(tokens))
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= need:
                    self._tokens -= need
                    return slept
                deficit = need - self._tokens
                delay = deficit / self.rate_per_sec if self.rate_per_sec > 0 else 1.0
            time.sleep(delay)
            slept += delay

    def try_acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            need = max(0.0, float(tokens))
            if self._tokens < need:
                return False
            self._tokens -= need
            return True


def parse_retry_after(header: str | None, *, default: float = 5.0) -> float:
    """Parse Retry-After as seconds or HTTP-date. Always returns >= 0."""
    if not header:
        return default
    raw = header.strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        return max(0.0, dt.timestamp() - time.time())
    except Exception:  # noqa: BLE001
        return default


def backoff_with_jitter(attempt_index: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    """attempt_index is 0-based after first failure. Exponential + jitter (§15.9)."""
    raw = min(cap, base * (2**attempt_index))
    return raw + random.uniform(0, raw * 0.25)
