"""TZ §8.3 / §14.11 — period-aware SERP budget pre-flight + soft-stop."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.estimate import months_spanned, projected_query_cost_usd


def test_projected_query_cost_scales_with_months(monkeypatch):
    monkeypatch.setattr(
        "app.services.estimate.get_settings",
        lambda: type("S", (), {"dataforseo_reference_price_per_snapshot": 0.00012})(),
    )
    one = projected_query_cost_usd(date(2026, 9, 1), date(2026, 9, 30))
    twelve = projected_query_cost_usd(date(2026, 1, 1), date(2026, 12, 31))
    assert months_spanned(date(2026, 1, 1), date(2026, 12, 31)) == 12
    assert one == Decimal("0.000120")
    assert twelve == Decimal("0.001440")
    assert twelve == one * 12


def test_budget_allows_accounts_for_reserved():
    from app.worker.serp_worker import _budget_allows

    run = type(
        "R",
        (),
        {"spent_usd": Decimal("0.50"), "budget_cap": Decimal("1.00")},
    )()
    assert _budget_allows(run, Decimal("0.40"), reserved=Decimal("0.10")) is True
    assert _budget_allows(run, Decimal("0.41"), reserved=Decimal("0.10")) is False
