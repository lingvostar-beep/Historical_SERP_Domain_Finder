"""Keyword import / normalization — TZ §4.2."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass

MAX_KEYWORD_CHARS = 700
_SPACE_RE = re.compile(r"\s+")


@dataclass
class KeywordImportResult:
    loaded: int
    unique: int
    duplicates_removed: int
    invalid: int
    keywords: list[tuple[str, str]]  # (original, normalized)
    invalid_samples: list[str]


def normalize_keyword(text: str) -> str:
    s = text.strip()
    s = s.lstrip("\ufeff")  # BOM
    s = _SPACE_RE.sub(" ", s)
    return s


def keyword_hash(normalized: str) -> str:
    # case-insensitive dedupe key; store original of first occurrence
    return hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()


def prepare_keywords(lines: list[str]) -> KeywordImportResult:
    loaded = 0
    invalid = 0
    invalid_samples: list[str] = []
    seen: dict[str, tuple[str, str]] = {}  # hash -> (original, normalized)
    duplicates = 0

    for raw in lines:
        loaded += 1
        original = raw.strip().lstrip("\ufeff")
        if not original:
            invalid += 1
            continue
        normalized = normalize_keyword(original)
        if not normalized:
            invalid += 1
            continue
        if len(normalized) > MAX_KEYWORD_CHARS:
            invalid += 1
            if len(invalid_samples) < 10:
                invalid_samples.append(normalized[:80] + "…(too long)")
            continue
        h = keyword_hash(normalized)
        if h in seen:
            duplicates += 1
            continue
        seen[h] = (original if original else normalized, normalized)

    keywords = list(seen.values())
    return KeywordImportResult(
        loaded=loaded,
        unique=len(keywords),
        duplicates_removed=duplicates,
        invalid=invalid,
        keywords=keywords,
        invalid_samples=invalid_samples,
    )


def lines_from_text(body: str) -> list[str]:
    return body.splitlines()


def lines_from_csv_bytes(data: bytes) -> list[str]:
    text = data.decode("utf-8-sig")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        return []
    header = [c.strip().casefold() for c in rows[0]]
    start = 0
    col = 0
    if "keyword" in header:
        col = header.index("keyword")
        start = 1
    out: list[str] = []
    for row in rows[start:]:
        if not row:
            continue
        if col >= len(row):
            continue
        out.append(row[col])
    return out
