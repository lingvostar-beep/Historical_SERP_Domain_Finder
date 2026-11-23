"""Live AU+UK pilot via SSH tunnel. Budget: ~$0.05–0.17 expected.

2 keywords × AU+UK × Sep 2026 → SERP → availability (max 40 domains) → exports.
Writes docs/pilot_au_uk_latest.md (no secrets).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / "deploy" / "vps_bootstrap_credentials.txt"
BASE = "http://127.0.0.1:8872"
OUT = ROOT / "docs" / "pilot_au_uk_latest.md"
REPORT_JSON = ROOT / "docs" / "pilot_au_uk_latest.json"


def load_basic() -> tuple[str, str]:
    user, pw = "admin", ""
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_BASIC_USER="):
            user = line.split("=", 1)[1].strip()
        if line.startswith("APP_BASIC_PASSWORD="):
            pw = line.split("=", 1)[1].strip()
    if not pw:
        raise SystemExit("missing APP_BASIC_PASSWORD")
    return user, pw


def find_country(s: requests.Session, q: str, iso: str) -> dict:
    data = s.get(f"{BASE}/api/locations?q={requests.utils.quote(q)}", timeout=30).json()
    for it in data.get("items") or []:
        if (it.get("country_iso_code") or "").upper() == iso.upper() and (
            it.get("location_type") or ""
        ).lower() in {"country", ""}:
            return it
        if (it.get("location_name") or "").lower() == q.lower():
            return it
    # fallback first hit
    if not data.get("items"):
        raise SystemExit(f"location not found: {q}")
    return data["items"][0]


def main() -> int:
    s = requests.Session()
    s.auth = load_basic()
    s.headers["Content-Type"] = "application/json"

    health = s.get(f"{BASE}/health", timeout=15)
    health.raise_for_status()
    win = s.get(f"{BASE}/api/meta/serp-window", timeout=15).json()
    date_from, date_to = "2026-09-01", "2026-09-30"
    if date_from < win["earliest_allowed_date"]:
        date_from = win["earliest_allowed_date"]

    au = find_country(s, "Australia", "AU")
    uk = find_country(s, "United Kingdom", "GB")
    # language: prefer en
    def lang(loc: dict) -> str:
        langs = loc.get("languages") or []
        for lg in langs:
            if (lg.get("language_code") or "").lower() == "en":
                return "en"
        return (langs[0].get("language_code") if langs else "en") or "en"

    targets = [
        {
            "location_code": au["location_code"],
            "location_name": au["location_name"],
            "language_code": lang(au),
        },
        {
            "location_code": uk["location_code"],
            "location_name": uk["location_name"],
            "language_code": lang(uk),
        },
    ]
    print("targets", targets)

    project = s.post(
        f"{BASE}/api/projects",
        json={"name": f"pilot-AU-UK-{date.today().isoformat()}"},
        timeout=30,
    ).json()
    pid = project["id"]
    kw = s.post(
        f"{BASE}/api/projects/{pid}/keywords/import",
        json={"text": "amazon\ncasino"},
        timeout=30,
    ).json()
    s.put(f"{BASE}/api/projects/{pid}/targets", json={"targets": targets}, timeout=30).raise_for_status()

    est = s.post(
        f"{BASE}/api/projects/{pid}/runs/estimate",
        json={"date_from": date_from, "date_to": date_to},
        timeout=30,
    ).json()
    print("estimate", est)

    run = s.post(
        f"{BASE}/api/projects/{pid}/runs",
        json={
            "date_from": date_from,
            "date_to": date_to,
            "depth": 10,
            "budget_cap": "1.00",
            "dedupe_mode": "registrable_domain",
            "availability_mode": "manual_after_serp",
            "start": True,
        },
        timeout=30,
    ).json()
    rid = run["id"]
    print("run", rid)

    deadline = time.time() + 360
    prog = None
    while time.time() < deadline:
        prog = s.get(f"{BASE}/api/runs/{rid}", timeout=30).json()
        print(
            "serp",
            prog.get("status"),
            prog.get("queries_by_status"),
            "snaps",
            prog.get("snapshots"),
            "spend",
            prog.get("spent_usd"),
        )
        if prog.get("status") in {
            "COMPLETED",
            "COMPLETED_WITH_GAPS",
            "FAILED",
            "CANCELED",
            "BUDGET_EXCEEDED",
        }:
            break
        time.sleep(4)
    else:
        print("FAIL serp timeout")
        return 2

    if prog.get("status") not in {"COMPLETED", "COMPLETED_WITH_GAPS"}:
        print("FAIL serp", prog)
        return 3

    domains = s.get(f"{BASE}/api/runs/{rid}/domains?page_size=100", timeout=30).json()
    coverage = s.get(f"{BASE}/api/runs/{rid}/coverage?page_size=50", timeout=30).json()
    positions = s.get(f"{BASE}/api/runs/{rid}/positions?page_size=5", timeout=30).json()
    print("domains", domains.get("total"), "coverage", coverage.get("total"))

    # coverage by country
    by_loc: dict[int, dict[str, int]] = {}
    for row in coverage.get("items") or []:
        lc = row.get("location_code")
        st = row.get("status") or "?"
        by_loc.setdefault(lc, {})
        by_loc[lc][st] = by_loc[lc].get(st, 0) + 1

    serp_exp = s.post(f"{BASE}/api/runs/{rid}/exports", timeout=60).json()

    aest = s.post(
        f"{BASE}/api/runs/{rid}/availability/estimate",
        json={"force_refresh": False, "max_n": 40},
        timeout=60,
    ).json()
    print("avail_estimate", aest)

    to_check = int(aest.get("to_check") or 0)
    budget_credits = max(to_check, 1)
    if to_check > 40:
        # shouldn't happen with max_n=40 on estimate, but create uses max_n
        pass

    job = s.post(
        f"{BASE}/api/runs/{rid}/availability/jobs",
        json={
            "budget_cap_credits": min(max(budget_credits, 1), 40),
            "force_refresh": False,
            "mode": "max_n",
            "max_n": 40,
            "start": True,
        },
        timeout=30,
    ).json()
    jid = job["job_id"]
    print("avail_job", jid)

    deadline = time.time() + 240
    jprog = None
    while time.time() < deadline:
        jprog = s.get(f"{BASE}/api/availability/jobs/{jid}", timeout=30).json()
        print(
            "avail",
            jprog.get("status"),
            "credits",
            jprog.get("spent_credits"),
            jprog.get("items_by_status"),
        )
        if jprog.get("status") in {
            "COMPLETED",
            "COMPLETED_WITH_GAPS",
            "FAILED",
            "CANCELED",
            "BUDGET_EXCEEDED",
        }:
            break
        time.sleep(3)
    else:
        print("FAIL avail timeout")
        return 4

    avail = s.get(f"{BASE}/api/runs/{rid}/availability?page_size=50", timeout=30).json()
    avail_only = s.get(
        f"{BASE}/api/runs/{rid}/availability?available_only=true&page_size=50",
        timeout=30,
    ).json()
    aexp = s.get(f"{BASE}/api/runs/{rid}/availability/export", timeout=60).json()

    # sample domains per geo from positions
    pos_all = s.get(f"{BASE}/api/runs/{rid}/positions?page_size=200", timeout=60).json()
    domains_by_loc: dict[int, set[str]] = {}
    for p in pos_all.get("items") or []:
        if p.get("domain") and p.get("location_code") is not None:
            domains_by_loc.setdefault(p["location_code"], set()).add(p["domain"])

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": pid,
        "run_id": rid,
        "job_id": jid,
        "window": {"date_from": date_from, "date_to": date_to, "serp_meta": win},
        "keywords": kw,
        "targets": targets,
        "estimate": est,
        "serp_progress": prog,
        "domains_total": domains.get("total"),
        "coverage_by_location": {str(k): v for k, v in by_loc.items()},
        "domains_by_location": {str(k): sorted(v) for k, v in domains_by_loc.items()},
        "positions_total": positions.get("total") if positions else pos_all.get("total"),
        "serp_export": serp_exp,
        "availability_estimate": aest,
        "availability_job": jprog,
        "availability_rows": avail.get("total"),
        "available_only_rows": avail_only.get("total"),
        "availability_export": aexp,
        "actual_cost": {
            "dataforseo_usd": prog.get("spent_usd"),
            "whoisfreaks_credits": jprog.get("spent_credits") if jprog else None,
            "whoisfreaks_usd_ref": jprog.get("spent_usd") if jprog else None,
        },
        "sample_availability": (avail.get("items") or [])[:8],
        "coverage_sample": (coverage.get("items") or [])[:8],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    au_code = targets[0]["location_code"]
    uk_code = targets[1]["location_code"]
    md = f"""# Pilot AU + UK — {date.today().isoformat()}

