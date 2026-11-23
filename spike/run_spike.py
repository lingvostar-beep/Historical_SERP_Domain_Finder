"""
Этап 0 — API feasibility spike (TZ §2 / §15.11 / §16).

Runs DataForSEO Legacy + Current, WhoisFreaks availability, optional GoDaddy.
Writes JSON + Markdown protocol under spike/results/ (gitignored).

Usage (from repo root, venv active):
  python spike/run_spike.py
  python spike/run_spike.py --skip-godaddy
  python spike/run_spike.py --keyword "online casino"
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RESULTS = Path(__file__).resolve().parent / "results"
LEGACY_URL = "https://api.dataforseo.com/v3/dataforseo_labs/historical_serps/live"
CURRENT_URL = "https://api.dataforseo.com/v3/dataforseo_labs/google/historical_serps/live"
WHOISFREAKS_URL = "https://api.whoisfreaks.com/v2.0/domain/availability"
GODADDY_DEFAULT_BASE = "https://api.godaddy.com"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def _require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing {name} in .env — copy .env.example and fill credentials.")
    return value


def _redact_url(url: str) -> str:
    """Strip apiKey / secrets from URLs before logging or saving."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = []
    for pair in parts.query.split("&"):
        key = pair.split("=", 1)[0].lower()
        if key in {"apikey", "api_key", "password", "token", "access_token"}:
            kept.append(f"{pair.split('=', 1)[0]}=***")
        else:
            kept.append(pair)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment))


