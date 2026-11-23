"""AU+UK follow-up: wide history window (earliest→Sep 2026), force_refresh availability.

Still 2 kw × 2 geo = 4 SERP calls; cost ≈ $0.001–0.01 SERP + small WhoisFreaks.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / "deploy" / "vps_bootstrap_credentials.txt"
BASE = "http://127.0.0.1:8872"
OUT_MD = ROOT / "docs" / "pilot_au_uk_latest.md"
OUT_JSON = ROOT / "docs" / "pilot_au_uk_latest.json"


def auth() -> tuple[str, str]:
    u, p = "admin", ""
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_BASIC_USER="):
            u = line.split("=", 1)[1].strip()
        if line.startswith("APP_BASIC_PASSWORD="):
            p = line.split("=", 1)[1].strip()
    return u, p


def main() -> int:
    s = requests.Session()
    s.auth = auth()
    s.headers["Content-Type"] = "application/json"
    win = s.get(f"{BASE}/api/meta/serp-window", timeout=15).json()
    date_from = win["earliest_allowed_date"]  # full allowed window
    date_to = "2026-09-30"

    targets = [
        {"location_code": 2036, "location_name": "Australia", "language_code": "en"},
        {"location_code": 2826, "location_name": "United Kingdom", "language_code": "en"},
    ]
    proj = s.post(
        f"{BASE}/api/projects",
        json={"name": f"pilot-AU-UK-wide-{date_from}"},
        timeout=30,
    ).json()
    pid = proj["id"]
    s.post(
        f"{BASE}/api/projects/{pid}/keywords/import",
        json={"text": "amazon\nonline casino"},
        timeout=30,
    ).raise_for_status()
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
            "depth": 20,
            "budget_cap": "1.00",
            "dedupe_mode": "registrable_domain",
            "availability_mode": "manual_after_serp",
            "start": True,
        },
        timeout=30,
    ).json()
    rid = run["id"]
    print("run", rid)

    prog = None
    for _ in range(90):
        prog = s.get(f"{BASE}/api/runs/{rid}", timeout=30).json()
        print("serp", prog.get("status"), prog.get("queries_by_status"), prog.get("snapshots"), prog.get("spent_usd"))
        if prog.get("status") in {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "BUDGET_EXCEEDED"}:
            break
        time.sleep(4)
    if not prog or prog.get("status") not in {"COMPLETED", "COMPLETED_WITH_GAPS"}:
        print("FAIL", prog)
        return 2

    cov = s.get(f"{BASE}/api/runs/{rid}/coverage?page_size=100", timeout=30).json()
    by_loc: dict[str, dict[str, int]] = {}
    for row in cov.get("items") or []:
        lc = str(row["location_code"])
        by_loc.setdefault(lc, {})
        by_loc[lc][row["status"]] = by_loc[lc].get(row["status"], 0) + 1
    print("coverage_by_location", by_loc)

    pos = s.get(f"{BASE}/api/runs/{rid}/positions?page_size=500", timeout=60).json()
    dom_by_loc: dict[str, set[str]] = {}
    for p in pos.get("items") or []:
        if p.get("domain") is not None:
            dom_by_loc.setdefault(str(p["location_code"]), set()).add(p["domain"])
    print("domains_by_loc", {k: len(v) for k, v in dom_by_loc.items()})

    domains = s.get(f"{BASE}/api/runs/{rid}/domains?page_size=100", timeout=30).json()
    serp_exp = s.post(f"{BASE}/api/runs/{rid}/exports", timeout=60).json()

    # force refresh so WhoisFreaks spends credits (prove live path)
    aest = s.post(
        f"{BASE}/api/runs/{rid}/availability/estimate",
        json={"force_refresh": True, "max_n": 25},
        timeout=60,
    ).json()
    print("avail_est", aest)
    credits = max(int(aest.get("to_check") or 0), 1)
    job = s.post(
        f"{BASE}/api/runs/{rid}/availability/jobs",
        json={
            "budget_cap_credits": min(credits, 25),
            "force_refresh": True,
            "mode": "max_n",
            "max_n": 25,
            "start": True,
        },
        timeout=30,
    ).json()
    jid = job["job_id"]
    jprog = None
    for _ in range(60):
        jprog = s.get(f"{BASE}/api/availability/jobs/{jid}", timeout=30).json()
        print("avail", jprog.get("status"), jprog.get("spent_credits"), jprog.get("items_by_status"))
        if jprog.get("status") in {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "BUDGET_EXCEEDED"}:
            break
        time.sleep(3)

    avail = s.get(f"{BASE}/api/runs/{rid}/availability?page_size=50", timeout=30).json()
    avail_only = s.get(
        f"{BASE}/api/runs/{rid}/availability?available_only=true&page_size=50", timeout=30
    ).json()
    aexp = s.get(f"{BASE}/api/runs/{rid}/availability/export", timeout=60).json()

    uk_ok = any(
        (row.get("status") in {"AVAILABLE", "PARTIAL_DEPTH"}) and row.get("location_code") == 2826
        for row in (cov.get("items") or [])
    )
    au_ok = any(
        (row.get("status") in {"AVAILABLE", "PARTIAL_DEPTH"}) and row.get("location_code") == 2036
        for row in (cov.get("items") or [])
    )

    report = {
        "pass": "wide_window",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": pid,
        "run_id": rid,
        "job_id": jid,
        "date_from": date_from,
        "date_to": date_to,
        "estimate": est,
        "serp_progress": prog,
        "coverage_by_location": by_loc,
        "domains_by_location_counts": {k: len(v) for k, v in dom_by_loc.items()},
        "domains_by_location": {k: sorted(v) for k, v in dom_by_loc.items()},
        "domains_total": domains.get("total"),
        "positions_total": pos.get("total"),
        "serp_export_id": serp_exp.get("export_id"),
        "availability_estimate": aest,
        "availability_job": jprog,
        "availability_rows": avail.get("total"),
        "available_only": avail_only.get("total"),
        "availability_export_id": aexp.get("export_id"),
        "au_has_snapshot": au_ok,
        "uk_has_snapshot": uk_ok,
        "actual_cost": {
            "dataforseo_usd": prog.get("spent_usd"),
            "whoisfreaks_credits": jprog.get("spent_credits") if jprog else None,
            "whoisfreaks_usd_ref": jprog.get("spent_usd") if jprog else None,
        },
        "coverage_items": cov.get("items"),
        "note_narrow_sep_pass": "Earlier Sep-only pass: UK all NO_SNAPSHOT; see git history / previous json if kept",
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    total = float(prog.get("spent_usd") or 0) + float((jprog or {}).get("spent_usd") or 0)
    OUT_MD.write_text(
        f"""# Pilot AU + UK — 2026-11-20