**Generated (UTC):** `{report["generated_at_utc"]}`  
**Run:** `{rid}` · **Project:** `{pid}` · **Avail job:** `{jid}`

## Scope

| | |
|---|---|
| Keywords | `amazon`, `casino` (2) |
| Geos | **Australia** (`{au_code}`) + **United Kingdom** (`{uk_code}`), language `en` |
| Period | `{date_from}` → `{date_to}` |
| Depth | TOP-10 organic |
| Availability | max 40 unique domains, WhoisFreaks |

## Costs (actual)

| Provider | Spend |
|---|---|
| DataForSEO | **${prog.get("spent_usd")}** (budget cap $1.00) |
| WhoisFreaks | **{jprog.get("spent_credits") if jprog else "?"} credits** / **${jprog.get("spent_usd") if jprog else "?"}** (ref) |
| **Total (ref)** | **~${float(prog.get("spent_usd") or 0) + float((jprog or {}).get("spent_usd") or 0):.6f}** |

Pre-flight estimate SERP: `{est.get("estimated_cost_usd")}` for ≤{est.get("max_planned_snapshots")} snapshots ({est.get("query_combinations")} combos × {est.get("planned_months")} mo).

## SERP result

| Metric | Value |
|---|---|
| Status | `{prog.get("status")}` |
| Queries | `{json.dumps(prog.get("queries_by_status"))}` |
| Snapshots saved | `{prog.get("snapshots")}` |
| Unique domains | `{domains.get("total")}` |
| Positions (total) | `{pos_all.get("total")}` |

