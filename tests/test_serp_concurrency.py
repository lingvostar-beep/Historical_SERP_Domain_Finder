"""TZ §8.2 — concurrent SERP query claiming."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.config import Settings
from app.worker import serp_worker
from app.worker.serp_worker import claim_next_queued_query


def test_default_concurrency_is_five():
    assert Settings.model_fields["dataforseo_concurrency"].default == 5


def test_claim_next_queued_query_sql_uses_skip_locked():
    db = MagicMock()
    run = MagicMock()
    run.status = "RUNNING"
    run.spent_usd = Decimal("0")
    run.budget_cap = Decimal("10")
    qid = uuid4()

    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = run
    cand_result = MagicMock()
    cand_result.first.return_value = (qid, date(2026, 1, 1), date(2026, 3, 31))
    inflight_result = MagicMock()
    inflight_result.all.return_value = []

    db.execute.side_effect = [run_result, cand_result, inflight_result, MagicMock()]

    with patch.object(serp_worker, "projected_query_cost_usd", return_value=Decimal("0.00036")):
        got = claim_next_queued_query(db, uuid4())

    assert got == qid
    # SELECT candidate uses SKIP LOCKED
    cand_sql = str(db.execute.call_args_list[1][0][0])
    assert "FOR UPDATE SKIP LOCKED" in cand_sql
    assert "QUEUED" in cand_sql


def test_claim_returns_none_when_empty():
    db = MagicMock()
    run = MagicMock()
    run.status = "RUNNING"
    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = run
    empty = MagicMock()
    empty.first.return_value = None
    db.execute.side_effect = [run_result, empty]
    assert claim_next_queued_query(db, uuid4()) is None


def test_claim_soft_stops_when_budget_too_low():
    db = MagicMock()
    run = MagicMock()
    run.status = "RUNNING"
    run.spent_usd = Decimal("0.99")
    run.budget_cap = Decimal("1.00")
    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = run
    cand = MagicMock()
    cand.first.return_value = (uuid4(), date(2026, 1, 1), date(2026, 12, 31))
    inflight = MagicMock()
    inflight.all.return_value = []
    db.execute.side_effect = [run_result, cand, inflight]

    with (
        patch.object(serp_worker, "projected_query_cost_usd", return_value=Decimal("0.05")),
        patch.object(serp_worker, "set_run_status") as set_status,
    ):
        got = claim_next_queued_query(db, uuid4())

    assert got is None
    set_status.assert_called_once()
    assert set_status.call_args[0][2] == "BUDGET_EXCEEDED"


def test_process_run_respects_concurrency_cap():
    run_id = uuid4()
    fake_run = MagicMock()
    fake_run.status = "CANCELED"
    db = MagicMock()
    db.get.return_value = fake_run

    with (
        patch.object(serp_worker, "SessionLocal", return_value=db),
        patch.object(serp_worker, "get_settings") as gs,
    ):
        gs.return_value.dataforseo_concurrency = 99
        out = serp_worker.process_run(run_id)
        assert out == {"stopped": "CANCELED"}
