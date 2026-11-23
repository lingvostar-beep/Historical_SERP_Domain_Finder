"""Contract tests against committed Spike fixtures (TZ §17 / Stage 3)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.providers.dataforseo import parse_historical_response
from app.providers.whoisfreaks import map_whoisfreaks_status
from app.services.domains import parse_result_url

FIX = Path(__file__).resolve().parent / "fixtures" / "spike"


def _load(name: str) -> dict:
    path = FIX / name
    assert path.is_file(), f"missing fixture {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_dir_has_no_apikey_literals():
    for path in FIX.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "apiKey=" not in text
        assert "DATAFORSEO_PASSWORD" not in text


def test_amazon_au_sep_one_snapshot_organics_and_cost():
    body = _load("diag_current_amazon_au_sep.json")
    assert body["status_code"] == 20000
    assert Decimal(str(body["cost"])) == Decimal("0.00012")

    parsed = parse_historical_response(body, "dataforseo_google_current")
    assert parsed.task_status_code == 20000
    assert len(parsed.snapshots) == 1
    snap = parsed.snapshots[0]
    assert snap.observed_month == "2026-09"
    assert snap.organic_count >= 1
    assert all(i.rank_group is not None for i in snap.organic_items[:3])
    # organic-only: parser drops non-organic types if present in raw
    assert parsed.cost_usd == Decimal("0.00012")


def test_amazon_au_sep_psl_on_fixture_urls():
    body = _load("diag_current_amazon_au_sep.json")
    parsed = parse_historical_response(body, "dataforseo_google_current")
    urls = [i.url for i in parsed.snapshots[0].organic_items if i.url]
    assert urls
    regs = {parse_result_url(u).registrable_domain for u in urls}
    regs.discard(None)
    assert regs
    # AU commerce often lands on amazon.com.au
    assert any(d and d.endswith(".com.au") or d == "amazon.com" for d in regs)


def test_casino_au_nodate_six_snapshots_kept():
    body = _load("diag_current_casino_au_nodate_slim.json")
    assert Decimal(str(body["cost"])) == Decimal("0.00072")
    parsed = parse_historical_response(body, "dataforseo_google_current")
    assert len(parsed.snapshots) == 6
    months = [s.observed_month for s in parsed.snapshots]
    assert len(months) == len(set(months))  # distinct months in this fixture
    assert parsed.cost_usd == Decimal("0.00072")
    # each slim snap still has some organics
    assert all(s.organic_count >= 1 for s in parsed.snapshots)


def test_casino_au_slim_excludes_non_organic_from_domain_list():
    body = _load("diag_current_casino_au_nodate_slim.json")
    parsed = parse_historical_response(body, "dataforseo_google_current")
    for snap in parsed.snapshots:
        for item in snap.organic_items:
            # OrganicItem comes only from type==organic in parser
            assert item.url or item.domain


def test_empty_sparse_month_zero_snapshots():
    body = _load("diag_current_casino_us_sep.json")
    parsed = parse_historical_response(body, "dataforseo_google_current")
    assert parsed.task_status_code in {20000, None} or parsed.task_status_code == 20000
    # empty archive month → no datetime items
    assert parsed.snapshots == []
    assert Decimal(str(body.get("cost") or 0)) == Decimal("0")


def test_old_date_from_task_40501():
    body = _load("raw_dfs_spike-legacy-au-2022-05_20261119T114727Z.json")
    assert body["status_code"] == 20000
    parsed = parse_historical_response(body, "dataforseo_legacy")
    assert parsed.task_status_code == 40501
    assert parsed.snapshots == []
    msg = (parsed.task_status_message or "").lower()
    assert "date_from" in msg or "invalid" in msg


def test_whoisfreaks_spike_enums_map_to_internal_statuses():
    body = _load("raw_whoisfreaks_20261119T114732Z.json")
    rows = body["bulk_domain_availability_response"]
    by_domain = {r["domain"]: r["availability"] for r in rows}

    assert map_whoisfreaks_status(by_domain["google.com"]) == "TAKEN"
    assert map_whoisfreaks_status(by_domain["example.com"]) == "TAKEN"
    assert map_whoisfreaks_status(by_domain["example.com.au"]) == "TAKEN"
    assert map_whoisfreaks_status(by_domain["hsdf-spike-1795088850.com"]) == "AVAILABLE_PRELIMINARY"
    assert map_whoisfreaks_status(by_domain["this-tld-should-fail.invalidtld"]) == "UNKNOWN"

    # unsupported / failed row must not become AVAILABLE
    bad = next(r for r in rows if r["domain"].endswith("invalidtld"))
    assert bad.get("status") is False
    assert map_whoisfreaks_status(bad["availability"]) not in {
        "AVAILABLE_PRELIMINARY",
        "AVAILABLE_CONFIRMED",
    }


def test_whoisfreaks_batch_links_by_domain_field():
    body = _load("raw_whoisfreaks_20261119T114732Z.json")
    rows = body["bulk_domain_availability_response"]
    requested = [
        "google.com",
        "hsdf-spike-1795088850.com",
        "this-tld-should-fail.invalidtld",
        "example.com.au",
        "example.com",
    ]
    got = {r["domain"] for r in rows}
    assert set(requested) == got


@pytest.mark.parametrize(
    "fixture,expect_snaps,expect_cost",
    [
        ("diag_current_amazon_au_sep.json", 1, "0.00012"),
        ("diag_current_casino_au_nodate_slim.json", 6, "0.00072"),
        ("diag_current_casino_us_sep.json", 0, "0"),
    ],
)
def test_cost_and_snapshot_matrix(fixture: str, expect_snaps: int, expect_cost: str):
    body = _load(fixture)
    parsed = parse_historical_response(body, "dataforseo_google_current")
    assert len(parsed.snapshots) == expect_snaps
    assert parsed.cost_usd == Decimal(expect_cost)
