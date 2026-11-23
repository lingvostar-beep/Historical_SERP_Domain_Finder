"""Cross-run snapshot isolation — no theft via run_query_id rewrite."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.models import SerpSnapshot
from app.services import persist_serp


def test_snapshot_unique_is_run_scoped():
    uq_names = [
        getattr(item, "name", None)
        for item in SerpSnapshot.__table_args__
        if getattr(item, "name", None)
    ]
    assert "uq_run_provider_snapshot" in uq_names
    assert "uq_provider_snapshot" not in uq_names
    assert "run_id" in SerpSnapshot.__table__.c


def test_persist_lookup_filters_by_run_id():
    src = inspect.getsource(persist_serp.persist_fetch)
    assert "SerpSnapshot.run_id == run.id" in src
    assert "row.run_query_id = query.id" not in src
    assert "run_id=run.id" in src


def test_migration_drops_global_unique():
    text = Path("alembic/versions/20261123_0003_snapshot_run_isolation.py").read_text(
        encoding="utf-8"
    )
    assert 'revision = "20261123_0003"' in text
    assert 'down_revision = "20261120_0002"' in text
    assert "uq_run_provider_snapshot" in text
    assert 'op.drop_constraint("uq_provider_snapshot"' in text
