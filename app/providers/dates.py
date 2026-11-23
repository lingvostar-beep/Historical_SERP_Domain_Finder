"""SERP history window helpers — Spike 2026-11-19: max ~365 days."""

from __future__ import annotations

from datetime import date, timedelta

from app.config import get_settings


class HistoryWindowError(ValueError):
    """Raised when requested dates are outside the proven provider window."""


def earliest_allowed_date(today: date | None = None) -> date:
    settings = get_settings()
    today = today or date.today()
    return today - timedelta(days=settings.dataforseo_max_history_days)


def validate_history_window(
    date_from: date | None,
    date_to: date | None,
    *,
    today: date | None = None,
) -> tuple[date | None, date | None]:
    """
    Enforce Spike constraint: do not send old date_from that DataForSEO rejects (40501).

    Returns normalized (from, to). Either bound may be None (omit in API → provider default window).
    """
    today = today or date.today()
    earliest = earliest_allowed_date(today)

    if date_to is not None and date_to > today:
        raise HistoryWindowError(f"date_to {date_to} is in the future")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HistoryWindowError("date_from must be <= date_to")

    if date_from is not None and date_from < earliest:
        raise HistoryWindowError(
            f"date_from {date_from} is older than allowed window "
            f"(earliest={earliest}, max_history_days={get_settings().dataforseo_max_history_days}). "
            "Deep history is out of MVP for DataForSEO on this account."
        )
    if date_to is not None and date_to < earliest:
        raise HistoryWindowError(
            f"date_to {date_to} is entirely outside the allowed ~365-day window (earliest={earliest})"
        )

    return date_from, date_to
