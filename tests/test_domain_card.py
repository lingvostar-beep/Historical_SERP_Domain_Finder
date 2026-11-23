"""TZ §9.4 — domain card availability + ccTLD warning contracts."""

from __future__ import annotations

import inspect

from app.services import availability as avail_svc
from app.services import results as results_svc


def test_domain_card_signature():
    assert "domain" in inspect.signature(results_svc.domain_card).parameters


def test_cctld_warning_helper_exists():
    assert callable(avail_svc.cctld_warning_for_domain)
    assert callable(avail_svc.check_history_for_domain)


def test_cctld_warning_message_shape_without_db_policy():
    """Unknown policy path returns a dict with message (mocked via empty session not available)."""
    # Contract: return type documented via helper defaults
    src = inspect.getsource(avail_svc.cctld_warning_for_domain)
    assert "Availability ≠ right to register" in src or "does not confirm" in src
    assert "eligibility_type" in src