def _dfs_auth_header(login: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start.isoformat(), end.isoformat()


def _recent_month_within_365() -> tuple[str, str]:
    """Pick a full calendar month that ends within the last ~365 days."""
    today = date.today()
    y, m = today.year, today.month - 1
    if m < 1:
        y, m = y - 1, 12
    return _month_bounds(y, m)


def _count_organic(snapshot: dict[str, Any]) -> int:
    items = snapshot.get("items") or []
    n = 0
    for it in items:
        if isinstance(it, dict) and it.get("type") == "organic":
            n += 1
    return n


def _summarize_dfs_body(body: Any) -> dict[str, Any]:
    """Extract protocol fields without dumping huge SERP payloads into the summary."""
    if not isinstance(body, dict):
        return {"parse_error": "body is not an object", "raw_type": type(body).__name__}

    tasks = body.get("tasks") or []
    task_summaries = []
    all_datetimes: list[str] = []
    total_organic = 0
    total_snapshots = 0

    for task in tasks:
        if not isinstance(task, dict):
            continue
        results = task.get("result") or []
        snap_info = []
        for res in results:
            if not isinstance(res, dict):
                continue
            # Historical: result[].items[] = snapshots; each snapshot has items[] = SERP rows
            for snap in res.get("items") or []:
                if not isinstance(snap, dict):
                    continue
                total_snapshots += 1
                dt = snap.get("datetime")
                if dt:
                    all_datetimes.append(str(dt))
                org = _count_organic(snap)
                total_organic += org
                snap_info.append(
                    {
                        "datetime": dt,
                        "organic_count": org,
                        "se_results_count": snap.get("se_results_count"),
                        "items_count": snap.get("items_count"),
                    }
                )
        task_summaries.append(
            {
                "id": task.get("id"),
                "status_code": task.get("status_code"),
                "status_message": task.get("status_message"),
                "cost": task.get("cost"),
                "result_count": task.get("result_count"),
                "snapshots": snap_info,
            }
        )

    return {
        "top_status_code": body.get("status_code"),
        "top_status_message": body.get("status_message"),
        "top_cost": body.get("cost"),
        "tasks_count": len(tasks),
        "tasks": task_summaries,
        "snapshot_datetimes": all_datetimes,
        "snapshot_count": total_snapshots,
        "organic_total_across_snapshots": total_organic,
    }


def call_dataforseo(
    *,
    endpoint: str,
    label: str,
    login: str,
    password: str,
    keyword: str,
    location_name: str,
    language_code: str,
    date_from: str,
    date_to: str,
    tag: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    payload = [
        {
            "keyword": keyword,
            "location_name": location_name,
            "language_code": language_code,
            "date_from": date_from,
            "date_to": date_to,
            "tag": tag,
        }
    ]
    started = time.perf_counter()
    record: dict[str, Any] = {
        "provider": "dataforseo",
        "label": label,
        "endpoint": endpoint,
        "request": {
            "keyword": keyword,
            "location_name": location_name,
            "language_code": language_code,
            "date_from": date_from,
            "date_to": date_to,
            "tag": tag,
        },
        "http_status": None,
        "latency_ms": None,
        "error": None,
        "summary": None,
        "raw_saved_as": None,
    }
    try:
        resp = requests.post(
            endpoint,
            headers=_dfs_auth_header(login, password),
            data=json.dumps(payload),
            timeout=timeout,
        )
        record["http_status"] = resp.status_code
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        try:
            body = resp.json()
        except Exception:
            record["error"] = f"non-JSON body: {resp.text[:500]}"
            return record
        record["summary"] = _summarize_dfs_body(body)
        # Keep full raw for audit (local only)
        raw_name = f"raw_dfs_{tag}_{_utc_stamp()}.json"
        raw_path = RESULTS / raw_name
        raw_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        record["raw_saved_as"] = raw_name
    except requests.RequestException as exc:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        record["error"] = str(exc)
    return record


def call_whoisfreaks(api_key: str, domains: list[str], timeout: float = 60.0) -> dict[str, Any]:
    url = f"{WHOISFREAKS_URL}?apiKey={api_key}"
    started = time.perf_counter()
    record: dict[str, Any] = {
        "provider": "whoisfreaks",
        "endpoint_redacted": _redact_url(url),
        "domains": domains,
        "http_status": None,
        "latency_ms": None,
        "error": None,
        "summary": None,
        "raw_saved_as": None,
    }
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"domainNames": domains},
            timeout=timeout,
        )
        record["http_status"] = resp.status_code
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        try:
            body = resp.json()
        except Exception:
            record["error"] = f"non-JSON body: {resp.text[:500]}"
            return record
        # Prefer documented array name; fall back to whole body keys
        items = body.get("bulk_domain_availability_response")
        if items is None and isinstance(body, list):
            items = body
        compact = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                compact.append(
                    {
                        "domain": it.get("domain") or it.get("domainName") or it.get("domain_name"),
                        "availability": it.get("availability") or it.get("domain_availability"),
                        "keys": sorted(it.keys()),
                    }
                )
        record["summary"] = {
            "top_keys": sorted(body.keys()) if isinstance(body, dict) else None,
            "results": compact,
            "note": "Exact status enums to be frozen from this live response.",
        }
        raw_name = f"raw_whoisfreaks_{_utc_stamp()}.json"
        # Scrub any accidental key echoes in saved raw if API mirrors request URL (unlikely in JSON body)
        raw_path = RESULTS / raw_name
        raw_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        record["raw_saved_as"] = raw_name
    except requests.RequestException as exc:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        record["error"] = str(exc)
    return record


def call_godaddy(pat: str, domains: list[str], base: str, timeout: float = 60.0) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/v3/domains/check-availability"
    started = time.perf_counter()
    record: dict[str, Any] = {
        "provider": "godaddy",
        "endpoint": url,
        "domains": domains,
        "http_status": None,
        "latency_ms": None,
        "error": None,
        "summary": None,
        "raw_saved_as": None,
    }
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {pat}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"domains": domains, "optimizeFor": "ACCURACY"},
            timeout=timeout,
        )
        record["http_status"] = resp.status_code
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        try:
            body = resp.json()
        except Exception:
            record["error"] = f"non-JSON body: {resp.text[:500]}"
            return record
        items = body.get("items") if isinstance(body, dict) else None
        compact = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    compact.append(
                        {
                            "domain": it.get("domain"),
                            "available": it.get("available"),
                            "keys": sorted(it.keys()),
                        }
                    )
        record["summary"] = {"top_keys": sorted(body.keys()) if isinstance(body, dict) else None, "items": compact}
        raw_name = f"raw_godaddy_{_utc_stamp()}.json"
        (RESULTS / raw_name).write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        record["raw_saved_as"] = raw_name
    except requests.RequestException as exc:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        record["error"] = str(exc)
    return record


