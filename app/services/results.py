"""Domains / Positions / Coverage queries — TZ §9 (1c)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Coverage,
    DomainAvailabilityState,
    Keyword,
    ProjectTarget,
    Run,
    RunQuery,
    SerpResult,
    SerpSnapshot,
)
from app.providers.availability_types import AVAILABLE_FILTER


def _run_or_raise(db: Session, run_id: uuid.UUID) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise KeyError("run not found")
    return run


def _base_join(run_id: uuid.UUID):
    return (
        SerpResult.snapshot_id == SerpSnapshot.id,
        SerpSnapshot.run_query_id == RunQuery.id,
        RunQuery.run_id == run_id,
        SerpResult.result_type == "organic",
        SerpResult.registrable_domain.isnot(None),
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _check_age(last_checked_at: datetime | None) -> str | None:
    if last_checked_at is None:
        return None
    ts = last_checked_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def parse_last_seen_before(value: str) -> datetime:
    """UC-03: calendar day inclusive (UTC end-of-day). Used in HAVING, not client-page filter."""
    day = value.strip()[:10]
    return datetime.fromisoformat(f"{day}T23:59:59+00:00")


def list_domains(
    db: Session,
    run_id: uuid.UUID,
    *,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
    available_only: bool = False,
    sort: str = "keywords_found",
    order: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _run_or_raise(db, run_id)
    page = max(1, page)
    page_size = min(max(1, page_size), 500)

    domain_col = SerpResult.registrable_domain
    stmt = (
        select(
            domain_col.label("domain"),
            func.count(func.distinct(SerpSnapshot.keyword_id)).label("keywords_found"),
            func.count(func.distinct(SerpSnapshot.location_code)).label("countries_found"),
            func.count(func.distinct(SerpSnapshot.observed_month)).label("months_found"),
            func.count().label("serp_appearances"),
            func.min(SerpResult.rank_group).label("best_organic_rank"),
            func.min(SerpSnapshot.observed_at).label("first_seen"),
            func.max(SerpSnapshot.observed_at).label("last_seen"),
            func.min(SerpResult.url).label("sample_url"),
        )
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .where(and_(*_base_join(run_id)))
        .group_by(domain_col)
    )
    if q:
        # §9.1 — full-text style filter across domain, keyword, and URL.
        needle = f"%{q.strip().lower()}%"
        match_domains = (
            select(SerpResult.registrable_domain)
            .select_from(SerpResult)
            .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
            .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
            .join(Keyword, SerpSnapshot.keyword_id == Keyword.id)
            .where(
                and_(
                    *_base_join(run_id),
                    or_(
                        func.lower(SerpResult.registrable_domain).like(needle),
                        func.lower(Keyword.normalized_text).like(needle),
                        func.lower(SerpResult.url).like(needle),
                    ),
                )
            )
            .distinct()
        )
        stmt = stmt.where(domain_col.in_(match_domains))
    if tld:
        t = tld.strip().lower().lstrip(".")
        stmt = stmt.where(func.lower(domain_col).like(f"%.{t}"))
    if last_seen_before:
        # UC-03: server-side HAVING over full run — total/page come from filtered set.
        cutoff = parse_last_seen_before(last_seen_before)
        stmt = stmt.having(func.max(SerpSnapshot.observed_at) <= cutoff)
    if available_only:
        avail_doms = select(DomainAvailabilityState.registrable_domain).where(
            DomainAvailabilityState.latest_status.in_(tuple(AVAILABLE_FILTER))
        )
        stmt = stmt.where(domain_col.in_(avail_doms))
    sort_map = {
        "keywords_found": "keywords_found",
        "best_organic_rank": "best_organic_rank",
        "last_seen": "last_seen",
        "first_seen": "first_seen",
        "countries_found": "countries_found",
        "months_found": "months_found",
        "serp_appearances": "serp_appearances",
        "domain": "domain",
    }
    sort_key = sort_map.get(sort, "keywords_found")
    # TZ defaults: keywords_found desc, best_organic_rank asc, last_seen asc, countries_found desc
    default_order = {
        "best_organic_rank": "asc",
        "last_seen": "asc",
        "first_seen": "asc",
        "domain": "asc",
    }
    order_eff = order.lower() if order else default_order.get(sort_key, "desc")
    if order_eff not in {"asc", "desc"}:
        order_eff = default_order.get(sort_key, "desc")
    # Count AFTER filters/HAVING so pager total is global, not “matches on this page”.
    sub = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    col = sub.c[sort_key]
    ordering = col.asc() if order_eff == "asc" else col.desc()
    rows = db.execute(
        select(sub).order_by(ordering).offset((page - 1) * page_size).limit(page_size)
    ).mappings().all()

    domains = [r["domain"] for r in rows if r["domain"]]
    state_map: dict[str, DomainAvailabilityState] = {}
    if domains:
        for st in db.scalars(
            select(DomainAvailabilityState).where(
                DomainAvailabilityState.registrable_domain.in_(domains)
            )
        ).all():
            state_map[st.registrable_domain] = st

    from app.services.availability import _eligibility_for_domain

    items = []
    for r in rows:
        best_kw = _best_keyword_for_domain(db, run_id, r["domain"], r["best_organic_rank"])
        st = state_map.get(r["domain"] or "")
        elig = st.eligibility_status if st else _eligibility_for_domain(db, r["domain"] or "")
        items.append(
            {
                "domain": r["domain"],
                "keywords_found": int(r["keywords_found"] or 0),
                "countries_found": int(r["countries_found"] or 0),
                "months_found": int(r["months_found"] or 0),
                "serp_appearances": int(r["serp_appearances"] or 0),
                "best_organic_rank": r["best_organic_rank"],
                "first_seen": _iso(r["first_seen"]),
                "last_seen": _iso(r["last_seen"]),
                "best_rank_keyword": best_kw,
                "sample_url": r["sample_url"],
                "registration_status": st.latest_status if st else "NOT_CHECKED",
                "availability_provider": st.provider if st else None,
                "last_checked_at": _iso(st.last_checked_at) if st else None,
                "check_age": _check_age(st.last_checked_at) if st else None,
                "registration_restrictions": elig,
                "confirmation_status": st.confirmation_status if st else "NONE",
                "eligibility_status": elig,
            }
        )
    return {
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "sort": sort_key,
        "order": order_eff,
        "available_only": bool(available_only),
        "available_statuses": sorted(AVAILABLE_FILTER),
        "items": items,
        "warning": (
            "Available (preliminary) is not a buy guarantee; "
            "UNKNOWN/ERROR/RESTRICTED are never treated as free."
        ),
    }


def _best_keyword_for_domain(
    db: Session, run_id: uuid.UUID, domain: str, best_rank: int | None
) -> str | None:
    if best_rank is None:
        return None
    row = db.execute(
        select(Keyword.normalized_text)
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .join(Keyword, SerpSnapshot.keyword_id == Keyword.id)
        .where(
            and_(
                *_base_join(run_id),
                SerpResult.registrable_domain == domain,
                SerpResult.rank_group == best_rank,
            )
        )
        .limit(1)
    ).first()
    return row[0] if row else None


def _position_facets(db: Session, run: Run) -> dict[str, Any]:
    targets = db.scalars(
        select(ProjectTarget).where(ProjectTarget.project_id == run.project_id)
    ).all()
    months = db.scalars(
        select(SerpSnapshot.observed_month)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .where(RunQuery.run_id == run.id, SerpSnapshot.observed_month.isnot(None))
        .distinct()
        .order_by(SerpSnapshot.observed_month.asc())
    ).all()
    sources = db.scalars(
        select(SerpSnapshot.provider)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .where(RunQuery.run_id == run.id, SerpSnapshot.provider.isnot(None))
        .distinct()
        .order_by(SerpSnapshot.provider.asc())
    ).all()
    return {
        "locations": [
            {"location_code": t.location_code, "location_name": t.location_name, "language_code": t.language_code}
            for t in targets
        ],
        "languages": sorted({t.language_code for t in targets if t.language_code}),
        "months": [m for m in months if m],
        "sources": [s for s in sources if s],
        "rank_presets": [3, 10, 20, 50, 100],
    }


def list_positions(
    db: Session,
    run_id: uuid.UUID,
    *,
    keyword: str | None = None,
    location_code: int | None = None,
    language_code: str | None = None,
    month: str | None = None,
    domain: str | None = None,
    tld: str | None = None,
    source: str | None = None,
    rank_max: int | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    run = _run_or_raise(db, run_id)
    page = max(1, page)
    page_size = min(max(1, page_size), 1000)

    stmt = (
        select(
            Keyword.normalized_text.label("keyword"),
            SerpSnapshot.location_code,
            SerpSnapshot.language_code,
            SerpSnapshot.observed_at,
            SerpSnapshot.observed_month,
            SerpResult.rank_group.label("organic_rank"),
            SerpResult.rank_absolute.label("absolute_rank"),
            SerpResult.registrable_domain.label("domain"),
            SerpResult.hostname,
            SerpResult.url,
            SerpResult.title,
            SerpSnapshot.provider.label("source"),
        )
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .join(Keyword, SerpSnapshot.keyword_id == Keyword.id)
        .where(and_(*_base_join(run_id)))
    )
    if keyword:
        stmt = stmt.where(func.lower(Keyword.normalized_text).like(f"%{keyword.strip().lower()}%"))
    if location_code is not None:
        stmt = stmt.where(SerpSnapshot.location_code == location_code)
    if language_code:
        stmt = stmt.where(SerpSnapshot.language_code == language_code.lower())
    if month:
        stmt = stmt.where(SerpSnapshot.observed_month == month)
    if domain:
        stmt = stmt.where(func.lower(SerpResult.registrable_domain).like(f"%{domain.strip().lower()}%"))
    if tld:
        t = tld.strip().lower().lstrip(".")
        stmt = stmt.where(func.lower(SerpResult.registrable_domain).like(f"%.{t}"))
    if source:
        stmt = stmt.where(func.lower(SerpSnapshot.provider) == source.strip().lower())
    if rank_max is not None:
        stmt = stmt.where(SerpResult.rank_group <= rank_max)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(
        stmt.order_by(SerpSnapshot.observed_at.desc(), SerpResult.rank_group.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).mappings().all()

    name_map = {
        t.location_code: t.location_name
        for t in db.scalars(select(ProjectTarget).where(ProjectTarget.project_id == run.project_id)).all()
    }

    items = [
        {
            "keyword": r["keyword"],
            "location_code": r["location_code"],
            "location_name": name_map.get(r["location_code"]),
            "language": r["language_code"],
            "observed_at": _iso(r["observed_at"]),
            "month": r["observed_month"],
            "organic_rank": r["organic_rank"],
            "absolute_rank": r["absolute_rank"],
            "domain": r["domain"],
            "hostname": r["hostname"],
            "url": r["url"],
            "title": r["title"],
            "source": r["source"],
        }
        for r in rows
    ]
    return {
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "items": items,
        "facets": _position_facets(db, run),
    }


def list_coverage(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    _run_or_raise(db, run_id)
    page = max(1, page)
    page_size = min(max(1, page_size), 2000)

    stmt = (
        select(Coverage, Keyword.normalized_text.label("keyword"))
        .join(Keyword, Coverage.keyword_id == Keyword.id)
        .where(Coverage.run_id == run_id)
    )
    count_q = (
        select(func.count())
        .select_from(Coverage)
        .join(Keyword, Coverage.keyword_id == Keyword.id)
        .where(Coverage.run_id == run_id)
    )
    if status:
        stmt = stmt.where(Coverage.status == status)
        count_q = count_q.where(Coverage.status == status)
    if keyword:
        like = f"%{keyword.strip().lower()}%"
        stmt = stmt.where(func.lower(Keyword.normalized_text).like(like))
        count_q = count_q.where(func.lower(Keyword.normalized_text).like(like))

    total = db.scalar(count_q) or 0
    rows = db.execute(
        stmt.order_by(Keyword.normalized_text, Coverage.location_code, Coverage.month)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    status_counts = dict(
        db.execute(
            select(Coverage.status, func.count()).where(Coverage.run_id == run_id).group_by(Coverage.status)
        ).all()
    )

    items = [
        {
            "keyword": kw,
            "location_code": cov.location_code,
            "language": cov.language_code,
            "month": cov.month,
            "status": cov.status,
            "snapshot_count": cov.snapshot_count,
            "organic_count": cov.organic_count,
        }
        for cov, kw in rows
    ]
    return {
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "status_counts": {k: int(v) for k, v in status_counts.items()},
        "planned_snapshots": int(total) if not status and not keyword else None,
        "items": items,
    }


def coverage_matrix(
    db: Session,
    run_id: uuid.UUID,
    *,
    keyword: str | None = None,
    location_code: int | None = None,
    status: str | None = None,
    keyword_page: int = 1,
    keyword_page_size: int = 25,
) -> dict[str, Any]:
    """TZ §9.3 — matrix keyword × country × month (not a flat list)."""
    run = _run_or_raise(db, run_id)
    keyword_page = max(1, keyword_page)
    keyword_page_size = min(max(1, keyword_page_size), 100)

    name_map = {
        t.location_code: t.location_name
        for t in db.scalars(select(ProjectTarget).where(ProjectTarget.project_id == run.project_id)).all()
    }

    status_counts = dict(
        db.execute(
            select(Coverage.status, func.count()).where(Coverage.run_id == run_id).group_by(Coverage.status)
        ).all()
    )
    planned = int(sum(status_counts.values()))
    available = int(status_counts.get("AVAILABLE", 0))

    kw_stmt = (
        select(Keyword.id, Keyword.normalized_text)
        .join(Coverage, Coverage.keyword_id == Keyword.id)
        .where(Coverage.run_id == run_id)
        .distinct()
        .order_by(Keyword.normalized_text.asc())
    )
    if keyword:
        kw_stmt = kw_stmt.where(func.lower(Keyword.normalized_text).like(f"%{keyword.strip().lower()}%"))
    if location_code is not None:
        kw_stmt = kw_stmt.where(Coverage.location_code == location_code)
    if status:
        kw_stmt = kw_stmt.where(Coverage.status == status)
    kw_sub = kw_stmt.subquery()
    kw_total = db.scalar(select(func.count()).select_from(kw_sub)) or 0
    kw_rows = db.execute(
        select(kw_sub.c.id, kw_sub.c.normalized_text)
        .order_by(kw_sub.c.normalized_text.asc())
        .offset((keyword_page - 1) * keyword_page_size)
        .limit(keyword_page_size)
    ).all()
    kw_ids = [r[0] for r in kw_rows]
    kw_names = {r[0]: r[1] for r in kw_rows}

    axis_rows = db.execute(
        select(Coverage.location_code, Coverage.month).where(Coverage.run_id == run_id).distinct()
    ).all()
    locations = sorted({r[0] for r in axis_rows})
    months = sorted({r[1] for r in axis_rows if r[1]})
    if location_code is not None:
        locations = [loc for loc in locations if loc == location_code]

    cells_raw: list[Coverage] = []
    if kw_ids:
        cov_stmt = select(Coverage).where(
            Coverage.run_id == run_id,
            Coverage.keyword_id.in_(kw_ids),
        )
        if location_code is not None:
            cov_stmt = cov_stmt.where(Coverage.location_code == location_code)
        if status:
            cov_stmt = cov_stmt.where(Coverage.status == status)
        cells_raw = list(db.scalars(cov_stmt).all())

    # cells[keyword][location_code][month] = status
    matrix: dict[str, dict[str, dict[str, str]]] = {kw_names[i]: {} for i in kw_ids}
    for cov in cells_raw:
        kw = kw_names.get(cov.keyword_id)
        if not kw:
            continue
        loc = str(cov.location_code)
        matrix.setdefault(kw, {}).setdefault(loc, {})[cov.month] = cov.status

    blocks = []
    for kid in kw_ids:
        kw = kw_names[kid]
        row_block = {
            "keyword": kw,
            "rows": [
                {
                    "location_code": loc,
                    "location_name": name_map.get(loc),
                    "cells": {m: matrix.get(kw, {}).get(str(loc), {}).get(m) for m in months},
                }
                for loc in locations
            ],
        }
        blocks.append(row_block)

    return {
        "run_id": str(run_id),
        "months": months,
        "locations": [
            {"location_code": loc, "location_name": name_map.get(loc)} for loc in locations
        ],
        "blocks": blocks,
        "keyword_total": int(kw_total),
        "keyword_page": keyword_page,
        "keyword_page_size": keyword_page_size,
        "stats": {
            "planned_snapshots": planned,
            "available_snapshots": available,
            "status_counts": {k: int(v) for k, v in status_counts.items()},
        },
        "note": "Empty / missing cells are archive gaps — not proof of zero ranking.",
    }


def domain_card(db: Session, run_id: uuid.UUID, domain: str) -> dict[str, Any]:
    run = _run_or_raise(db, run_id)
    domain = domain.strip().lower()

    # exact domain aggregate
    exact = list_domains(db, run_id, q=domain, page=1, page_size=100)
    match = next((i for i in exact["items"] if (i["domain"] or "").lower() == domain), None)
    if not match:
        raise KeyError("domain not found in run")

    from app.services.availability import (
        cctld_warning_for_domain,
        check_history_for_domain,
        _eligibility_for_domain,
    )

    st = db.get(DomainAvailabilityState, domain)
    elig = st.eligibility_status if st else _eligibility_for_domain(db, domain)
    cctld = cctld_warning_for_domain(db, domain)
    history = check_history_for_domain(db, domain, limit=50)

    pos = list_positions(db, run_id, domain=domain, page=1, page_size=500)
    months = db.execute(
        select(
            SerpSnapshot.observed_month,
            func.min(SerpResult.rank_group),
            func.count(),
        )
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .where(and_(*_base_join(run_id), SerpResult.registrable_domain == domain))
        .group_by(SerpSnapshot.observed_month)
        .order_by(SerpSnapshot.observed_month)
    ).all()

    by_keyword = db.execute(
        select(
            Keyword.normalized_text,
            func.min(SerpResult.rank_group),
            func.count(func.distinct(SerpSnapshot.location_code)),
        )
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .join(Keyword, SerpSnapshot.keyword_id == Keyword.id)
        .where(and_(*_base_join(run_id), SerpResult.registrable_domain == domain))
        .group_by(Keyword.normalized_text)
        .order_by(func.min(SerpResult.rank_group))
    ).all()

    by_region = db.execute(
        select(
            SerpSnapshot.location_code,
            SerpSnapshot.language_code,
            func.min(SerpResult.rank_group),
            func.count(),
        )
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .where(and_(*_base_join(run_id), SerpResult.registrable_domain == domain))
        .group_by(SerpSnapshot.location_code, SerpSnapshot.language_code)
        .order_by(func.min(SerpResult.rank_group))
    ).all()
    name_map = {
        t.location_code: t.location_name
        for t in db.scalars(select(ProjectTarget).where(ProjectTarget.project_id == run.project_id)).all()
    }

    urls = sorted(
        {
            p["url"]
            for p in pos["items"]
            if p.get("url")
        }
    )

    return {
        "domain": domain,
        "summary": match,
        "availability": {
            "registration_status": st.latest_status if st else "NOT_CHECKED",
            "eligibility_status": elig,
            "provider": st.provider if st else None,
            "last_checked_at": _iso(st.last_checked_at) if st else None,
            "check_age": _check_age(st.last_checked_at) if st else None,
            "confirmation_status": st.confirmation_status if st else "NONE",
            "expires_at": _iso(st.expires_at) if st else None,
            "cctld_warning": cctld,
        },
        "check_history": history,
        "months": [{"month": m, "best_rank": br, "appearances": int(c)} for m, br, c in months],
        "keywords": [{"keyword": k, "best_rank": br, "countries": int(c)} for k, br, c in by_keyword],
        "regions": [
            {
                "location_code": loc,
                "location_name": name_map.get(loc),
                "language": lang,
                "best_rank": br,
                "appearances": int(c),
            }
            for loc, lang, br, c in by_region
        ],
        "historical_urls": urls[:200],
        "positions_sample": pos["items"][:100],
        "positions_total": pos["total"],
        "note": "Missing months are gaps in archive coverage, not proof of deindexing. Gaps are not filled with zeros.",
    }


def list_unique_hostnames(
    db: Session,
    run_id: uuid.UUID,
    *,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
) -> list[str]:
    """Distinct hostnames for run (dedupe_mode=hostname exports)."""
    _run_or_raise(db, run_id)
    stmt = (
        select(SerpResult.hostname)
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .join(RunQuery, SerpSnapshot.run_query_id == RunQuery.id)
        .where(
            RunQuery.run_id == run_id,
            SerpResult.result_type == "organic",
            SerpResult.hostname.isnot(None),
            SerpResult.hostname != "",
        )
    )
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(SerpResult.hostname).like(needle)
            | func.lower(SerpResult.registrable_domain).like(needle)
        )
    if tld:
        t = tld.strip().lower().lstrip(".")
        stmt = stmt.where(func.lower(SerpResult.registrable_domain).like(f"%.{t}"))
    if last_seen_before:
        cutoff = parse_last_seen_before(last_seen_before)
        # keep hostnames whose max observed_at <= cutoff
        stmt = (
            stmt.group_by(SerpResult.hostname)
            .having(func.max(SerpSnapshot.observed_at) <= cutoff)
        )
        rows = db.scalars(stmt.order_by(SerpResult.hostname.asc())).all()
    else:
        rows = db.scalars(stmt.distinct().order_by(SerpResult.hostname.asc())).all()
    return [h for h in rows if h]


def iter_all_domains(
    db: Session,
    run_id: uuid.UUID,
    *,
    q: str | None = None,
    tld: str | None = None,
    last_seen_before: str | None = None,
    available_only: bool = False,
    sort: str = "domain",
    order: str = "asc",
):
    page = 1
    while True:
        chunk = list_domains(
            db,
            run_id,
            q=q,
            tld=tld,
            last_seen_before=last_seen_before,
            available_only=available_only,
            page=page,
            page_size=500,
            sort=sort,
            order=order,
        )
        if not chunk["items"]:
            break
        yield from chunk["items"]
        if page * chunk["page_size"] >= chunk["total"]:
            break
        page += 1


def iter_all_positions(
    db: Session,
    run_id: uuid.UUID,
    *,
    keyword: str | None = None,
    location_code: int | None = None,
    language_code: str | None = None,
    month: str | None = None,
    domain: str | None = None,
    tld: str | None = None,
    source: str | None = None,
    rank_max: int | None = None,
):
    page = 1
    while True:
        chunk = list_positions(
            db,
            run_id,
            keyword=keyword,
            location_code=location_code,
            language_code=language_code,
            month=month,
            domain=domain,
            tld=tld,
            source=source,
            rank_max=rank_max,
            page=page,
            page_size=1000,
        )
        if not chunk["items"]:
            break
        yield from chunk["items"]
        if page * chunk["page_size"] >= chunk["total"]:
            break
        page += 1


def iter_all_coverage(
    db: Session,
    run_id: uuid.UUID,
    *,
    status: str | None = None,
    keyword: str | None = None,
):
    page = 1
    while True:
        chunk = list_coverage(
            db, run_id, status=status, keyword=keyword, page=page, page_size=2000
        )
        if not chunk["items"]:
            break
        yield from chunk["items"]
        if page * chunk["page_size"] >= chunk["total"]:
            break
        page += 1
