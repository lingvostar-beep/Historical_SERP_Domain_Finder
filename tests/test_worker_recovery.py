"""UC-02 / §12 — reclaim in-flight work; pause must not leave queries as PAUSED."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.worker import recovery


def test_reclaim_serp_run_updates_running_and_paused_queries():
    db = MagicMock()
    # rowcount for two update() calls
    db.execute.side_effect = [MagicMock(rowcount=2), MagicMock(rowcount=1)]
    run_id = uuid4()
    got = recovery.reclaim_serp_run(db, run_id)
    assert got == {"queries_running_to_queued": 2, "queries_paused_to_queued": 1}
    assert db.execute.call_count == 2


def test_reclaim_availability_job_updates_checking():
    db = MagicMock()
    db.execute.return_value = MagicMock(rowcount=5)
    got = recovery.reclaim_availability_job(db, uuid4())
    assert got == {"items_checking_to_queued": 5}


def test_recover_on_startup_skips_paused_runs():
    run_paused = MagicMock()
    run_paused.status = "PAUSED"
    run_queued = MagicMock()
    run_queued.status = "QUEUED"
    rid_paused, rid_queued = uuid4(), uuid4()

    db = MagicMock()
    with (
        patch.object(recovery, "SessionLocal", return_value=db),
        patch.object(recovery, "reclaim_orphans", return_value={"ok": 1}),
        patch.object(
            recovery,
            "list_resumable_run_ids",
            return_value=[rid_paused, rid_queued],
        ),
        patch.object(recovery, "list_resumable_job_ids", return_value=[]),
        patch("app.worker.serp_worker.start_run_async", return_value=True) as start_run,
        patch("app.worker.availability_worker.start_availability_job_async"),
    ):
        db.get.side_effect = lambda model, rid: {
            rid_paused: run_paused,
            rid_queued: run_queued,
        }.get(rid)
        stats = recovery.recover_workers_on_startup()

    assert stats["started_runs"] == 1
    start_run.assert_called_once_with(rid_queued)
