"""Persist SERP fetch results into snapshots / results / coverage / api_usage."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ApiUsage, Coverage, Keyword, Run, RunQuery, SerpResult, SerpSnapshot
from app.providers.types import SerpFetchResult
from app.services.domains import parse_result_url


def _raw_path(run_id: uuid.UUID, query_id: uuid.UUID) -> Path:
    settings = get_settings()
    folder = settings.raw_storage_dir / str(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{query_id}.json"


def persist_fetch(
    db: Session,
    *,
    run: Run,
    query: RunQuery,
    keyword: Keyword,
    fetch: SerpFetchResult,
    latency_ms: int | None = None,
) -> dict:
    raw_path = _raw_path(run.id, query.id)
    raw_path.write_text(json.dumps(fetch.raw_response or {}, ensure_ascii=False), encoding="utf-8")

    db.add(
        ApiUsage(
            run_query_id=query.id,
            provider=fetch.provider,
            request_at=datetime.now(timezone.utc),
            http_code=fetch.http_status,
            provider_status=fetch.task_status_code,
            provider_cost_usd=fetch.cost_usd or Decimal("0"),
            latency_ms=latency_ms,
            meta={
                "top_status_code": fetch.top_status_code,
                "task_status_message": fetch.task_status_message,
                "error": fetch.error,
            },
        )
    )

    cost = fetch.cost_usd or Decimal("0")
    query.cost_usd = (query.cost_usd or Decimal("0")) + cost
    # Lock run row so concurrent workers don't lose spent_usd updates (§8.2).
    locked_run = db.execute(select(Run).where(Run.id == run.id).with_for_update()).scalar_one()
    locked_run.spent_usd = (locked_run.spent_usd or Decimal("0")) + cost
    run.spent_usd = locked_run.spent_usd

    months_with_data: dict[str, dict] = {}
    saved_snaps = 0
    saved_organics = 0

    for snap in fetch.snapshots:
        # Lookup ONLY within this run — never re-link another run's snapshot.
        existing = db.scalar(
            select(SerpSnapshot).where(
                SerpSnapshot.run_id == run.id,
                SerpSnapshot.provider == snap.provider,
                SerpSnapshot.keyword_id == keyword.id,
                SerpSnapshot.location_code == query.location_code,
                SerpSnapshot.language_code == query.language_code,
                SerpSnapshot.observed_at == snap.observed_at,
            )
        )
        if existing:
            # Idempotent retry / overlapping query in the same run: keep rows + depth.
            # Do not rewrite run_query_id (avoids moving ownership inside the run too).
            row = existing
        else:
            row = SerpSnapshot(
                run_id=run.id,
                run_query_id=query.id,
                keyword_id=keyword.id,
                location_code=query.location_code,
                language_code=query.language_code,
                observed_at=snap.observed_at,
                observed_month=snap.observed_month,
                provider=snap.provider,
                organic_count=0,
                raw_json_path=str(raw_path),
            )
            db.add(row)
            db.flush()
            saved_snaps += 1

            order = 0
            organic_kept = 0
            for item in snap.organic_items:
                if item.rank_group is not None and item.rank_group > run.depth:
                    continue
                parts = parse_result_url(item.url, item.domain)
                db.add(
                    SerpResult(
                        snapshot_id=row.id,
                        item_order=order,
                        result_type="organic",
                        rank_group=item.rank_group,
                        rank_absolute=item.rank_absolute,
                        url=item.url,
                        title=item.title,
                        hostname=parts.hostname,
                        registrable_domain=parts.registrable_domain,
                        provider_domain=parts.provider_domain,
                        subdomain=parts.subdomain,
                    )
                )
                order += 1
                organic_kept += 1
                saved_organics += 1
            row.organic_count = organic_kept

        bucket = months_with_data.setdefault(
            snap.observed_month, {"snapshot_count": 0, "organic_count": 0}
        )
        bucket["snapshot_count"] += 1
        bucket["organic_count"] += row.organic_count

    # Update coverage for planned months in this query's range
    y, m = query.range_from.year, query.range_from.month
    end = (query.range_to.year, query.range_to.month)
    while (y, m) <= end:
        month = f"{y:04d}-{m:02d}"
        cov = db.scalar(
            select(Coverage).where(
                Coverage.run_id == run.id,
                Coverage.keyword_id == keyword.id,
                Coverage.location_code == query.location_code,
                Coverage.language_code == query.language_code,
                Coverage.month == month,
            )
        )
        if cov:
            if month in months_with_data:
                info = months_with_data[month]
                cov.snapshot_count = info["snapshot_count"]
                cov.organic_count = info["organic_count"]
                if info["organic_count"] > 0 and info["organic_count"] < run.depth:
                    cov.status = "PARTIAL_DEPTH"
                else:
                    cov.status = "AVAILABLE"
            elif fetch.error or (fetch.task_status_code and fetch.task_status_code != 20000):
                cov.status = "API_ERROR"
            else:
                cov.status = "NO_SNAPSHOT"
        m += 1
        if m > 12:
            y, m = y + 1, 1

    db.flush()
    return {
        "saved_snapshots": saved_snaps,
        "saved_organics": saved_organics,
        "cost_usd": str(cost),
        "months_with_data": list(months_with_data.keys()),
    }
