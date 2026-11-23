"""UC-03 — last_seen filter is server-side (HAVING), not a client page slice."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.results import parse_last_seen_before


def test_parse_last_seen_before_is_inclusive_utc_eod():
    cutoff = parse_last_seen_before("2026-09-15")
    assert cutoff == datetime(2026, 9, 15, 23, 59, 59, tzinfo=timezone.utc)
    # Same calendar day still included
    assert datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc) <= cutoff
    assert datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc) > cutoff


def test_parse_strips_time_suffix_if_present():
    cutoff = parse_last_seen_before("2026-01-02T99:99:99")
    assert cutoff.date().isoformat() == "2026-01-02"
