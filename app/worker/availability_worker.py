"""In-process availability worker (WhoisFreaks batches)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AvailabilityJob, AvailabilityJobItem
from app.providers.rate_limit import backoff_with_jitter
from app.providers.whoisfreaks import BATCH_MAX, WhoisFreaksProvider
from app.services.availability import (
    apply_batch_results,
    availability_batch_limit,
    job_progress,
)

log = logging.getLogger(__name__)
_lock = threading.Lock()
_active: dict[str, threading.Thread] = {}


def process_availability_job(job_id: uuid.UUID) -> dict:
    db = SessionLocal()
    provider = WhoisFreaksProvider()
    try:
        from app.worker.recovery import reclaim_availability_job

        job = db.get(AvailabilityJob, job_id)
        if not job:
            raise KeyError("job not found")
        reclaim_availability_job(db, job_id)
        job.status = "RUNNING"
        db.commit()

        while True:
            db.refresh(job)
            if job.status in {"PAUSED", "CANCELED"}:
                # Return in-flight CHECKING items to QUEUED for later resume.
                reclaim_availability_job(db, job_id)
                db.commit()
                break
            limit = availability_batch_limit(
                spent_credits=int(job.spent_credits or 0),
                budget_cap_credits=int(job.budget_cap_credits),
                spent_usd=Decimal(job.spent_usd or 0),
                budget_cap_usd=Decimal(job.budget_cap_usd),
                batch_max=BATCH_MAX,
            )
            if limit < 1:
                job.status = "BUDGET_EXCEEDED"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                break

            q_domains = db.scalars(
                select(AvailabilityJobItem.registrable_domain)
                .where(
                    AvailabilityJobItem.job_id == job_id,
                    AvailabilityJobItem.status == "QUEUED",
                )
                .limit(limit)
            ).all()
            if not q_domains:
                break

            # mark checking
            for dom in q_domains:
                row = db.scalar(
                    select(AvailabilityJobItem).where(
                        AvailabilityJobItem.job_id == job_id,
                        AvailabilityJobItem.registrable_domain == dom,
                    )
                )
                if row:
                    row.status = "CHECKING"
            db.commit()

            started = time.perf_counter()
            result = provider.check_many(list(q_domains))
            duration_ms = round((time.perf_counter() - started) * 1000)

            job = db.get(AvailabilityJob, job_id)
            if job.status in {"CANCELED", "PAUSED"}:
                reclaim_availability_job(db, job_id)
                db.commit()
                break

            # §15.9 — rate limit / transient: requeue, honour Retry-After via backoff
            rate_limited = result.http_status == 429 or (
                result.error or ""
            ).startswith("rate_limited")
            if rate_limited and result.credits_actual == 0:
                for dom in q_domains:
                    row = db.scalar(
                        select(AvailabilityJobItem).where(
                            AvailabilityJobItem.job_id == job_id,
                            AvailabilityJobItem.registrable_domain == dom,
                        )
                    )
                    if row:
                        row.status = "QUEUED"
                        row.last_error = result.error or "rate_limited_429"
                        row.attempt_count = (row.attempt_count or 0) + 1
                db.commit()
                time.sleep(backoff_with_jitter(1, base=2.0, cap=60.0))
                continue

            if result.error and not result.items:
                for dom in q_domains:
                    row = db.scalar(
                        select(AvailabilityJobItem).where(
                            AvailabilityJobItem.job_id == job_id,
                            AvailabilityJobItem.registrable_domain == dom,
                        )
                    )
                    if row:
                        row.status = "FAILED"
                        row.last_error = result.error
                        row.attempt_count = (row.attempt_count or 0) + 1
                db.commit()
                # stop on hard provider failure
                job.status = "FAILED"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                break

            apply_batch_results(
                db,
                job,
                list(q_domains),
                http_status=result.http_status,
                provider=result.provider,
                items=result.items,
                credits_actual=result.credits_actual,
                duration_ms=duration_ms,
                raw_response=result.raw_response or {"error": result.error},
            )
            db.commit()

            # §15.10.6 — requeue only per-domain failures (not whole-batch hard fail)
            requeued = 0
            for dom in q_domains:
                row = db.scalar(
                    select(AvailabilityJobItem).where(
                        AvailabilityJobItem.job_id == job_id,
                        AvailabilityJobItem.registrable_domain == dom,
                    )
                )
                if (
                    row
                    and row.status == "FAILED"
                    and (row.attempt_count or 0) < 3
                ):
                    row.status = "QUEUED"
                    row.last_error = (row.last_error or "") + ";requeued"
                    requeued += 1
            if requeued:
                db.commit()

            # Inter-batch pacing is the WhoisFreaks token bucket inside check_many (§15.9).

        job = db.get(AvailabilityJob, job_id)
        if job.status == "RUNNING":
            left = db.scalar(
                select(AvailabilityJobItem.id)
                .where(
                    AvailabilityJobItem.job_id == job_id,
                    AvailabilityJobItem.status.in_(["QUEUED", "CHECKING"]),
                )
                .limit(1)
            )
            failed = db.scalar(
                select(AvailabilityJobItem.id)
                .where(
                    AvailabilityJobItem.job_id == job_id,
                    AvailabilityJobItem.status == "FAILED",
                )
                .limit(1)
            )
            job.status = "COMPLETED_WITH_GAPS" if failed or left else "COMPLETED"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()

        return job_progress(db, job_id)
    finally:
        db.close()


def start_availability_job_async(job_id: uuid.UUID) -> bool:
    key = str(job_id)
    with _lock:
        t = _active.get(key)
        if t and t.is_alive():
            return False

        def _target() -> None:
            try:
                process_availability_job(job_id)
            except Exception:  # noqa: BLE001
                log.exception("availability job failed %s", job_id)
            finally:
                with _lock:
                    _active.pop(key, None)

        thread = threading.Thread(target=_target, name=f"avail-{key[:8]}", daemon=True)
        _active[key] = thread
        thread.start()
        return True
