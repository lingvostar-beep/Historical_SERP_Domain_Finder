from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import KeywordsTextImport, ProjectCreate, TargetsReplace
from app.auth import require_basic_auth
from app.db import get_db
from app.models import Keyword, Project, ProjectKeyword
from app.services import runs as run_svc
from app.services.keywords import lines_from_csv_bytes, lines_from_text

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: str = Depends(require_basic_auth),
):
    project = run_svc.create_project(db, name=body.name, owner_id=user)
    db.commit()
    return {"id": str(project.id), "name": project.name, "owner_id": project.owner_id}


@router.get("")
def list_projects(
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    return run_svc.list_projects(db, q=q, page=page, page_size=page_size)


@router.get("/{project_id}")
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    n_kw, n_tg = run_svc.project_counts(db, project_id)
    return {
        "id": str(project.id),
        "name": project.name,
        "owner_id": project.owner_id,
        "keywords": n_kw,
        "targets": n_tg,
        "target_list": run_svc.list_project_targets(db, project_id),
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


@router.get("/{project_id}/runs")
def list_project_runs(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    limit: int = 50,
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    return {"items": run_svc.list_project_runs(db, project_id, limit=limit)}


@router.post("/{project_id}/keywords/import")
def import_keywords_text(
    project_id: uuid.UUID,
    body: KeywordsTextImport,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    stats = run_svc.add_keywords_to_project(db, project_id, lines_from_text(body.text))
    db.commit()
    return stats


@router.post("/{project_id}/keywords/import-file")
async def import_keywords_file(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    file: UploadFile = File(...),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    data = await file.read()
    name = (file.filename or "").lower()
    if name.endswith(".csv"):
        lines = lines_from_csv_bytes(data)
    else:
        lines = lines_from_text(data.decode("utf-8-sig"))
    stats = run_svc.add_keywords_to_project(db, project_id, lines)
    db.commit()
    return stats


@router.put("/{project_id}/targets")
def replace_targets(
    project_id: uuid.UUID,
    body: TargetsReplace,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    if not body.targets:
        raise HTTPException(400, "targets required")
    rows = run_svc.set_project_targets(db, project_id, [t.model_dump() for t in body.targets])
    db.commit()
    return {
        "count": len(rows),
        "targets": [
            {
                "location_code": r.location_code,
                "location_name": r.location_name,
                "language_code": r.language_code,
            }
            for r in rows
        ],
    }


@router.get("/{project_id}/keywords")
def list_keywords(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_basic_auth),
    limit: int = 100,
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    rows = db.execute(
        select(Keyword.original_text, Keyword.normalized_text)
        .join(ProjectKeyword, ProjectKeyword.keyword_id == Keyword.id)
        .where(ProjectKeyword.project_id == project_id)
        .limit(min(limit, 5000))
    ).all()
    return {"items": [{"original": o, "normalized": n} for o, n in rows]}
