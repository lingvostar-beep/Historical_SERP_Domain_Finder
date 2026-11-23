"""Retry policy for DataForSEO SERP fetches (TZ §8)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.providers.types import SerpFetchResult


def is_retryable(fetch: SerpFetchResult) -> bool:
    """Retry network/429/5xx; never retry business 40xxx task codes."""
    code = fetch.task_status_code
    if code is not None and 40000 <= int(code) < 50000:
        return False
    if fetch.http_status in {0, 408, 425, 429}:
        return True
    if fetch.http_status >= 500:
        return True
    return False


def backoff_seconds(attempt_index: int, *, base: float = 1.0, cap: float = 30.0) -> float:
    """attempt_index is 0-based (after first failure). Exponential + jitter."""
    raw = min(cap, base * (2**attempt_index))
    jitter = random.uniform(0, raw * 0.25)
    return raw + jitter
