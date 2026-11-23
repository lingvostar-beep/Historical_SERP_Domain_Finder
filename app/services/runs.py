"""Create runs, build query matrix, progress — TZ §8."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Coverage, Keyword, Project, ProjectKeyword, ProjectTarget, Run, RunQuery
from app.providers.dates import validate_history_window
from app.services.estimate import estimate_serp, months_spanned, projected_query_cost_usd
from app.services.keywords import keyword_hash, prepare_keywords


ALLOWED_DEPTHS = {10, 20, 50, 100}
ALLOWED_DEDUPE = {"registrable_domain", "hostname"}
ALLOWED_AVAIL = {"manual_after_serp", "auto_after_serp", "off"}


def create_project(db: Session, *, name: str, owner_id: str | None = None) -> Project:
    project = Project(name=name.strip(), owner_id=owner_id)
    db.add(project)
    db.flush()
    return project


def list_projects(
    db: Session,
    *,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    filt = []
    if q and q.strip():
        filt.append(Project.name.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(Project).where(*filt)) or 0
    rows = db.scalars(
        select(Project)
        .where(*filt)
        .order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for p in rows:
        n_kw, n_tg = project_counts(db, p.id)
        runs_n = db.scalar(select(func.count()).select_from(Run).where(Run.project_id == p.id)) or 0
        items.append(
            {
                "id": str(p.id),
                "name": p.name,
                "owner_id": p.owner_id,
                "keywords": n_kw,
                "targets": n_tg,
                "runs": int(runs_n),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        )
    return {"total": int(total), "page": page, "page_size": page_size, "items": items}


def add_keywords_to_project(db: Session, project_id: uuid.UUID, lines: list[str]) -> dict:
    prepared = prepare_keywords(lines)
    linked = 0
    for original, normalized in prepared.keywords:
        h = keyword_hash(normalized)
        kw = db.scalar(select(Keyword).where(Keyword.hash == h))
        if not kw:
            kw = Keyword(original_text=original, normalized_text=normalized, hash=h)
            db.add(kw)
            db.flush()
        exists = db.scalar(
            select(ProjectKeyword).where(
                ProjectKeyword.project_id == project_id,
                ProjectKeyword.keyword_id == kw.id,
            )
        )
        if not exists:
            db.add(ProjectKeyword(project_id=project_id, keyword_id=kw.id))
            linked += 1
    db.flush()
    return {
        "loaded": prepared.loaded,
        "unique": prepared.unique,
        "duplicates_removed": prepared.duplicates_removed,
        "invalid": prepared.invalid,
        "linked_to_project": linked,
        "invalid_samples": prepared.invalid_samples,
    }


def set_project_targets(
    db: Session,
    project_id: uuid.UUID,
    targets: list[dict],
) -> list[ProjectTarget]:
    db.query(ProjectTarget).filter(ProjectTarget.project_id == project_id).delete()
    rows: list[ProjectTarget] = []
    for t in targets:
        row = ProjectTarget(
            project_id=project_id,
            location_code=int(t["location_code"]),
            location_name=str(t["location_name"]),
            language_code=str(t["language_code"]).lower(),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def project_counts(db: Session, project_id: uuid.UUID) -> tuple[int, int]:
    n_kw = db.scalar(
        select(func.count()).select_from(ProjectKeyword).where(ProjectKeyword.project_id == project_id)
    ) or 0
    n_tg = db.scalar(
        select(func.count()).select_from(ProjectTarget).where(ProjectTarget.project_id == project_id)
    ) or 0
    return int(n_kw), int(n_tg)


def list_project_runs(db: Session, project_id: uuid.UUID, *, limit: int = 50) -> list[dict]:
    limit = min(max(1, limit), 200)
    rows = db.scalars(
        select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "date_from": r.date_from.isoformat(),
            "date_to": r.date_to.isoformat(),
            "depth": r.depth,
            "budget_cap": str(r.budget_cap),
            "spent_usd": str(r.spent_usd),
            "source": r.source,
            "availability_mode": r.availability_mode,
            "dedupe_mode": r.dedupe_mode,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]


def list_project_targets(db: Session, project_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(ProjectTarget).where(ProjectTarget.project_id == project_id)).all()
    return [
        {
            "location_code": r.location_code,
            "location_name": r.location_name,
            "language_code": r.language_code,
        }
        for r in rows
    ]


def create_run(
    db: Session,
    *,
    project_id: uuid.UUID,
    date_from: date,
    date_to: date,
    depth: int = 100,
    budget_cap: Decimal,
    dedupe_mode: str = "registrable_domain",
    availability_mode: str = "manual_after_serp",
    source: str | None = None,
) -> Run:
    if depth not in ALLOWED_DEPTHS:
        raise ValueError(f"depth must be one of {sorted(ALLOWED_DEPTHS)}")
    if dedupe_mode not in ALLOWED_DEDUPE:
        raise ValueError("invalid dedupe_mode")
    if availability_mode not in ALLOWED_AVAIL:
        raise ValueError("invalid availability_mode")

    fr, to = validate_history_window(date_from, date_to)
    assert fr and to
    settings = get_settings()
    src = source or settings.dataforseo_primary_source

    n_kw, n_tg = project_counts(db, project_id)
    if n_kw < 1:
        raise ValueError("project has no keywords")
    if n_tg < 1:
        raise ValueError("project has no targets")

    run = Run(
        project_id=project_id,
        source=src,
        date_from=fr,
        date_to=to,
        depth=depth,
        budget_cap=budget_cap,
        status="QUEUED",
        dedupe_mode=dedupe_mode,
        availability_mode=availability_mode,
        spent_usd=Decimal("0"),
    )
    db.add(run)
    db.flush()

    keyword_ids = db.scalars(
        select(ProjectKeyword.keyword_id).where(ProjectKeyword.project_id == project_id)
    ).all()
    targets = db.scalars(select(ProjectTarget).where(ProjectTarget.project_id == project_id)).all()

    for kid in keyword_ids:
        for tg in targets:
            db.add(
                RunQuery(
                    run_id=run.id,
                    keyword_id=kid,
                    location_code=tg.location_code,
                    language_code=tg.language_code,
                    range_from=fr,
                    range_to=to,
                    status="QUEUED",
                )
            )
    db.flush()

    # Seed coverage as NOT_REQUESTED for each month cell
    months = []
    y, m = fr.year, fr.month
    while (y, m) <= (to.year, to.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1

    for kid in keyword_ids:
        for tg in targets:
            for month in months:
                db.add(
                    Coverage(
                        run_id=run.id,
                        keyword_id=kid,
                        location_code=tg.location_code,
                        language_code=tg.language_code,
                        month=month,
                        status="NOT_REQUESTED",
                        snapshot_count=0,
                        organic_count=0,
                    )
                )
    db.flush()
    return run


def estimate_for_project(
    db: Session,
    project_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> dict:
    n_kw, n_tg = project_counts(db, project_id)
    est = estimate_serp(
        unique_keywords=n_kw,
        region_language_pairs=n_tg,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "unique_keywords": est.unique_keywords,
        "region_language_pairs": est.region_language_pairs,
        "query_combinations": est.query_combinations,
        "planned_months": est.planned_months,
        "max_planned_snapshots": est.max_planned_snapshots,
        "reference_price_per_snapshot": est.reference_price_per_snapshot,
        "estimated_cost_usd": str(est.estimated_cost_usd),
        "date_from": est.date_from.isoformat(),
        "date_to": est.date_to.isoformat(),
        "note": est.note,
    }


def run_progress(db: Session, run_id: uuid.UUID) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise KeyError("run not found")
    total = db.scalar(select(func.count()).select_from(RunQuery).where(RunQuery.run_id == run_id)) or 0
    by_status = dict(
        db.execute(
            select(RunQuery.status, func.count())
            .where(RunQuery.run_id == run_id)
            .group_by(RunQuery.status)
        ).all()
    )
    from app.models import SerpSnapshot

    snap_count = (
        db.scalar(
            select(func.count())
            .select_from(SerpSnapshot)
            .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
            .where(RunQuery.run_id == run_id)
        )
        or 0
    )
    spent = run.spent_usd or Decimal("0")
    cap = run.budget_cap or Decimal("0")
    ratio = float(spent / cap) if cap > 0 else 0.0
    next_projected = projected_query_cost_usd(run.date_from, run.date_to)
    headroom = cap - spent if cap > 0 else Decimal("0")
    return {
        "run_id": str(run.id),
        "status": run.status,
        "spent_usd": str(run.spent_usd),
        "budget_cap": str(run.budget_cap),
        "budget_ratio": round(ratio, 4),
        "budget_warning_80": bool(cap > 0 and spent >= (cap * Decimal("0.80"))),
        "budget_headroom_usd": str(headroom.quantize(Decimal("0.000001"))),
        "next_query_projected_usd": str(next_projected),
        "can_afford_next_query": bool(cap > 0 and headroom >= next_projected),
        "depth": run.depth,
        "source": run.source,
        "date_from": run.date_from.isoformat(),
        "date_to": run.date_to.isoformat(),
        "queries_total": int(total),
        "queries_by_status": {k: int(v) for k, v in by_status.items()},
        "snapshots": int(snap_count),
        "planned_months": months_spanned(run.date_from, run.date_to),
    }


def set_run_status(db: Session, run_id: uuid.UUID, status: str) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise KeyError("run not found")
    run.status = status
    if status in {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "CANCELED", "BUDGET_EXCEEDED"}:
        run.finished_at = datetime.now(timezone.utc)
    db.flush()
    return run
