from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_basic_auth
from app.services.locations import LocationsService

router = APIRouter(prefix="/api/locations", tags=["locations"])


@router.get("")
def list_locations(
    q: str | None = Query(default=None, description="Filter by location name"),
    refresh: bool = Query(default=False, description="Force refresh from DataForSEO"),
    _: str = Depends(require_basic_auth),
):
    service = LocationsService()
    try:
        rows = service.list_locations(q=q, force_refresh=refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "count": len(rows),
        "items": [
            {
                "location_code": r.location_code,
                "location_name": r.location_name,
                "location_code_parent": r.location_code_parent,
                "country_iso_code": r.country_iso_code,
                "location_type": r.location_type,
                "languages": r.languages,
            }
            for r in rows
        ],
    }


@router.post("/refresh")
def refresh_locations(_: str = Depends(require_basic_auth)):
    service = LocationsService()
    try:
        payload = service.fetch_remote()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "fetched_at": payload.get("fetched_at"),
        "items": len(payload.get("items") or []),
    }
