from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AvailabilityEstimateIn(BaseModel):
    force_refresh: bool = False
    max_n: Optional[int] = Field(default=None, ge=1)


class AvailabilityJobCreate(BaseModel):
    budget_cap_credits: int = Field(ge=1)
    budget_cap_usd: Optional[Decimal] = None
    force_refresh: bool = False
    mode: Literal["all_unique", "filtered", "max_n"] = "all_unique"
    max_n: Optional[int] = Field(default=None, ge=1)
    domains: Optional[list[str]] = None
    start: bool = True