def build_markdown(protocol: dict[str, Any]) -> str:
    lines = [
        "# Spike protocol — Historical SERP Domain Finder",
        "",
        f"- Generated (UTC): `{protocol['generated_at_utc']}`",
        f"- Keyword: `{protocol['keyword']}`",
        "",
        "## DataForSEO calls",
        "",
        "| Label | HTTP | Top status | Task status(es) | Snapshots | Organic (sum) | Cost | Error |",
        "|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for c in protocol["dataforseo"]:
        summary = c.get("summary") or {}
        tasks = summary.get("tasks") or []
        task_statuses = ", ".join(str(t.get("status_code")) for t in tasks) or "—"
        costs = summary.get("top_cost")
        if costs is None and tasks:
            costs = sum((t.get("cost") or 0) for t in tasks)
        lines.append(
            "| {label} | {http} | {top} | {tasks} | {snaps} | {org} | {cost} | {err} |".format(
                label=c.get("label"),
                http=c.get("http_status"),
                top=summary.get("top_status_code"),
                tasks=task_statuses,
                snaps=summary.get("snapshot_count"),
                org=summary.get("organic_total_across_snapshots"),
                cost=costs,
                err=(c.get("error") or "—")[:80],
            )
        )
    lines.extend(
        [
            "",
            "### Datetimes observed",
            "",
        ]
    )
    for c in protocol["dataforseo"]:
        summary = c.get("summary") or {}
        dts = summary.get("snapshot_datetimes") or []
        lines.append(f"- **{c.get('label')}**: {', '.join(dts) if dts else '(none)'}")

    lines.extend(["", "## WhoisFreaks", ""])
    wf = protocol.get("whoisfreaks")
    if not wf:
        lines.append("_skipped_")
    else:
        lines.append(f"- HTTP: `{wf.get('http_status')}` latency_ms=`{wf.get('latency_ms')}`")
        lines.append(f"- Endpoint (redacted): `{wf.get('endpoint_redacted')}`")
        if wf.get("error"):
            lines.append(f"- Error: `{wf['error']}`")
        for row in ((wf.get("summary") or {}).get("results") or []):
            lines.append(f"- `{row.get('domain')}` → availability=`{row.get('availability')}`")

    lines.extend(["", "## GoDaddy", ""])
    gd = protocol.get("godaddy")
    if not gd:
        lines.append("_not configured / skipped_")
    elif gd.get("skipped"):
        lines.append(f"_skipped: {gd.get('reason')}_")
    else:
        lines.append(f"- HTTP: `{gd.get('http_status')}` latency_ms=`{gd.get('latency_ms')}`")
        if gd.get("error"):
            lines.append(f"- Error: `{gd['error']}`")
        for row in ((gd.get("summary") or {}).get("items") or []):
            lines.append(f"- `{row.get('domain')}` → available=`{row.get('available')}`")

    lines.extend(
        [
            "",
            "## Go / No-go (fill after review)",
            "",
            "- [ ] Legacy returns usable snapshots for 2022–2024 (AU and/or UK)",
            "- [ ] Current works inside last 365 days",
            "- [ ] Organic depth enough for product TOP-N defaults",
            "- [ ] WhoisFreaks statuses understood; credits match expectation",
            "- [ ] GoDaddy confirm path usable **or** explicitly deferred",
            "- [ ] **Decision:** primary SERP source = `_______________`",
            "- [ ] **Decision:** UI date range = `_______________`",
            "",
            "## Notes",
            "",
            protocol.get("notes") or "_add operator notes here_",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Этап 0 API Spike")
    parser.add_argument("--keyword", default="online casino")
    parser.add_argument("--skip-godaddy", action="store_true")
    parser.add_argument("--skip-whoisfreaks", action="store_true")
    args = parser.parse_args()

    _load_env()
    RESULTS.mkdir(parents=True, exist_ok=True)

    login = _require("DATAFORSEO_LOGIN")
    password = _require("DATAFORSEO_PASSWORD")
    keyword = args.keyword

    # TZ intervals + one recent month
    windows = [
        ("2022-05", *_month_bounds(2022, 5)),
        ("2023-05", *_month_bounds(2023, 5)),
        ("2024-05", *_month_bounds(2024, 5)),
    ]
    recent_label = "recent_le365"
    windows.append((recent_label, *_recent_month_within_365()))

    dfs_calls: list[dict[str, Any]] = []

    print("=== DataForSEO Legacy (AU) ===")
    for label, d_from, d_to in windows:
        tag = f"spike-legacy-au-{label}"
        print(f"  {tag} {d_from}..{d_to}")
        dfs_calls.append(
            call_dataforseo(
                endpoint=LEGACY_URL,
                label=f"legacy|AU|{label}",
                login=login,
                password=password,
                keyword=keyword,
                location_name="Australia",
                language_code="en",
                date_from=d_from,
                date_to=d_to,
                tag=tag,
            )
        )

    print("=== DataForSEO Current/Google (AU, recent month) ===")
    _, r_from, r_to = windows[-1]
    dfs_calls.append(
        call_dataforseo(
            endpoint=CURRENT_URL,
            label=f"current|AU|{recent_label}",
            login=login,
            password=password,
            keyword=keyword,
            location_name="Australia",
            language_code="en",
            date_from=r_from,
            date_to=r_to,
            tag=f"spike-current-au-{recent_label}",
        )
    )

    print("=== DataForSEO Legacy (UK, 2023-05) ===")
    uk_from, uk_to = _month_bounds(2023, 5)
    dfs_calls.append(
        call_dataforseo(
            endpoint=LEGACY_URL,
            label="legacy|UK|2023-05",
            login=login,
            password=password,
            keyword=keyword,
            location_name="United Kingdom",
            language_code="en",
            date_from=uk_from,
            date_to=uk_to,
            tag="spike-legacy-uk-2023-05",
        )
    )

    # Also probe Current on an old month (expect fail / empty) — documents limit
    print("=== DataForSEO Current (AU, 2022-05) — expect limited/empty ===")
    o_from, o_to = _month_bounds(2022, 5)
    dfs_calls.append(
        call_dataforseo(
            endpoint=CURRENT_URL,
            label="current|AU|2022-05(expect_gap)",
            login=login,
            password=password,
            keyword=keyword,
            location_name="Australia",
            language_code="en",
            date_from=o_from,
            date_to=o_to,
            tag="spike-current-au-2022-05",
        )
    )

    whoisfreaks_rec = None
    if not args.skip_whoisfreaks:
        print("=== WhoisFreaks ===")
        wf_key = _require("WHOISFREAKS_API_KEY")
        # Mix: almost certainly taken, multi-part PSL, nonsense TLD, plus a random-looking name
        domains = [
            "example.com",
            "google.com",
            "example.com.au",
            f"hsdf-spike-{int(time.time())}.com",
            "this-tld-should-fail.invalidtld",
        ]
        whoisfreaks_rec = call_whoisfreaks(wf_key, domains)
    else:
        print("=== WhoisFreaks skipped ===")

    godaddy_rec: dict[str, Any] | None
    pat = (os.getenv("GODADDY_PAT") or "").strip()
    if args.skip_godaddy or not pat:
        godaddy_rec = {"skipped": True, "reason": "GODADDY_PAT empty or --skip-godaddy"}
        print("=== GoDaddy skipped ===")
    else:
        print("=== GoDaddy ===")
        base = (os.getenv("GODADDY_API_BASE") or GODADDY_DEFAULT_BASE).strip()
        godaddy_rec = call_godaddy(pat, ["example.com", "google.com"], base)

    protocol = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "keyword": keyword,
        "dataforseo": dfs_calls,
        "whoisfreaks": whoisfreaks_rec,
        "godaddy": godaddy_rec,
        "notes": "",
    }

    stamp = _utc_stamp()
    json_path = RESULTS / f"spike_protocol_{stamp}.json"
    md_path = RESULTS / f"spike_protocol_{stamp}.md"
    json_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(protocol), encoding="utf-8")

    # Stable “latest” copies for easy open
    (RESULTS / "spike_protocol_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (RESULTS / "spike_protocol_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    print()
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print("Also: spike/results/spike_protocol_latest.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
