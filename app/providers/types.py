from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional


@dataclass
class SerpFetchRequest:
    keyword: str
    location_code: Optional[int] = None
    location_name: Optional[str] = None
    language_code: str = "en"
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    tag: Optional[str] = None


@dataclass
class OrganicItem:
    rank_group: Optional[int]
    rank_absolute: Optional[int]
    url: Optional[str]
    title: Optional[str]
    domain: Optional[str]
    item_order: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoricalSnapshot:
    observed_at: datetime
    observed_month: str
    provider: str
    organic_items: list[OrganicItem]
    organic_count: int
    raw_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class SerpFetchResult:
    provider: str
    http_status: int
    top_status_code: Optional[int]
    task_status_code: Optional[int]
    task_status_message: Optional[str]
    cost_usd: Decimal
    snapshots: list[HistoricalSnapshot]
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
