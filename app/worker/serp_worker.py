"""In-process SERP worker — concurrent query pool (TZ §8.2, default 5)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Keyword, Run, RunQuery
from app.providers import get_serp_provider
from app.providers.types import SerpFetchRequest
from app.services.estimate import projected_query_cost_usd
from app.services.persist_serp import persist_fetch
from app.services.runs import run_progress, set_run_status
from app.services.serp_retry import backoff_seconds, is_retryable

log = logging.getLogger(__name__)

_lock = threading.Lock()
_active: dict[str, threading.Thread] = {}

# TZ §11 — warn / soft-stop when approaching the cap (before hard overspend).
BUDGET_WARN_RATIO = Decimal("0.80")


def _budget_allows(run: Run, projected: Decimal, *, reserved: Decimal = Decimal("0")) -> bool:
    return (run.spent_usd or Decimal("0")) + reserved + projected <= run.budget_cap


def _inflight_reserved_usd(db: Session, run_id: uuid.UUID) -> Decimal:
    """Sum max projected cost of queries already RUNNING (pre-flight reservations)."""
    rows = db.execute(
        select(RunQuery.range_from, RunQuery.range_to).where(
            RunQuery.run_id == run_id,
            RunQuery.status == "RUNNING",
        )
    ).all()
    total = Decimal("0")
    for fr, to in rows:
        total += projected_query_cost_usd(fr, to)
    return total


def claim_next_queued_query(db: Session, run_id: uuid.UUID) -> uuid.UUID | None:
    """Claim one QUEUED query with run lock + period-aware budget pre-flight (§8.3)."""
    run = db.execute(select(Run).where(Run.id == run_id).with_for_update()).scalar_one_or_none()
    if not run or run.status in {"PAUSED", "CANCELED", "BUDGET_EXCEEDED"}:
        db.commit()
        return None

    cand = db.execute(
        text(
            """
            SELECT id, range_from, range_to FROM run_queries
            WHERE run_id = :run_id AND status = 'QUEUED'
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ),
        {"run_id": run_id},
    ).first()
    if not cand:
        db.commit()
        return None

    qid = uuid.UUID(str(cand[0]))
    projected = projected_query_cost_usd(cand[1], cand[2])
    reserved = _inflight_reserved_usd(db, run_id)
    if not _budget_allows(run, projected, reserved=reserved):
        # Soft-stop: do not start a call that could push past the cap (§4 / §14.11).
        set_run_status(db, run_id, "BUDGET_EXCEEDED")
        db.commit()
        log.info(
            "budget soft-stop run=%s spent=%s reserved=%s projected=%s cap=%s",
            run_id,
            run.spent_usd,
            reserved,
            projected,
            run.budget_cap,
        )
        return None

    db.execute(
        text("UPDATE run_queries SET status = 'RUNNING' WHERE id = :id AND status = 'QUEUED'"),
        {"id": qid},
    )
    db.commit()
    return qid


