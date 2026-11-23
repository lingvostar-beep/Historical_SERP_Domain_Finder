"""Synthetic mid-scale SERP seed + timing — $0 provider spend (Stage 3 / §13 evidence).

Creates a clearly named project/run with fake snapshots/results/coverage (+ optional
availability state), then measures Domains pagination, run export, and availability list.

Usage (on host that can reach HSDF Postgres, typically VPS):
  .venv/bin/python scripts/seed_synthetic_load.py
  .venv/bin/python scripts/seed_synthetic_load.py --keywords 500 --months 12 --domains 5000
  .venv/bin/python scripts/seed_synthetic_load.py --replace   # drop prior SYNTHETIC_* project

Never calls DataForSEO / WhoisFreaks.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Coverage,
    DomainAvailabilityState,
    Keyword,
    Project,
    ProjectKeyword,
    ProjectTarget,
    Run,
    RunQuery,
    SerpResult,
    SerpSnapshot,
)
from app.services import availability as avail_svc  # noqa: E402
from app.services import exports as export_svc  # noqa: E402
from app.services import results as results_svc  # noqa: E402
from app.services.keywords import keyword_hash  # noqa: E402
from app.services.runs import create_project  # noqa: E402

PROJECT_PREFIX = "SYNTHETIC_LOAD_TEST"
PROVIDER = "synthetic_seed"
LOCATIONS = (
    (2036, "Australia", "en"),
    (2826, "United Kingdom", "en"),
)


def _month_range(n_months: int) -> tuple[date, date, list[str]]:
    """Last completed month and n_months back (inclusive), within typical 365d window."""
    today = date.today()
    # end = last day of previous month
    first_this = today.replace(day=1)
    end = first_this - timedelta(days=1)
    # start = first day of month (n_months-1) before end's month
    y, m = end.year, end.month
    for _ in range(n_months - 1):
        m -= 1
        if m < 1:
            y, m = y - 1, 12
    start = date(y, m, 1)
    months: list[str] = []
    cy, cm = start.year, start.month
    while (cy, cm) <= (end.year, end.month):
        months.append(f"{cy:04d}-{cm:02d}")
        cm += 1
        if cm > 12:
            cy, cm = cy + 1, 1
    return start, end, months


def _purge_prior(db: Session) -> int:
    rows = db.scalars(select(Project).where(Project.name.like(f"{PROJECT_PREFIX}%"))).all()
    n = 0
    for p in rows:
        db.delete(p)  # cascades runs → queries → snapshots/results/coverage
        n += 1
    db.commit()
    return n


def _ensure_keywords(db: Session, project_id: uuid.UUID, n: int) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for i in range(n):
        original = f"synth keyword {i:04d}"
        normalized = original
        h = keyword_hash(normalized)
        kw = db.scalar(select(Keyword).where(Keyword.hash == h))
        if not kw:
            kw = Keyword(original_text=original, normalized_text=normalized, hash=h)
            db.add(kw)
            db.flush()
        db.merge(ProjectKeyword(project_id=project_id, keyword_id=kw.id))
        ids.append(kw.id)
    db.flush()
    return ids


def seed(
    db: Session,
    *,
    n_keywords: int,
    n_months: int,
    n_locations: int,
    organic_depth: int,
    domain_pool: int,
    avail_sample: int,
) -> dict:
    date_from, date_to, months = _month_range(n_months)
    locs = LOCATIONS[: max(1, min(n_locations, len(LOCATIONS)))]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    project = create_project(db, name=f"{PROJECT_PREFIX}_{stamp}")
    kw_ids = _ensure_keywords(db, project.id, n_keywords)
    for code, name, lang in locs:
        db.add(
            ProjectTarget(
                project_id=project.id,
                location_code=code,
                location_name=name,
                language_code=lang,
            )
        )
    db.flush()

    domains = [f"synth{i:05d}.example.com" for i in range(domain_pool)]

    run = Run(
        project_id=project.id,
        source=PROVIDER,
        date_from=date_from,
        date_to=date_to,
        depth=max(organic_depth, 10),
        budget_cap=Decimal("0"),
        status="COMPLETED",
        dedupe_mode="registrable_domain",
        availability_mode="off",
        spent_usd=Decimal("0"),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    # Queries + coverage skeleton
    queries: list[RunQuery] = []
    for kid in kw_ids:
        for code, _name, lang in locs:
            q = RunQuery(
                run_id=run.id,
                keyword_id=kid,
                location_code=code,
                language_code=lang,
                range_from=date_from,
                range_to=date_to,
                status="DONE",
                cost_usd=Decimal("0"),
            )
            db.add(q)
            queries.append(q)
    db.flush()

    for kid in kw_ids:
        for code, _name, lang in locs:
            for month in months:
                db.add(
                    Coverage(
                        run_id=run.id,
                        keyword_id=kid,
                        location_code=code,
                        language_code=lang,
                        month=month,
                        status="AVAILABLE",
                        snapshot_count=1,
                        organic_count=organic_depth,
                    )
                )
    db.flush()

    # Snapshots + results (bulk)
    snap_rows: list[dict] = []
    result_rows: list[dict] = []
    domain_cursor = 0
    for q in queries:
        for month in months:
            y, m = int(month[:4]), int(month[5:7])
            observed = datetime(y, m, 15, 12, 0, 0, tzinfo=timezone.utc)
            sid = uuid.uuid4()
            snap_rows.append(
                {
                    "id": sid,
                    "run_id": run.id,
                    "run_query_id": q.id,
                    "keyword_id": q.keyword_id,
                    "location_code": q.location_code,
                    "language_code": q.language_code,
                    "observed_at": observed,
                    "observed_month": month,
                    "provider": PROVIDER,
                    "organic_count": organic_depth,
                    "raw_json_path": None,
                }
            )
            for rank in range(1, organic_depth + 1):
                dom = domains[domain_cursor % domain_pool]
                domain_cursor += 1
                result_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "snapshot_id": sid,
                        "item_order": rank - 1,
                        "result_type": "organic",
                        "rank_group": rank,
                        "rank_absolute": rank,
                        "url": f"https://{dom}/page/{rank}",
                        "title": f"Synth {dom}",
                        "hostname": dom,
                        "registrable_domain": dom,
                        "provider_domain": dom,
                        "subdomain": None,
                    }
                )

    t_ins = time.perf_counter()
    chunk = 2000
    for i in range(0, len(snap_rows), chunk):
        db.execute(SerpSnapshot.__table__.insert(), snap_rows[i : i + chunk])
    for i in range(0, len(result_rows), chunk):
        db.execute(SerpResult.__table__.insert(), result_rows[i : i + chunk])
    db.flush()
    insert_s = time.perf_counter() - t_ins

    # Availability state sample (no API)
    avail_n = min(avail_sample, domain_pool)
    now = datetime.now(timezone.utc)
    for i in range(avail_n):
        dom = domains[i]
        st = db.get(DomainAvailabilityState, dom)
        if not st:
            st = DomainAvailabilityState(registrable_domain=dom)
            db.add(st)
        st.latest_status = "AVAILABLE_PRELIMINARY" if i % 5 == 0 else "TAKEN"
        st.last_checked_at = now
        st.expires_at = now + timedelta(hours=24)
        st.confirmation_status = "PRELIMINARY" if i % 5 == 0 else "NONE"
        st.eligibility_status = "NOT_APPLICABLE"
        st.provider = "synthetic_seed"
    db.commit()

    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "run_id": str(run.id),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "keywords": n_keywords,
        "locations": len(locs),
        "months": len(months),
        "month_list": months,
        "queries": len(queries),
        "snapshots": len(snap_rows),
        "serp_results": len(result_rows),
        "domain_pool": domain_pool,
        "organic_depth": organic_depth,
        "availability_states": avail_n,
        "insert_seconds": round(insert_s, 3),
    }


def benchmark(db: Session, run_id: uuid.UUID) -> dict:
    rid = run_id
    out: dict = {}

    t0 = time.perf_counter()
    page1 = results_svc.list_domains(db, rid, page=1, page_size=50)
    out["domains_page1_s"] = round(time.perf_counter() - t0, 3)
    out["domains_total"] = page1["total"]

    t0 = time.perf_counter()
    page2 = results_svc.list_domains(db, rid, page=2, page_size=50)
    out["domains_page2_s"] = round(time.perf_counter() - t0, 3)
    out["domains_page2_items"] = len(page2["items"])

    # Last page stress (OFFSET deep)
    last_page = max(1, (page1["total"] + 49) // 50)
    t0 = time.perf_counter()
    results_svc.list_domains(db, rid, page=last_page, page_size=50)
    out["domains_last_page"] = last_page
    out["domains_last_page_s"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    exp = export_svc.build_run_exports(db, rid, export_all=True)
    out["export_s"] = round(time.perf_counter() - t0, 3)
    out["export_id"] = exp.get("export_id")
    out["export_counts"] = exp.get("counts")

    t0 = time.perf_counter()
    avail = avail_svc.list_run_availability(db, rid, page=1, page_size=50)
    out["availability_page1_s"] = round(time.perf_counter() - t0, 3)
    out["availability_total"] = avail["total"]

    t0 = time.perf_counter()
    cov = results_svc.coverage_matrix(db, rid, keyword_page=1, keyword_page_size=25)
    out["coverage_matrix_s"] = round(time.perf_counter() - t0, 3)
    out["coverage_keyword_total"] = cov.get("keyword_total")

    # Row counts
    out["db_snapshots"] = db.scalar(
        select(func.count()).select_from(SerpSnapshot).where(SerpSnapshot.run_id == rid)
    )
    out["db_results"] = db.scalar(
        select(func.count())
        .select_from(SerpResult)
        .join(SerpSnapshot, SerpResult.snapshot_id == SerpSnapshot.id)
        .where(SerpSnapshot.run_id == rid)
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Synthetic mid-scale load seed + timing")
    p.add_argument("--keywords", type=int, default=500)
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--locations", type=int, default=2)
    p.add_argument("--depth", type=int, default=10, help="organics per snapshot")
    p.add_argument("--domains", type=int, default=5000, help="unique domain pool size")
    p.add_argument("--avail-sample", type=int, default=1000)
    p.add_argument("--replace", action="store_true", help="delete prior SYNTHETIC_LOAD_TEST* projects")
    p.add_argument("--bench-only-run", type=str, default="", help="skip seed; bench existing run_id")
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.bench_only_run:
            run_id = uuid.UUID(args.bench_only_run)
            meta = {"run_id": args.bench_only_run, "seed": "skipped"}
            bench = benchmark(db, run_id)
        else:
            if args.replace:
                purged = _purge_prior(db)
                print(f"purged_prior_projects={purged}")
            t0 = time.perf_counter()
            meta = seed(
                db,
                n_keywords=args.keywords,
                n_months=args.months,
                n_locations=args.locations,
                organic_depth=args.depth,
                domain_pool=args.domains,
                avail_sample=args.avail_sample,
            )
            meta["seed_wall_s"] = round(time.perf_counter() - t0, 3)
            print(json.dumps({"seed": meta}, ensure_ascii=False, indent=2))
            bench = benchmark(db, uuid.UUID(meta["run_id"]))

        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider_spend_usd": 0,
            "note": "Synthetic seed — no DataForSEO / WhoisFreaks calls",
            "seed": meta,
            "benchmark": bench,
        }
        out_json = ROOT / "docs" / "synthetic_load_latest.json"
        out_md = ROOT / "docs" / "synthetic_load_latest.md"
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        b = bench
        s = meta
        out_md.write_text(
            "\n".join(
                [
                    "# Synthetic mid-scale load — latest",
                    "",
                    f"**Generated:** `{report['generated_at_utc']}`  ",
                    f"**Provider spend:** `$0` (no live SERP/availability APIs)",
                    "",
                    "## Seed",
                    "",
                    f"| | |",
                    f"|---|---|",
                    f"| Project | `{s.get('project_name', '')}` |",
                    f"| Run | `{s.get('run_id')}` |",
                    f"| Keywords × locs × months | {s.get('keywords')} × {s.get('locations')} × {s.get('months')} |",
                    f"| Snapshots / results | {s.get('snapshots')} / {s.get('serp_results')} |",
                    f"| Domain pool | {s.get('domain_pool')} |",
                    f"| Insert time | {s.get('insert_seconds')}s |",
                    "",
                    "## Benchmark",
                    "",
                    f"| Call | Seconds | Notes |",
                    f"|---|---:|---|",
                    f"| Domains page 1 (50) | {b.get('domains_page1_s')} | total={b.get('domains_total')} |",
                    f"| Domains page 2 | {b.get('domains_page2_s')} | |",
                    f"| Domains last page ({b.get('domains_last_page')}) | {b.get('domains_last_page_s')} | deep OFFSET |",
                    f"| build_run_exports | {b.get('export_s')} | {b.get('export_counts')} |",
                    f"| Availability page 1 | {b.get('availability_page1_s')} | total={b.get('availability_total')} |",
                    f"| Coverage matrix (25 kw) | {b.get('coverage_matrix_s')} | kw_total={b.get('coverage_keyword_total')} |",
                    "",
                    "## Interpretation",
                    "",
                    "Evidence for Stage 3 / §13 mid-scale without provider budget. "
                    "If Domains last-page or export times grow steeply, prioritize precomputed domain aggregates "
                    "(Roadmap 1c) and/or keyset pagination.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(json.dumps({"benchmark": bench, "wrote": [str(out_json), str(out_md)]}, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
