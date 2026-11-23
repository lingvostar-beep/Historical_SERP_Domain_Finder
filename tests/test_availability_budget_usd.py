"""Availability spend-cap: credits AND budget_cap_usd (§15.9 / §15.10.10)."""

from __future__ import annotations

from decimal import Decimal

from app.services.availability import availability_batch_limit


def test_usd_cap_stops_before_credits_exhausted():
    # 50 credits room, but only $0.01 left at $0.004/credit → 2 domains
    n = availability_batch_limit(
        spent_credits=0,
        budget_cap_credits=50,
        spent_usd=Decimal("0"),
        budget_cap_usd=Decimal("0.010"),
        batch_max=100,
        rate_usd=Decimal("0.004"),
    )
    assert n == 2


def test_credit_cap_binds_when_usd_is_looser():
    n = availability_batch_limit(
        spent_credits=48,
        budget_cap_credits=50,
        spent_usd=Decimal("0"),
        budget_cap_usd=Decimal("100"),
        batch_max=100,
        rate_usd=Decimal("0.004"),
    )
    assert n == 2


def test_batch_max_binds():
    n = availability_batch_limit(
        spent_credits=0,
        budget_cap_credits=500,
        spent_usd=Decimal("0"),
        budget_cap_usd=Decimal("100"),
        batch_max=100,
        rate_usd=Decimal("0.004"),
    )
    assert n == 100


def test_exhausted_usd_returns_zero():
    n = availability_batch_limit(
        spent_credits=1,
        budget_cap_credits=100,
        spent_usd=Decimal("0.004"),
        budget_cap_usd=Decimal("0.004"),
        batch_max=100,
        rate_usd=Decimal("0.004"),
    )
    assert n == 0