def process_one_query(
    db: Session,
    query_id: uuid.UUID,
    *,
    already_claimed: bool = False,
) -> dict:
    query = db.get(RunQuery, query_id)
    if not query:
        raise KeyError("query not found")
    run = db.get(Run, query.run_id)
    if not run:
        raise KeyError("run not found")
    keyword = db.get(Keyword, query.keyword_id)
    if not keyword:
        raise KeyError("keyword not found")

    if run.status in {"PAUSED", "CANCELED", "BUDGET_EXCEEDED"}:
        if query.status == "RUNNING":
            query.status = "QUEUED" if run.status == "PAUSED" else (
                "CANCELED" if run.status == "CANCELED" else "FAILED"
            )
            db.commit()
        return {"skipped": True, "reason": run.status}

    settings = get_settings()
    # Re-check under lock: reserve months×price for this query's full period (§8.3).
    projected = projected_query_cost_usd(query.range_from, query.range_to)
    locked_run = db.execute(select(Run).where(Run.id == run.id).with_for_update()).scalar_one()
    # Exclude this query from inflight sum if already RUNNING (claimed).
    reserved = _inflight_reserved_usd(db, run.id)
    if already_claimed and query.status == "RUNNING":
        reserved = max(Decimal("0"), reserved - projected)
    if not _budget_allows(locked_run, projected, reserved=reserved):
        query.status = "QUEUED"
        query.last_error = "deferred_budget_soft_stop"
        set_run_status(db, run.id, "BUDGET_EXCEEDED")
        db.commit()
        return {"skipped": True, "reason": "BUDGET_EXCEEDED"}

    if not already_claimed:
        query.status = "RUNNING"
        db.commit()

    provider = get_serp_provider(run.source)
    req = SerpFetchRequest(
        keyword=keyword.normalized_text,
        location_code=query.location_code,
        language_code=query.language_code,
        date_from=query.range_from,
        date_to=query.range_to,
        tag=f"run-{run.id}-q-{query.id}",
    )

    max_attempts = max(1, int(settings.dataforseo_max_retries))
    base_backoff = float(settings.dataforseo_retry_base_seconds)
    fetch = None
    latency_ms = 0
    retries_used = 0

    def _abort_if_run_stopped() -> dict | None:
        """Run-level pause/cancel must not leave the query stuck as PAUSED/RUNNING."""
        q = db.get(RunQuery, query_id)
        r = db.get(Run, q.run_id)
        if r.status == "PAUSED":
            # Unfinished work stays QUEUED so resume can pick it up (UC-02 / §14.12).
            q.status = "QUEUED"
            db.commit()
            return {"skipped": True, "reason": "PAUSED"}
        if r.status == "CANCELED":
            q.status = "CANCELED"
            db.commit()
            return {"skipped": True, "reason": "CANCELED"}
        if r.status == "BUDGET_EXCEEDED":
            q.status = "FAILED"
            q.last_error = "budget_exceeded"
            db.commit()
            return {"skipped": True, "reason": "BUDGET_EXCEEDED"}
        return None

    for attempt in range(1, max_attempts + 1):
        stopped = _abort_if_run_stopped()
        if stopped:
            return stopped

        query = db.get(RunQuery, query_id)
        query.attempts = (query.attempts or 0) + 1
        db.commit()

        started = time.perf_counter()
        fetch = provider.fetch(req)
        latency_ms = round((time.perf_counter() - started) * 1000)

        ok = not fetch.error and (
            not fetch.task_status_code or fetch.task_status_code == 20000
        )
        if ok or not is_retryable(fetch) or attempt >= max_attempts:
            break

        retries_used += 1
        sleep_for = backoff_seconds(attempt - 1, base=base_backoff)
        log.warning(
            "serp retry query=%s attempt=%s/%s http=%s task=%s sleep=%.2fs err=%s",
            query_id,
            attempt,
            max_attempts,
            fetch.http_status,
            fetch.task_status_code,
            sleep_for,
            (fetch.error or fetch.task_status_message or "")[:160],
        )
        # Interruptible backoff so pause is noticed during retries.
        left = sleep_for
        while left > 0:
            stopped = _abort_if_run_stopped()
            if stopped:
                return stopped
            step = min(0.25, left)
            time.sleep(step)
            left -= step

    # Re-load after long HTTP / retries
    stopped = _abort_if_run_stopped()
    if stopped:
        return stopped

    query = db.get(RunQuery, query_id)
    run = db.get(Run, query.run_id)
    keyword = db.get(Keyword, query.keyword_id)

    assert fetch is not None
    result_meta = persist_fetch(
        db, run=run, query=query, keyword=keyword, fetch=fetch, latency_ms=latency_ms
    )

    if fetch.error or (fetch.task_status_code and fetch.task_status_code != 20000):
        query.status = "FAILED"
        query.last_error = fetch.error or fetch.task_status_message
        query.api_task_id = None
    else:
        query.status = "COMPLETED"
        query.last_error = None

    # Reload spent after persist; stop at/over cap and surface 80% approach.
    locked_run = db.execute(select(Run).where(Run.id == run.id).with_for_update()).scalar_one()
    spent = locked_run.spent_usd or Decimal("0")
    cap = locked_run.budget_cap or Decimal("0")
    if cap > 0 and spent >= cap:
        set_run_status(db, run.id, "BUDGET_EXCEEDED")
    elif cap > 0 and spent >= (cap * BUDGET_WARN_RATIO):
        # Approaching limit: block new claims that cannot fit another period.
        # In-flight finish; coordinator sees BUDGET_EXCEEDED only when next claim fails
        # OR when remaining headroom is below one month price.
        headroom = cap - spent
        min_unit = Decimal(str(settings.dataforseo_reference_price_per_snapshot))
        if headroom < min_unit:
            set_run_status(db, run.id, "BUDGET_EXCEEDED")

    db.commit()
    return {
        "ok": True,
        "query_id": str(query_id),
        **result_meta,
        "query_status": query.status,
        "retries_used": retries_used,
        "attempts": query.attempts,
        "projected_reserved_usd": str(projected),
    }


