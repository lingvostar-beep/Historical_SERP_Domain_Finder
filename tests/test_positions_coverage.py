"""TZ §9.2 Positions filters + §9.3 Coverage matrix contracts."""

from __future__ import annotations

import inspect

from app.api import routes_results
from app.api.schemas import RunExportRequest
from app.services import results as results_svc
from app.services.exports import _clean_filters


def test_list_positions_accepts_tld_source_rank_and_geo_filters():
    params = inspect.signature(results_svc.list_positions).parameters
    for name in (
        "keyword",
        "location_code",
        "language_code",
        "month",
        "domain",
        "tld",
        "source",
        "rank_max",
    ):
        assert name in params


def test_positions_route_exposes_same_filters():
    params = inspect.signature(routes_results.get_positions).parameters
    for name in (
        "keyword",
        "location_code",
        "language",
        "month",
        "domain",
        "tld",
        "source",
        "rank_max",
    ):
        assert name in params


def test_coverage_matrix_route_and_service_exist():
    assert hasattr(routes_results, "get_coverage_matrix")
    params = inspect.signature(results_svc.coverage_matrix).parameters
    for name in ("keyword", "location_code", "status", "keyword_page", "keyword_page_size"):
        assert name in params


def test_export_schema_carries_position_and_coverage_filters():
    fields = RunExportRequest.model_fields
    for name in (
        "pos_tld",
        "pos_source",
        "location_code",
        "language",
        "month",
        "rank_max",
        "coverage_status",
        "coverage_keyword",
    ):
        assert name in fields


def test_clean_filters_keeps_pos_tld_and_coverage_keyword():
    got = _clean_filters(
        {
            "pos_tld": "com.au",
            "pos_source": "dataforseo_google_current",
            "coverage_keyword": "loan",
            "coverage_status": "AVAILABLE",
            "rank_max": 10,
        },
        export_all=False,
    )
    assert got["pos_tld"] == "com.au"
    assert got["pos_source"] == "dataforseo_google_current"
    assert got["coverage_keyword"] == "loan"
    assert got["coverage_status"] == "AVAILABLE"
    assert got["rank_max"] == 10
