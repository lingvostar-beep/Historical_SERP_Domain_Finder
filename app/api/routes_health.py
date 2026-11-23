from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.auth import require_basic_auth
from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "version": __version__,
        "env": settings.app_env,
        "serp_primary": settings.dataforseo_primary_source,
        "max_history_days": settings.dataforseo_max_history_days,
    }


@router.get("/api/health/db")
def health_db(
    _: str = Depends(require_basic_auth),
    db: Session = Depends(get_db),
):
    db.execute(text("SELECT 1"))
    return {"ok": True, "database": True}
