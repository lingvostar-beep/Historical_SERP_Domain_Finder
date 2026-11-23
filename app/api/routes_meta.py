from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from app.auth import require_basic_auth
from app.config import get_settings
from app.providers.dates import earliest_allowed_date

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/serp-window")
def serp_window(_: str = Depends(require_basic_auth)):
    settings = get_settings()
    today = date.today()
    return {
        "provider_primary": settings.dataforseo_primary_source,
        "max_history_days": settings.dataforseo_max_history_days,
        "earliest_allowed_date": earliest_allowed_date(today).isoformat(),
        "today": today.isoformat(),
        "reference_price_per_snapshot_usd": settings.dataforseo_reference_price_per_snapshot,
        "concurrency": settings.dataforseo_concurrency,
        "note": "Spike 2026-11-19: DataForSEO rejects older date_from (40501). MVP UI must clamp to this window.",
    }
