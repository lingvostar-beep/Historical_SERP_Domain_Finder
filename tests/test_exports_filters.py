"""TZ §10 — filtered exports + streamed CSV (no full materialization helper)."""

from __future__ import annotations

from pathlib import Path

from app.services.csv_safe import write_csv_file
from app.services.exports import _clean_filters


def test_clean_filters_export_all_clears():
    assert _clean_filters({"q": "x", "tld": "com"}, export_all=True) == {}


def test_clean_filters_keeps_values():
    got = _clean_filters(
        {"q": "  foo ", "tld": "", "last_seen_before": "2026-09-01", "rank_max": 10},
        export_all=False,
    )
    assert got == {"q": "foo", "last_seen_before": "2026-09-01", "rank_max": 10}


def test_write_csv_file_streams_and_bom(tmp_path: Path):
    path = tmp_path / "out.csv"

    def rows():
        for i in range(3):
            yield [f"d{i}.com", i]

    n = write_csv_file(path, ["domain", "n"], rows())
    assert n == 3
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = path.read_text(encoding="utf-8-sig")
    assert "d0.com" in text and "d2.com" in text
