"""Contract-level acceptance for TZ §14 (SERP) + §15.10 (availability)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.providers.availability_types import AVAILABLE_FILTER
from app.providers.dataforseo import parse_historical_response
from app.providers.whoisfreaks import BATCH_MAX, map_whoisfreaks_status
from app.services.domains import parse_result_url
from app.services.estimate import estimate_serp
from app.services.serp_retry import is_retryable
from app.providers.types import SerpFetchResult


def test_s14_2_multigeo_estimate_combinations():
    est = estimate_serp(
        unique_keywords=3,
        region_language_pairs=2,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )
    assert est.query_combinations == 6


def test_s14_3_all_snapshots_kept():
    body = {
        "status_code": 20000,
        "cost": 0.00072,
        "tasks": [
            {
                "status_code": 20000,
                "status_message": "Ok",
                "result": [
                    {
                        "items": [
                            {
                                "datetime": f"2026-0{i}-01 12:00:00 +00:00",
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "rank_absolute": 1,
                                        "url": f"https://ex{i}.com/",
                                        "domain": f"ex{i}.com",
                                    }
                                ],
                            }
                            for i in range(1, 7)
                        ]
                    }
                ],
            }
        ],
    }
    parsed = parse_historical_response(body, "dataforseo_google_current")
    assert len(parsed.snapshots) == 6


def test_s14_5_rank_group_not_absolute():
    body = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "datetime": "2026-09-01 12:00:00 +00:00",
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 5,
                                        "rank_absolute": 12,
                                        "url": "https://a.com/",
                                        "domain": "a.com",
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ],
    }
    snap = parse_historical_response(body, "test").snapshots[0]
    assert snap.organic_items[0].rank_group == 5
    assert snap.organic_items[0].rank_absolute == 12


def test_s14_6_paa_ads_excluded_from_organic():
    body = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "datetime": "2026-09-01 12:00:00 +00:00",
                                "items": [
                                    {"type": "paid", "rank_group": 1, "url": "https://ad.com/", "domain": "ad.com"},
                                    {
                                        "type": "people_also_ask",
                                        "rank_group": 1,
                                        "url": "https://paa.com/",
                                        "domain": "paa.com",
                                    },
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://org.com/",
                                        "domain": "org.com",
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ],
    }
    snap = parse_historical_response(body, "test").snapshots[0]
    assert len(snap.organic_items) == 1
    assert snap.organic_items[0].domain == "org.com"


def test_s14_7_psl_com_au_and_other_separate():
    a = parse_result_url("https://www.example.com.au/")
    b = parse_result_url("https://blog.example.com.au/")
    c = parse_result_url("https://other.com.au/")
    assert a.registrable_domain == b.registrable_domain == "example.com.au"
    assert c.registrable_domain == "other.com.au"
    assert c.registrable_domain != a.registrable_domain


def test_s14_13_task_error_surfaces():
    body = {
        "status_code": 20000,
        "tasks": [{"status_code": 40501, "status_message": "Invalid Field: date_from", "result": []}],
    }
    parsed = parse_historical_response(body, "test")
    # provider.fetch also sets error; parser exposes codes
    assert parsed.task_status_code == 40501
    assert parsed.task_status_message


def test_s14_16_special_keyword_chars_in_payload_ok():
    # estimate / window validation must not choke on unicode keywords at import layer
    from app.services.keywords import prepare_keywords

    prep = prepare_keywords(["café % discount", "c++ tutorial", "ключ"])
    assert prep.unique >= 3
    assert prep.invalid == 0


def test_s15_batch_max_and_201_needs_three():
    assert BATCH_MAX == 100
    credits = 201
    batches = (credits + BATCH_MAX - 1) // BATCH_MAX
    assert batches == 3


def test_s15_available_filter_strict():
    assert "TAKEN" not in AVAILABLE_FILTER
    assert "UNKNOWN" not in AVAILABLE_FILTER
    assert "AVAILABLE_PRELIMINARY" in AVAILABLE_FILTER
    assert "AVAILABLE_CONFIRMED" in AVAILABLE_FILTER


def test_s15_map_errors_not_taken():
    assert map_whoisfreaks_status("AVAILABLE") == "AVAILABLE_PRELIMINARY"
    assert map_whoisfreaks_status("UNAVAILABLE") == "TAKEN"
    assert map_whoisfreaks_status("UNKNOWN") == "UNKNOWN"
    assert map_whoisfreaks_status("UNSUPPORTED") == "UNSUPPORTED_TLD"  # not TAKEN
    assert map_whoisfreaks_status("RESTRICTED") == "RESTRICTED"
    assert map_whoisfreaks_status("INVALID") == "INVALID"
    assert map_whoisfreaks_status(None) == "UNKNOWN"


def test_s14_retry_policy_no_business_40xxx():
    fetch = SerpFetchResult(
        provider="t",
        http_status=200,
        top_status_code=20000,
        task_status_code=40501,
        task_status_message="Invalid Field",
        cost_usd=Decimal("0"),
        snapshots=[],
        error="Invalid Field",
    )
    assert not is_retryable(fetch)
    fetch429 = SerpFetchResult(
        provider="t",
        http_status=429,
        top_status_code=None,
        task_status_code=None,
        task_status_message=None,
        cost_usd=Decimal("0"),
        snapshots=[],
        error="rate",
    )
    assert is_retryable(fetch429)


def test_s15_no_purchase_in_godaddy_stub():
    from app.providers.whoisfreaks import GoDaddyAvailabilityStub

    stub = GoDaddyAvailabilityStub()
    res = stub.check_many(["example.com"])
    assert res.error
    assert res.credits_actual == 0
    assert "purchase" not in (res.error or "").lower()
