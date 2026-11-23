from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import RunCreate, RunEstimateIn
from app.auth import require_basic_auth
from app.db import get_db
from app.models import Project, Run
from app.providers.dates import HistoryWindowError
from app.services import runs as run_svc
from app.worker.serp_worker import start_run_async

router = APIRouter(tags=["runs"])


@router.post("/api/projects/{project_id}/runs/estimate")
def estimate_run(
    project_id: uuid.UUID,
    body: RunEstimateIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    try:
        return run_svc.estimate_for_project(db, project_id, body.date_from, body.date_to)
    except HistoryWindowError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/projects/{project_id}/runs")
def create_run(
    project_id: uuid.UUID,
    body: RunCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    try:
        run = run_svc.create_run(
            db,
            project_id=project_id,
            date_from=body.date_from,
            date_to=body.date_to,
            depth=body.depth,
            budget_cap=body.budget_cap,
            dedupe_mode=body.dedupe_mode,
            availability_mode=body.availability_mode,
            source=body.source,
        )
        db.commit()
    except HistoryWindowError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    started = False
    if body.start:
        started = start_run_async(run.id)
    return {
        "id": str(run.id),
        "status": run.status if not started else "RUNNING",
        "worker_started": started or body.start,
        "progress": run_svc.run_progress(db, run.id),
    }


@router.get("/api/runs/{run_id}")
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    return run_svc.run_progress(db, run_id)


@router.post("/api/runs/{run_id}/pause")
def pause_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    run_svc.set_run_status(db, run_id, "PAUSED")
    db.commit()
    return run_svc.run_progress(db, run_id)


@router.post("/api/runs/{run_id}/resume")
def resume_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    from app.worker.recovery import reclaim_serp_run

    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    # RUNNING allowed: process died mid-run; reclaim then restart worker.
    if run.status not in {"PAUSED", "QUEUED", "RUNNING"}:
        raise HTTPException(409, f"cannot resume from {run.status}")
    reclaimed = reclaim_serp_run(db, run_id)
    run_svc.set_run_status(db, run_id, "QUEUED")
    db.commit()
    started = start_run_async(run_id)
    return {
        "worker_started": started,
        "reclaimed": reclaimed,
        "progress": run_svc.run_progress(db, run_id),
    }


@router.post("/api/runs/{run_id}/cancel")
def cancel_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    run_svc.set_run_status(db, run_id, "CANCELED")
    db.commit()
    return run_svc.run_progress(db, run_id)