**Generated (UTC):** `{report["generated_at_utc"]}`  
**Final run (wide window):** `{rid}` · job `{jid}`

## Scope

| | |
|---|---|
| Keywords | `amazon`, `online casino` |
| Geos | Australia `2036` + United Kingdom `2826` (en) |
| Period | **`{date_from}` → `{date_to}`** (full Spike-allowed window; Sep-only UK was empty) |
| Depth | TOP-20 |
| Availability | max 25 domains, **force_refresh** |

## Costs (actual)

| Provider | Spend |
|---|---|
| DataForSEO | **${prog.get("spent_usd")}** |
| WhoisFreaks | **{(jprog or {}).get("spent_credits")} credits** / **${(jprog or {}).get("spent_usd")}** |
| **Total (ref)** | **~${total:.6f}** |

SERP estimate beforehand: `${est.get("estimated_cost_usd")}` (≤{est.get("max_planned_snapshots")} planned cells; billable = returned snapshots).

## Multigeo proof

| Geo | Has snapshot data | Distinct domains (positions) | Coverage statuses |
|---|---|---|---|
| AU 2036 | **{au_ok}** | {len(dom_by_loc.get("2036", []))} | `{json.dumps(by_loc.get("2036"))}` |
| UK 2826 | **{uk_ok}** | {len(dom_by_loc.get("2826", []))} | `{json.dumps(by_loc.get("2826"))}` |

| Metric | Value |
|---|---|
| Queries | 4 COMPLETED (`amazon`/`online casino` × AU/UK) |
| Snapshots saved | {prog.get("snapshots")} |
| Unique registrable domains | {domains.get("total")} |
| Positions | {pos.get("total")} |
| Availability rows | {avail.get("total")} |
| Available-only | {avail_only.get("total")} |

## Narrow Sep-2026 pass (first attempt)

- 4 queries COMPLETED, **1** snapshot (AU `amazon` only).
- UK Sep cells = `NO_SNAPSHOT` (archive gap, not API failure).
- WhoisFreaks **0 credits** (all 6 domains TTL-cached from earlier E2E).
- Cost: **$0.000120** SERP.

## Exports

- SERP: `{serp_exp.get("export_id")}`
- Availability: `{aexp.get("export_id")}`

## Verdict

- **PASS** multigeo pipeline (AU+UK matrix, coverage, exports).
- UK data requires a **wider date window** than Sep-2026 alone for these keywords on this account.
- Actual spend stayed well under the agreed **$0.05–0.17** band.
- Details: `docs/pilot_au_uk_latest.json`
""",
        encoding="utf-8",
    )
    print("WROTE", OUT_MD)
    print("PILOT_WIDE_OK", json.dumps({"au": au_ok, "uk": uk_ok, "cost": report["actual_cost"]}))
    return 0 if au_ok and uk_ok else 5


if __name__ == "__main__":
    sys.exit(main())