### Coverage by location

```json
{json.dumps(report["coverage_by_location"], indent=2)}
```

### Distinct domains seen per geo (from positions)

| Geo code | Domains |
|---|---|
| AU `{au_code}` | {len(domains_by_loc.get(au_code, []))} |
| UK `{uk_code}` | {len(domains_by_loc.get(uk_code, []))} |

## Availability

| Metric | Value |
|---|---|
| Estimate to_check | `{aest.get("to_check")}` (cached `{aest.get("cached_fresh")}`) |
| Job status | `{jprog.get("status") if jprog else "?"}` |
| Rows with status | `{avail.get("total")}` |
| Available-only filter | `{avail_only.get("total")}` |
| Export files | `{", ".join(aexp.get("files") or [])}` |

## Exports

- SERP export `{serp_exp.get("export_id")}`: {", ".join(serp_exp.get("files") or [])}
- Availability export `{aexp.get("export_id")}`: {", ".join(aexp.get("files") or [])}

## Verdict

- Multigeo matrix executed (AU+UK).
- Actual spend within agreed band (~$0.05–0.17) if domains ≤40 and snapshots ≤4.
- Machine-readable copy: `docs/pilot_au_uk_latest.json`
"""
    OUT.write_text(md, encoding="utf-8")
    print("WROTE", OUT)
    print("PILOT_OK", json.dumps(report["actual_cost"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
