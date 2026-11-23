from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.api.routes_health import router as health_router
from app.api.routes_locations import router as locations_router
from app.api.routes_meta import router as meta_router
from app.api.routes_availability import router as availability_router
from app.api.routes_projects import router as projects_router
from app.api.routes_results import router as results_router
from app.api.routes_runs import router as runs_router
from app.config import get_settings
from app.static_mount import mount_frontend

settings = get_settings()

app = FastAPI(
    title="Historical SERP Domain Finder",
    version=__version__,
    description="MVP — SERP + availability API and internal UI",
)

app.include_router(health_router)
app.include_router(locations_router)
app.include_router(meta_router)
app.include_router(projects_router)
app.include_router(runs_router)
app.include_router(results_router)
app.include_router(availability_router)

# SPA last so /api/* and /health win
mount_frontend(app)


@app.on_event("startup")
def _startup() -> None:
    settings.raw_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.locations_cache_path.parent.mkdir(parents=True, exist_ok=True)
    # UC-02 / §12: reclaim orphaned RUNNING work after API restart and resume queues.
    try:
        from app.worker.recovery import recover_workers_on_startup

        recover_workers_on_startup()
    except Exception:  # noqa: BLE001 — never block boot on recovery
        import logging

        logging.getLogger(__name__).exception("startup worker recovery failed")