def finalize_run(db: Session, run_id: uuid.UUID) -> None:
    run = db.get(Run, run_id)
    if not run or run.status in {"CANCELED", "BUDGET_EXCEEDED"}:
        return
    statuses = db.scalars(select(RunQuery.status).where(RunQuery.run_id == run_id)).all()
    if any(s in {"QUEUED", "RUNNING"} for s in statuses):
        return
    failed = sum(1 for s in statuses if s == "FAILED")
    if failed:
        set_run_status(db, run_id, "COMPLETED_WITH_GAPS")
    else:
        set_run_status(db, run_id, "COMPLETED")
    db.commit()

    # Auto availability after SERP (TZ availability_mode)
    try:
        from app.services import availability as avail_svc
        from app.worker.availability_worker import start_availability_job_async

        job_id = avail_svc.maybe_enqueue_auto_after_serp(db, run_id)
        if job_id:
            db.commit()
            started = start_availability_job_async(job_id)
            log.info(
                "auto_after_serp run=%s job=%s worker_started=%s",
                run_id,
                job_id,
                started,
            )
    except Exception:  # noqa: BLE001
        log.exception("auto_after_serp failed for run %s", run_id)


def _process_claimed_query(run_id: uuid.UUID, query_id: uuid.UUID) -> dict:
    """Worker-thread entry: own DB session per claimed query."""
    db = SessionLocal()
    try:
        return process_one_query(db, query_id, already_claimed=True)
    except Exception:  # noqa: BLE001
        log.exception("query worker failed run=%s query=%s", run_id, query_id)
        try:
            q = db.get(RunQuery, query_id)
            if q and q.status == "RUNNING":
                q.status = "QUEUED"
                q.last_error = "worker_exception_requeued"
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("failed to requeue query %s", query_id)
        return {"ok": False, "query_id": str(query_id), "error": "worker_exception"}
    finally:
        db.close()


def process_run(run_id: uuid.UUID, *, max_queries: int | None = None) -> dict:
    settings = get_settings()
    concurrency = max(1, min(30, int(settings.dataforseo_concurrency)))
    processed = 0
    db = SessionLocal()
    try:
        from app.worker.recovery import reclaim_serp_run

        run = db.get(Run, run_id)
        if not run:
            raise KeyError("run not found")
        if run.status in {"CANCELED"}:
            return {"stopped": run.status}
        reclaim_serp_run(db, run_id)
        db.commit()
        set_run_status(db, run_id, "RUNNING")
        db.commit()
        log.info("serp process_run %s concurrency=%s", run_id, concurrency)

        with ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix=f"serp-{str(run_id)[:8]}",
        ) as pool:
            while True:
                db.refresh(run)
                if run.status in {"PAUSED", "CANCELED", "BUDGET_EXCEEDED"}:
                    break

                batch: list[uuid.UUID] = []
                while len(batch) < concurrency:
                    if max_queries is not None and processed + len(batch) >= max_queries:
                        break
                    qid = claim_next_queued_query(db, run_id)
                    if not qid:
                        break
                    batch.append(qid)

                if not batch:
                    break

                futures = {
                    pool.submit(_process_claimed_query, run_id, qid): qid for qid in batch
                }
                for fut in as_completed(futures):
                    processed += 1
                    try:
                        fut.result()
                    except Exception:  # noqa: BLE001
                        log.exception("future failed for query %s", futures[fut])

                if max_queries is not None and processed >= max_queries:
                    break

        finalize_run(db, run_id)
        progress = run_progress(db, run_id)
        progress["concurrency"] = concurrency
        progress["queries_processed_this_pass"] = processed
        return progress
    finally:
        db.close()


def start_run_async(run_id: uuid.UUID) -> bool:
    key = str(run_id)
    with _lock:
        t = _active.get(key)
        if t and t.is_alive():
            return False

        def _target() -> None:
            try:
                process_run(run_id)
            except Exception:  # noqa: BLE001
                log.exception("run worker failed %s", run_id)
            finally:
                with _lock:
                    _active.pop(key, None)

        thread = threading.Thread(target=_target, name=f"serp-run-{key[:8]}", daemon=True)
        _active[key] = thread
        thread.start()
        return True
