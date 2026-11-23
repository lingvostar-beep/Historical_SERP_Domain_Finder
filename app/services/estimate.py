"""Pre-run volume / cost estimate — TZ §4.3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.config import get_settings
from app.providers.dates import earliest_allowed_date, validate_history_window


@dataclass
class SerpEstimate:
    unique_keywords: int
    region_language_pairs: int
    query_combinations: int
    planned_months: int
    max_planned_snapshots: int
    reference_price_per_snapshot: float
    estimated_cost_usd: Decimal
    date_from: date
    date_to: date
    note: str


def months_spanned(date_from: date, date_to: date) -> int:
    return (date_to.year - date_from.year) * 12 + (date_to.month - date_from.month) + 1


def projected_query_cost_usd(date_from: date, date_to: date) -> Decimal:
    """Max expected charge for one run_query covering [from, to].

    TZ §8.3 / §11: one API call may return up to ~one snapshot per month;
    pre-flight must reserve months × reference_price, not a single snapshot.
    """
    settings = get_settings()
    months = max(1, months_spanned(date_from, date_to))
    price = Decimal(str(settings.dataforseo_reference_price_per_snapshot))
    return (price * Decimal(months)).quantize(Decimal("0.000001"))


def estimate_serp(
    *,
    unique_keywords: int,
    region_language_pairs: int,
    date_from: date,
    date_to: date,
    coverage_assumption: float = 1.0,
) -> SerpEstimate:
    fr, to = validate_history_window(date_from, date_to)
    assert fr is not None and to is not None
    settings = get_settings()
    combos = unique_keywords * region_language_pairs
    months = months_spanned(fr, to)
    # One API call per combo covering the whole range; max snapshots ≈ months if one snap/month
    max_snaps = int(combos * months * coverage_assumption)
    price = settings.dataforseo_reference_price_per_snapshot
    est = (Decimal(str(price)) * Decimal(max_snaps)).quantize(Decimal("0.000001"))
    return SerpEstimate(
        unique_keywords=unique_keywords,
        region_language_pairs=region_language_pairs,
        query_combinations=combos,
        planned_months=months,
        max_planned_snapshots=max_snaps,
        reference_price_per_snapshot=price,
        estimated_cost_usd=est,
        date_from=fr,
        date_to=to,
        note=(
            "Estimate assumes up to one billable snapshot per keyword×geo×month. "
            "Actual cost comes from API `cost`. Empty months are not charged as snapshots. "
            f"History window earliest={earliest_allowed_date().isoformat()}."
        ),
    )
