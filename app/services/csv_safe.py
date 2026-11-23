"""CSV helpers — UTF-8 BOM + formula-injection guard (TZ §10)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Iterable


def csv_guard(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in {"=", "+", "-", "@"}:
        return "'" + s
    return s


def write_csv_rows(headers: list[str], rows: Iterable[Iterable[Any]]) -> bytes:
    """In-memory helper (tests / small payloads). Prefer write_csv_file for exports."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(headers)
    for row in rows:
        w.writerow([csv_guard(c) for c in row])
    return buf.getvalue().encode("utf-8-sig")


def write_csv_file(path: Path, headers: list[str], rows: Iterable[Iterable[Any]]) -> int:
    """Stream CSV to disk (utf-8-sig). Does not materialize all rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(headers)
        for row in rows:
            w.writerow([csv_guard(c) for c in row])
            count += 1
    return count
