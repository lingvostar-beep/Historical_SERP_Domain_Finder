"""TZ §9.1 — Domains tab helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.results import _check_age


def test_check_age_buckets():
    now = datetime.now(timezone.utc)
    assert _check_age(None) is None
    assert _check_age(now - timedelta(seconds=10)).endswith("s")
    assert _check_age(now - timedelta(minutes=5)).endswith("m")
    assert _check_age(now - timedelta(hours=3)).endswith("h")
    assert _check_age(now - timedelta(days=2)).endswith("d")
