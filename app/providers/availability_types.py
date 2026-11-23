from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Internal statuses (TZ §15.6) — WhoisFreaks maps into these
AVAILABLE_FILTER = {"AVAILABLE_PRELIMINARY", "AVAILABLE_CONFIRMED"}


@dataclass
class AvailabilityItemResult:
    domain: str
    status: str
    raw_availability: Optional[str] = None
    error: Optional[str] = None
    is_premium: bool = False
    billed: bool = True  # False for local INVALID/UNSUPPORTED (no WhoisFreaks credit)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AvailabilityBatchResult:
    provider: str
    http_status: int
    items: list[AvailabilityItemResult]
    credits_actual: int
    error: Optional[str] = None
    raw_response: dict[str, Any] = field(default_factory=dict)
