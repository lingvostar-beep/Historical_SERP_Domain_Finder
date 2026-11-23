"""Run exports — TZ §10 SERP + availability (filters + streamed CSV)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Run
from app.providers.availability_types import AVAILABLE_FILTER
from app.services import availability as avail_svc
from app.services.csv_safe import write_csv_file
from app.services.results import (
    iter_all_coverage,
    iter_all_domains,
    iter_all_positions,
    list_unique_hostnames,
)
from app.services.runs import run_progress


def exports_root() -> Path:
    root = get_settings().raw_storage_dir.parent / "exports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clean_filters(raw: dict[str, Any] | None, *, export_all: bool) -> dict[str, Any]:
    if export_all or not raw:
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value.strip() if isinstance(value, str) else value
    return out


def build_run_exports(
    db: Session,
    run_id: uuid.UUID,
    *,
    export_all: bool = True,
    filters: dict[str, Any] | None = None,
) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise KeyError("run not found")

    applied = _clean_filters(filters, export_all=export_all)
    export_id = uuid.uuid4()
    out_dir = exports_root() / str(run_id) / str(export_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    domain_kw = {
        "q": applied.get("q"),
        "tld": applied.get("tld"),
        "last_seen_before": applied.get("last_seen_before"),
        "available_only": bool(applied.get("available_only")),
    }
    position_kw = {
        "keyword": applied.get("keyword") or applied.get("pos_keyword"),
        "location_code": applied.get("location_code"),
        "language_code": applied.get("language") or applied.get("language_code"),
        "month": applied.get("month"),
        "domain": applied.get("domain") or applied.get("pos_domain"),
        "tld": applied.get("tld") or applied.get("pos_tld"),
        "source": applied.get("source") or applied.get("pos_source"),
        "rank_max": applied.get("rank_max"),
    }
    coverage_kw = {
        "status": applied.get("coverage_status") or applied.get("status"),
        "keyword": applied.get("coverage_keyword"),
    }

    progress = run_progress(db, run_id)

    # 1) unique_domains.txt — stream domain names into a set (strings only), then sort
    if run.dedupe_mode == "hostname":
        uniq = list_unique_hostnames(
            db,
            run_id,
            **{
                k: v
                for k, v in domain_kw.items()
                if k != "available_only" and v is not None
            },
        )
        uniq_kind = "hostname"
    else:
        uniq_set: set[str] = set()
        for d in iter_all_domains(db, run_id, **domain_kw, sort="domain", order="asc"):
            if d.get("domain"):
                uniq_set.add(d["domain"])
        uniq = sorted(uniq_set)
        uniq_kind = "registrable_domain"
    (out_dir / "unique_domains.txt").write_text(
        "\n".join(uniq) + ("\n" if uniq else ""),
        encoding="utf-8",
    )

    # 2) domains_summary.csv — streamed pages, no list(iter_all_*)
    domain_rows = write_csv_file(
        out_dir / "domains_summary.csv",
        [
            "domain",
            "keywords_found",
            "countries_found",
            "months_found",
            "serp_appearances",
            "best_organic_rank",
            "first_seen",
            "last_seen",
            "best_rank_keyword",
            "sample_url",
        ],
        (
            [
                d["domain"],
                d["keywords_found"],
                d["countries_found"],
                d["months_found"],
                d["serp_appearances"],
                d["best_organic_rank"],
                d["first_seen"],
                d["last_seen"],
                d["best_rank_keyword"],
                d["sample_url"],
            ]
            for d in iter_all_domains(db, run_id, **domain_kw, sort="domain", order="asc")
        ),
    )

    # 3) positions_detailed.csv
    position_rows = write_csv_file(
        out_dir / "positions_detailed.csv",
        [
            "keyword",
            "country_code",
            "country_name",
            "language",
            "observed_at",
            "month",
            "organic_rank",
            "absolute_rank",
            "domain",
            "hostname",
            "url",
            "title",
            "source",
        ],
        (
            [
                p["keyword"],
                p["location_code"],
                p["location_name"],
                p["language"],
                p["observed_at"],
                p["month"],
                p["organic_rank"],
                p["absolute_rank"],
                p["domain"],
                p["hostname"],
                p["url"],
                p["title"],
                p["source"],
            ]
            for p in iter_all_positions(db, run_id, **position_kw)
        ),
    )

    # 4) coverage.csv
    coverage_rows = write_csv_file(
        out_dir / "coverage.csv",
        [
            "keyword",
            "location_code",
            "language",
            "month",
            "status",
            "snapshot_count",
            "organic_count",
        ],
        (
            [
                c["keyword"],
                c["location_code"],
                c["language"],
                c["month"],
                c["status"],
                c["snapshot_count"],
                c["organic_count"],
            ]
            for c in iter_all_coverage(db, run_id, **coverage_kw)
        ),
    )

    # 5) run_metadata.json
    meta = {
        "export_id": str(export_id),
        "run_id": str(run_id),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": run.source,
        "date_from": run.date_from.isoformat(),
        "date_to": run.date_to.isoformat(),
        "depth": run.depth,
        "budget_cap": str(run.budget_cap),
        "spent_usd": str(run.spent_usd),
        "status": run.status,
        "dedupe_mode": run.dedupe_mode,
        "history_limit_note": "DataForSEO usable window ≈ last 365 days (Spike 2026-11-19)",
        "export_all": bool(export_all) or not applied,
        "filters_applied": applied,
        "progress": progress,
        "counts": {
            "unique_domains": len(uniq),
            "unique_list_kind": uniq_kind,
            "domain_rows": domain_rows,
            "position_rows": position_rows,
            "coverage_rows": coverage_rows,
        },
        "files": [
            "unique_domains.txt",
            "domains_summary.csv",
            "positions_detailed.csv",
            "coverage.csv",
            "run_metadata.json",
        ],
    }
    (out_dir / "run_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "export_id": str(export_id),
        "run_id": str(run_id),
        "path": str(out_dir),
        "files": meta["files"],
        "counts": meta["counts"],
        "export_all": meta["export_all"],
        "filters_applied": applied,
    }


def export_file_path(run_id: uuid.UUID, export_id: uuid.UUID, filename: str) -> Path:
    allowed = {
        "unique_domains.txt",
        "domains_summary.csv",
        "positions_detailed.csv",
        "coverage.csv",
        "run_metadata.json",
    }
    if filename not in allowed:
        raise ValueError("unknown export file")
    path = exports_root() / str(run_id) / str(export_id) / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path


def build_availability_exports(
    db: Session,
    run_id: uuid.UUID,
    *,
    export_all: bool = True,
    filters: dict[str, Any] | None = None,
) -> dict:
    run = db.get(Run, run_id)
    if not run:
        raise KeyError("run not found")

    applied = _clean_filters(filters, export_all=export_all)
    export_id = uuid.uuid4()
    out_dir = exports_root() / str(run_id) / str(export_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    domain_kw = {
        "q": applied.get("q"),
        "tld": applied.get("tld"),
        "last_seen_before": applied.get("last_seen_before"),
    }
    available_only = bool(applied.get("available_only"))
    status = applied.get("status")

    available: list[str] = []

    def row_iter():
        for item in avail_svc.iter_run_availability(
            db,
            run_id,
            available_only=available_only,
            status=status,
            **domain_kw,
        ):
            dom = item.get("domain")
            if dom and item.get("registration_status") in AVAILABLE_FILTER:
                available.append(dom)
            yield [
                item.get("domain"),
                item.get("registration_status"),
                item.get("eligibility_status"),
                item.get("availability_provider"),
                item.get("last_checked_at"),
                item.get("expires_at"),
                item.get("freshness"),
                item.get("registration_restrictions"),
                item.get("confirmation_status"),
                item.get("error_code"),
                item.get("credits_spent"),
                item.get("is_premium"),
                item.get("price_amount"),
                item.get("price_currency"),
                item.get("keywords_found"),
                item.get("best_organic_rank"),
                item.get("first_seen"),
                item.get("last_seen"),
            ]

    rows = write_csv_file(
        out_dir / "domain_availability.csv",
        [
            "domain",
            "registration_status",
            "eligibility_status",
            "availability_provider",
            "last_checked_at",
            "expires_at",
            "freshness",
            "registration_restrictions",
            "confirmation_status",
            "error_code",
            "credits_spent",
            "is_premium",
            "price_amount",
            "price_currency",
            "keywords_found",
            "best_organic_rank",
            "first_seen",
            "last_seen",
        ],
        row_iter(),
    )

    available_sorted = sorted(set(available))
    warning = (
        "# WARNING: statuses are preliminary and may change; "
        "TLD eligibility / rights to register are checked separately.\n"
    )
    (out_dir / "available_domains.txt").write_text(
        warning + "\n".join(available_sorted) + ("\n" if available_sorted else ""),
        encoding="utf-8",
    )

    meta = {
        "export_id": str(export_id),
        "run_id": str(run_id),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "type": "availability",
        "export_all": bool(export_all) or not applied,
        "filters_applied": applied,
        "available_count": len(available_sorted),
        "rows": rows,
        "available_statuses": sorted(AVAILABLE_FILTER),
        "godaddy_confirm": "deferred",
        "files": ["available_domains.txt", "domain_availability.csv", "availability_metadata.json"],
        "warning": "Available statuses are preliminary and may change; TLD eligibility is separate.",
    }
    (out_dir / "availability_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "export_id": str(export_id),
        "run_id": str(run_id),
        "path": str(out_dir),
        "files": meta["files"],
        "counts": {"available": len(available_sorted), "rows": rows},
        "export_all": meta["export_all"],
        "filters_applied": applied,
    }


def export_availability_file_path(run_id: uuid.UUID, export_id: uuid.UUID, filename: str) -> Path:
    allowed = {
        "available_domains.txt",
        "domain_availability.csv",
        "availability_metadata.json",
    }
    if filename not in allowed:
        raise ValueError("unknown availability export file")
    path = exports_root() / str(run_id) / str(export_id) / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path
