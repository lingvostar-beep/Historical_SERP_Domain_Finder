from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.schemas import RunExportRequest
from app.auth import require_basic_auth
from app.db import get_db
from app.models import Run
from app.services import exports as export_svc
from app.services import results as results_svc

router = APIRouter(tags=["results"])


@router.get("/api/runs/{run_id}/domains")
def get_domains(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
    available_only: bool = False,
    sort: str = Query(default="keywords_found"),
    order: str | None = Query(default=None),
    page: int = 1,
    page_size: int = 50,
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    return results_svc.list_domains(
        db,
        run_id,
        q=q,
        tld=tld,
        last_seen_before=last_seen_before,
        available_only=available_only,
        sort=sort,
        order=order or "",
        page=page,
        page_size=page_size,
    )


@router.get("/api/runs/{run_id}/domains/{domain}")
def get_domain_card(
    run_id: uuid.UUID,
    domain: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    try:
        return results_svc.domain_card(db, run_id, domain)
    except KeyError:
        raise HTTPException(404, "domain not found in run") from None


@router.get("/api/runs/{run_id}/positions")
def get_positions(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    keyword: str | None = None,
    location_code: int | None = None,
    language: str | None = None,
    month: str | None = None,
    domain: str | None = None,
    tld: str | None = None,
    source: str | None = None,
    rank_max: int | None = None,
    page: int = 1,
    page_size: int = 100,
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    return results_svc.list_positions(
        db,
        run_id,
        keyword=keyword,
        location_code=location_code,
        language_code=language,
        month=month,
        domain=domain,
        tld=tld,
        source=source,
        rank_max=rank_max,
        page=page,
        page_size=page_size,
    )


@router.get("/api/runs/{run_id}/coverage")
def get_coverage(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 200,
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    return results_svc.list_coverage(
        db, run_id, status=status, keyword=keyword, page=page, page_size=page_size
    )


@router.get("/api/runs/{run_id}/coverage/matrix")
def get_coverage_matrix(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    keyword: str | None = None,
    location_code: int | None = None,
    status: str | None = None,
    keyword_page: int = 1,
    keyword_page_size: int = 25,
):
    """TZ §9.3 matrix: keyword × country × month."""
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    return results_svc.coverage_matrix(
        db,
        run_id,
        keyword=keyword,
        location_code=location_code,
        status=status,
        keyword_page=keyword_page,
        keyword_page_size=keyword_page_size,
    )


@router.post("/api/runs/{run_id}/exports")
def create_export(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    body: RunExportRequest | None = None,
):
    if not db.get(Run, run_id):
        raise HTTPException(404, "run not found")
    req = body or RunExportRequest(export_all=True)
    # Empty body / no filters → whole run (backward compatible for scripts).
    export_all = bool(req.export_all) or not any(
        [
            req.q,
            req.tld,
            req.last_seen_before,
            req.available_only,
            req.keyword,
            req.pos_keyword,
            req.pos_domain,
            req.domain,
            req.location_code is not None,
            req.language,
            req.month,
            req.rank_max is not None,
            req.coverage_status,
            req.coverage_keyword,
        ]
    )
    try:
        return export_svc.build_run_exports(
            db,
            run_id,
            export_all=export_all,
            filters=req.model_dump(exclude={"export_all"}),
        )
    except KeyError:
        raise HTTPException(404, "run not found") from None


@router.get("/api/exports/{export_id}")
def get_export_meta(
    export_id: uuid.UUID,
    run_id: uuid.UUID = Query(..., description="Run that owns this export"),
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    # meta file is source of truth
    try:
        path = export_svc.export_file_path(run_id, export_id, "run_metadata.json")
    except FileNotFoundError:
        raise HTTPException(404, "export not found") from None
    return FileResponse(path, media_type="application/json", filename="run_metadata.json")


@router.get("/api/exports/{export_id}/files/{filename}")
def download_export_file(
    export_id: uuid.UUID,
    filename: str,
    run_id: uuid.UUID = Query(...),
    _: str = Depends(require_basic_auth),
):
    try:
        path = export_svc.export_file_path(run_id, export_id, filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(404, "file not found") from None
    return FileResponse(path, filename=filename)
