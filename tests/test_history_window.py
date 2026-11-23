from datetime import date

import pytest

from app.providers.dates import HistoryWindowError, earliest_allowed_date, validate_history_window


def test_earliest_allowed_respects_365_days(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_MAX_HISTORY_DAYS", "365")
    from app.config import get_settings

    get_settings.cache_clear()
    today = date(2026, 11, 19)
    assert earliest_allowed_date(today) == date(2025, 11, 19)


def test_rejects_old_date_from(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_MAX_HISTORY_DAYS", "365")
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(HistoryWindowError):
        validate_history_window(date(2022, 5, 1), date(2022, 5, 31), today=date(2026, 11, 19))


def test_allows_recent_window(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_MAX_HISTORY_DAYS", "365")
    from app.config import get_settings

    get_settings.cache_clear()
    fr, to = validate_history_window(date(2026, 1, 1), date(2026, 3, 31), today=date(2026, 11, 19))
    assert fr == date(2026, 1, 1)
    assert to == date(2026, 3, 31)


def test_allows_omit_dates(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_MAX_HISTORY_DAYS", "365")
    from app.config import get_settings

    get_settings.cache_clear()
    assert validate_history_window(None, None, today=date(2026, 11, 19)) == (None, None)
