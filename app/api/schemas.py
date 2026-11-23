from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class KeywordsTextImport(BaseModel):
    text: str


class TargetIn(BaseModel):
    location_code: int
    location_name: str
    language_code: str


class TargetsReplace(BaseModel):
    targets: list[TargetIn]


class RunEstimateIn(BaseModel):
    date_from: date
    date_to: date


class RunCreate(BaseModel):
    date_from: date
    date_to: date
    depth: Literal[10, 20, 50, 100] = 100
    budget_cap: Decimal = Field(gt=0)
    dedupe_mode: Literal["registrable_domain", "hostname"] = "registrable_domain"
    availability_mode: Literal["manual_after_serp", "auto_after_serp", "off"] = "manual_after_serp"
    source: Optional[str] = None
    start: bool = True


class RunExportRequest(BaseModel):
    """TZ §10: respect current filters; export_all=true = whole run."""

    export_all: bool = False
    q: Optional[str] = None
    tld: Optional[str] = None
    last_seen_before: Optional[str] = None
    available_only: bool = False
    keyword: Optional[str] = None
    pos_keyword: Optional[str] = None
    pos_domain: Optional[str] = None
    domain: Optional[str] = None
    location_code: Optional[int] = None
    language: Optional[str] = None
    month: Optional[str] = None
    rank_max: Optional[int] = None
    pos_tld: Optional[str] = None
    pos_source: Optional[str] = None
    source: Optional[str] = None
    coverage_status: Optional[str] = None
    coverage_keyword: Optional[str] = None


class AvailabilityExportRequest(BaseModel):
    export_all: bool = False
    available_only: bool = False
    status: Optional[str] = None
    q: Optional[str] = None
    tld: Optional[str] = None
    last_seen_before: Optional[str] = None
