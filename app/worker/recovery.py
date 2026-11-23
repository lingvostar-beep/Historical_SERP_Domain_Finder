"""Durable worker recovery after process restart (TZ §12 / UC-02).

Postgres is the queue source of truth. In-process threads die with the API;
on startup we reclaim in-flight rows and restart unfinished runs/jobs.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AvailabilityJob, AvailabilityJobItem, Run, RunQuery

log = logging.getLogger(__name__)

ACTIVE_RUN = {"QUEUED", "RUNNING", "PAUSED"}
ACTIVE_JOB = {"QUEUED", "RUNNING", "PAUSED"}


def reclaim_serp_run(db: Session, run_id: uuid.UUID) -> dict[str, int]:
    """Return in-flight SERP queries to QUEUED so resume can pick them up."""
    n_running = db.execute(
        update(RunQuery)
        .where(RunQuery.run_id == run_id, RunQuery.status == "RUNNING")
        .values(status="QUEUED", last_error="reclaimed_after_interrupt")
    ).rowcount
    # Legacy pause race left query.status=PAUSED — treat as unfinished work.
    n_paused = db.execute(
        update(RunQuery)
        .where(RunQuery.run_id == run_id, RunQuery.status == "PAUSED")
        .values(status="QUEUED", last_error="reclaimed_from_paused_query")
    ).rowcount
    return {"queries_running_to_queued": int(n_running or 0), "queries_paused_to_queued": int(n_paused or 0)}


def reclaim_availability_job(db: Session, job_id: uuid.UUID) -> dict[str, int]:
    n_checking = db.execute(
        update(AvailabilityJobItem)
        .where(
            AvailabilityJobItem.job_id == job_id,
            AvailabilityJobItem.status == "CHECKING",
        )
        .values(status="QUEUED", last_error="reclaimed_after_interrupt")
    ).rowcount
    return {"items_checking_to_queued": int(n_checking or 0)}


def reclaim_orphans(db: Session) -> dict:
    """Reclaim all orphaned in-flight work across the DB."""
    serp_q = db.execute(
        update(RunQuery)
        .where(RunQuery.status.in_(["RUNNING", "PAUSED"]))
        .values(status="QUEUED")
    ).rowcount
    avail_i = db.execute(
        update(AvailabilityJobItem)
        .where(AvailabilityJobItem.status == "CHECKING")
        .values(status="QUEUED")
    ).rowcount

    # Runs stuck in RUNNING with remaining work → QUEUED (worker will set RUNNING)
    run_ids = db.scalars(select(Run.id).where(Run.status == "RUNNING")).all()
    runs_reset = 0
    for rid in run_ids:
        left = db.scalar(
            select(RunQuery.id)
            .where(RunQuery.run_id == rid, RunQuery.status == "QUEUED")
            .limit(1)
        )
        if left:
            run = db.get(Run, rid)
            if run:
                run.status = "QUEUED"
                runs_reset += 1
        else:
            # no work left — leave for finalize path on resume attempt
            pass

    job_ids = db.scalars(select(AvailabilityJob.id).where(AvailabilityJob.status == "RUNNING")).all()
    jobs_reset = 0
    for jid in job_ids:
        left = db.scalar(
            select(AvailabilityJobItem.id)
            .where(
                AvailabilityJobItem.job_id == jid,
                AvailabilityJobItem.status == "QUEUED",
            )
            .limit(1)
        )
        if left:
            job = db.get(AvailabilityJob, jid)
            if job:
                job.status = "QUEUED"
                jobs_reset += 1

    db.commit()
    return {
        "serp_queries_reclaimed": int(serp_q or 0),
        "availability_items_reclaimed": int(avail_i or 0),
        "runs_running_to_queued": runs_reset,
        "jobs_running_to_queued": jobs_reset,
    }


def list_resumable_run_ids(db: Session) -> list[uuid.UUID]:
    """Runs that still have QUEUED queries and are not terminal."""
    terminal = {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "CANCELED", "BUDGET_EXCEEDED"}
    rows = db.execute(
        select(Run.id, Run.status)
        .join(RunQuery, RunQuery.run_id == Run.id)
        .where(RunQuery.status == "QUEUED", Run.status.notin_(terminal))
        .distinct()
    ).all()
    out: list[uuid.UUID] = []
    for rid, status in rows:
        if status in ACTIVE_RUN or status == "QUEUED":
            out.append(rid)
    return out


def list_resumable_job_ids(db: Session) -> list[uuid.UUID]:
    terminal = {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "CANCELED", "BUDGET_EXCEEDED"}
    rows = db.execute(
        select(AvailabilityJob.id, AvailabilityJob.status)
        .join(AvailabilityJobItem, AvailabilityJobItem.job_id == AvailabilityJob.id)
        .where(
            AvailabilityJobItem.status == "QUEUED",
            AvailabilityJob.status.notin_(terminal),
        )
        .distinct()
    ).all()
    return [jid for jid, status in rows if status in ACTIVE_JOB or status == "QUEUED"]


def recover_workers_on_startup() -> dict:
    """Call from FastAPI startup: reclaim orphans and restart unfinished work."""
    from app.worker.availability_worker import start_availability_job_async
    from app.worker.serp_worker import start_run_async

    db = SessionLocal()
    try:
        stats = reclaim_orphans(db)
        run_ids = list_resumable_run_ids(db)
        job_ids = list_resumable_job_ids(db)

        # Auto-resume only QUEUED/RUNNING work — leave PAUSED for the operator.
        started_runs = 0
        for rid in run_ids:
            run = db.get(Run, rid)
            if not run or run.status == "PAUSED":
                continue
            if run.status != "QUEUED":
                run.status = "QUEUED"
            db.commit()
            if start_run_async(rid):
                started_runs += 1

        started_jobs = 0
        for jid in job_ids:
            job = db.get(AvailabilityJob, jid)
            if not job or job.status == "PAUSED":
                continue
            if job.status != "QUEUED":
                job.status = "QUEUED"
            db.commit()
            if start_availability_job_async(jid):
                started_jobs += 1

        stats["resumable_runs"] = len(run_ids)
        stats["resumable_jobs"] = len(job_ids)
        stats["started_runs"] = started_runs
        stats["started_jobs"] = started_jobs
        log.info("worker recovery: %s", stats)
        return stats
    except Exception:  # noqa: BLE001
        log.exception("worker recovery failed")
        return {"error": "recovery_failed"}
    finally:
        db.close()
