from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.schemas import AvailabilityExportRequest
from app.api.schemas_availability import AvailabilityEstimateIn, AvailabilityJobCreate
from app.auth import require_basic_auth
from app.db import get_db
from app.models import AvailabilityJob, Run
from app.providers.whoisfreaks import GoDaddyAvailabilityStub
from app.services import availability as avail_svc
from app.services import exports as export_svc
from app.worker.availability_worker import start_availability_job_async

router = APIRouter(tags=["availability"])


@router.post("/api/runs/{run_id}/availability/estimate")
def estimate(
    run_id: uuid.UUID,
    body: AvailabilityEstimateIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    try:
        return avail_svc.estimate_availability(
            db, run_id, force_refresh=body.force_refresh, max_n=body.max_n
        )
    except KeyError:
        raise HTTPException(404, "run not found") from None


@router.post("/api/runs/{run_id}/availability/jobs")
def create_job(
    run_id: uuid.UUID,
    body: AvailabilityJobCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    try:
        job = avail_svc.create_availability_job(
            db,
            run_id,
            budget_cap_credits=body.budget_cap_credits,
            budget_cap_usd=body.budget_cap_usd,
            force_refresh=body.force_refresh,
            mode=body.mode,
            max_n=body.max_n,
            domains_filter=body.domains,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError:
        raise HTTPException(404, "run not found") from None

    started = False
    if body.start:
        started = start_availability_job_async(job.id)
    return {
        "job_id": str(job.id),
        "worker_started": started or body.start,
        "progress": avail_svc.job_progress(db, job.id),
    }


@router.get("/api/availability/jobs/{job_id}")
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    try:
        return avail_svc.job_progress(db, job_id)
    except KeyError:
        raise HTTPException(404, "job not found") from None


@router.post("/api/availability/jobs/{job_id}/pause")
def pause_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    job = db.get(AvailabilityJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.status = "PAUSED"
    db.commit()
    return avail_svc.job_progress(db, job_id)


@router.post("/api/availability/jobs/{job_id}/resume")
def resume_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    from app.worker.recovery import reclaim_availability_job

    job = db.get(AvailabilityJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status not in {"PAUSED", "QUEUED", "RUNNING"}:
        raise HTTPException(409, f"cannot resume from {job.status}")
    reclaimed = reclaim_availability_job(db, job_id)
    job.status = "QUEUED"
    db.commit()
    started = start_availability_job_async(job_id)
    return {
        "worker_started": started,
        "reclaimed": reclaimed,
        "progress": avail_svc.job_progress(db, job_id),
    }


@router.post("/api/availability/jobs/{job_id}/cancel")
def cancel_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    job = db.get(AvailabilityJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.status = "CANCELED"
    db.commit()
    return avail_svc.job_progress(db, job_id)


@router.get("/api/runs/{run_id}/availability")
def list_availability(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    status: str | None = None,
    available_only: bool = False,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    try:
        return avail_svc.list_run_availability(
            db,
            run_id,
            status=status,
            available_only=available_only,
            q=q,
            tld=tld,
            last_seen_before=last_seen_before,
            page=page,
            page_size=page_size,
        )
    except KeyError:
        raise HTTPException(404, "run not found") from None


@router.post("/api/domains/{domain}/availability/recheck")
def recheck_domain(
    domain: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    run_id: uuid.UUID = Query(..., description="Attach recheck to this run's job"),
    budget_cap_credits: int = Query(default=1, ge=1),
):
    """Force-refresh a single domain via a tiny availability job."""
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    try:
        job = avail_svc.create_availability_job(
            db,
            run_id,
            budget_cap_credits=budget_cap_credits,
            budget_cap_usd=None,
            force_refresh=True,
            mode="filtered",
            domains_filter=[domain.lower()],
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    started = start_availability_job_async(job.id)
    return {"job_id": str(job.id), "worker_started": started, "progress": avail_svc.job_progress(db, job.id)}


@router.post("/api/domains/{domain}/availability/confirm-live")
def confirm_live_stub(
    domain: str,
    _: str = Depends(require_basic_auth),
):
    stub = GoDaddyAvailabilityStub().check_many([domain.lower()])
    raise HTTPException(
        501,
        detail={
            "message": "GoDaddy live confirm deferred in MVP bootstrap",
            "provider_error": stub.error,
            "domain": domain.lower(),
        },
    )


def _availability_export(
    db: Session,
    run_id: uuid.UUID,
    *,
    export_all: bool,
    available_only: bool,
    status: str | None,
    q: str | None,
    tld: str | None,
    last_seen_before: str | None,
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    has_filters = any([available_only, status, q, tld, last_seen_before])
    export_all = bool(export_all) or not has_filters
    try:
        return export_svc.build_availability_exports(
            db,
            run_id,
            export_all=export_all,
            filters={
                "available_only": available_only or None,
                "status": status,
                "q": q,
                "tld": tld,
                "last_seen_before": last_seen_before,
            },
        )
    except KeyError:
        raise HTTPException(404, "run not found") from None


@router.get("/api/runs/{run_id}/availability/export")
def export_availability_get(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    export_all: bool = True,
    available_only: bool = False,
    status: str | None = None,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
):
    """GET keeps scripts working; pass filters via query or use POST."""
    return _availability_export(
        db,
        run_id,
        export_all=export_all,
        available_only=available_only,
        status=status,
        q=q,
        tld=tld,
        last_seen_before=last_seen_before,
    )


@router.post("/api/runs/{run_id}/availability/export")
def export_availability_post(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    body: AvailabilityExportRequest | None = None,
):
    req = body or AvailabilityExportRequest(export_all=True)
    return _availability_export(
        db,
        run_id,
        export_all=req.export_all,
        available_only=req.available_only,
        status=req.status,
        q=req.q,
        tld=req.tld,
        last_seen_before=req.last_seen_before,
    )


@router.get("/api/exports/{export_id}/availability/{filename}")
def download_availability_export(
    export_id: uuid.UUID,
    filename: str,
    run_id: uuid.UUID = Query(...),
    _: str = Depends(require_basic_auth),
):
    try:
        path = export_svc.export_availability_file_path(run_id, export_id, filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(404, "file not found") from None
    return FileResponse(path, filename=filename)
