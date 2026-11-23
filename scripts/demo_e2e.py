"""Demo E2E: SERP → unique domains → availability → Available filter → export.

Writes docs/demo_e2e_latest.md + .json. Uses Basic auth from credentials file.
Low spend: 1 kw × AU × Sep 2026 + up to 10 WF credits.
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
OUT_MD = ROOT / "docs" / "demo_e2e_latest.md"
OUT_JSON = ROOT / "docs" / "demo_e2e_latest.json"


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
    steps: list[dict] = []

    def ok(step: str, detail: dict) -> None:
        steps.append({"step": step, "status": "PASS", "detail": detail})
        print("PASS", step, json.dumps(detail, default=str)[:200])

    def fail(step: str, detail: dict) -> int:
        steps.append({"step": step, "status": "FAIL", "detail": detail})
        print("FAIL", step, detail)
        _write(steps, None)
        return 2

    # 0 health
    h = s.get(f"{BASE}/health", timeout=15)
    h.raise_for_status()
    ok("health", h.json())

    # 1 project + keywords + target
    p = s.post(f"{BASE}/api/projects", json={"name": f"demo-e2e-{datetime.now(timezone.utc).strftime('%H%M%S')}"}, timeout=30).json()
    pid = p["id"]
    kw = s.post(f"{BASE}/api/projects/{pid}/keywords/import", json={"text": "amazon"}, timeout=30).json()
    s.put(
        f"{BASE}/api/projects/{pid}/targets",
        json={"targets": [{"location_code": 2036, "location_name": "Australia", "language_code": "en"}]},
        timeout=30,
    ).raise_for_status()
    ok("project_setup", {"project_id": pid, "keywords": kw})

    # 2 SERP run
    run = s.post(
        f"{BASE}/api/projects/{pid}/runs",
        json={
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
            "depth": 10,
            "budget_cap": "1.00",
            "dedupe_mode": "registrable_domain",
            "availability_mode": "manual_after_serp",
            "start": True,
        },
        timeout=30,
    ).json()
    rid = run["id"]
    prog = None
    for _ in range(60):
        prog = s.get(f"{BASE}/api/runs/{rid}", timeout=30).json()
        if prog.get("status") in {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "BUDGET_EXCEEDED"}:
            break
        time.sleep(3)
    if not prog or prog.get("status") not in {"COMPLETED", "COMPLETED_WITH_GAPS"} or not prog.get("snapshots"):
        return fail("serp_run", {"progress": prog})
    ok("serp_run", {"run_id": rid, "status": prog["status"], "snapshots": prog["snapshots"], "spent_usd": prog["spent_usd"]})

    # 3 unique domains
    domains = s.get(f"{BASE}/api/runs/{rid}/domains?page_size=50", timeout=30).json()
    if not domains.get("total"):
        return fail("unique_domains", domains)
    ok(
        "unique_domains",
        {
            "total": domains["total"],
            "sample": [d["domain"] for d in (domains.get("items") or [])[:5]],
        },
    )

    # 4 batch availability
    est = s.post(
        f"{BASE}/api/runs/{rid}/availability/estimate",
        json={"force_refresh": True, "max_n": 10},
        timeout=60,
    ).json()
    credits = max(int(est.get("to_check") or 0), 1)
    job = s.post(
        f"{BASE}/api/runs/{rid}/availability/jobs",
        json={
            "budget_cap_credits": min(credits, 10),
            "force_refresh": True,
            "mode": "max_n",
            "max_n": 10,
            "start": True,
        },
        timeout=30,
    ).json()
    jid = job["job_id"]
    jprog = None
    for _ in range(60):
        jprog = s.get(f"{BASE}/api/availability/jobs/{jid}", timeout=30).json()
        if jprog.get("status") in {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "BUDGET_EXCEEDED"}:
            break
        time.sleep(2)
    if not jprog or jprog.get("status") not in {"COMPLETED", "COMPLETED_WITH_GAPS", "BUDGET_EXCEEDED"}:
        return fail("availability_batch", {"job": jprog})
    # BUDGET_EXCEEDED with all items done still OK for demo
    ok(
        "availability_batch",
        {
            "job_id": jid,
            "status": jprog["status"],
            "spent_credits": jprog.get("spent_credits"),
            "spent_usd": jprog.get("spent_usd"),
            "items_by_status": jprog.get("items_by_status"),
        },
    )

    # 5 Available filter
    all_av = s.get(f"{BASE}/api/runs/{rid}/availability?page_size=50", timeout=30).json()
    avail_only = s.get(
        f"{BASE}/api/runs/{rid}/availability?available_only=true&page_size=50",
        timeout=30,
    ).json()
    allowed = set(avail_only.get("available_statuses") or ["AVAILABLE_PRELIMINARY", "AVAILABLE_CONFIRMED"])
    for row in avail_only.get("items") or []:
        if row.get("registration_status") not in allowed:
            return fail("available_filter", {"bad_row": row, "allowed": sorted(allowed)})
    ok(
        "available_filter",
        {
            "all_rows": all_av.get("total"),
            "available_only_rows": avail_only.get("total"),
            "available_statuses": sorted(allowed),
            "warning": avail_only.get("warning"),
            "sample_available": [r.get("domain") for r in (avail_only.get("items") or [])[:5]],
        },
    )

    # 6 exports SERP + availability
    serp_exp = s.post(f"{BASE}/api/runs/{rid}/exports", timeout=60).json()
    need_serp = {"unique_domains.txt", "domains_summary.csv", "positions_detailed.csv", "coverage.csv", "run_metadata.json"}
    got_serp = set(serp_exp.get("files") or [])
    if not need_serp.issubset(got_serp):
        return fail("serp_export", {"got": sorted(got_serp), "need": sorted(need_serp)})

    aexp = s.get(f"{BASE}/api/runs/{rid}/availability/export", timeout=60).json()
    need_av = {"available_domains.txt", "domain_availability.csv", "availability_metadata.json"}
    got_av = set(aexp.get("files") or [])
    if not need_av.issubset(got_av):
        return fail("availability_export", {"got": sorted(got_av), "need": sorted(need_av)})

    # download available_domains.txt content check
    eid = aexp["export_id"]
    txt = s.get(
        f"{BASE}/api/exports/{eid}/availability/available_domains.txt",
        params={"run_id": rid},
        timeout=30,
    )
    txt.raise_for_status()
    raw_lines = [ln.strip() for ln in txt.text.splitlines() if ln.strip()]
    # allow leading # warning comments (export policy notice)
    lines = [ln for ln in raw_lines if not ln.startswith("#")]
    for ln in lines:
        if " " in ln or ln.upper() == "UNKNOWN" or "/" in ln or "://" in ln:
            return fail("available_txt_content", {"line": ln})

    ok(
        "exports",
        {
            "serp_export_id": serp_exp.get("export_id"),
            "serp_files": sorted(got_serp),
            "availability_export_id": eid,
            "availability_files": sorted(got_av),
            "available_domains_txt_lines": len(lines),
            "available_domains_sample": lines[:10],
            "export_counts": aexp.get("counts"),
        },
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS",
        "project_id": pid,
        "run_id": rid,
        "job_id": jid,
        "steps": steps,
        "costs": {
            "dataforseo_usd": prog.get("spent_usd"),
            "whoisfreaks_credits": jprog.get("spent_credits"),
            "whoisfreaks_usd_ref": jprog.get("spent_usd"),
        },
    }
    _write(steps, report)
    print("DEMO_E2E_OK", json.dumps(report["costs"]))
    return 0


def _write(steps: list, report: dict | None) -> None:
    if report is None:
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "verdict": "FAIL",
            "steps": steps,
        }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Demo E2E — SERP → domains → availability → Available → export",
        "",
        f"**Generated (UTC):** `{report['generated_at_utc']}`  ",
        f"**Verdict:** **{report.get('verdict')}**  ",
    ]
    if report.get("run_id"):
        lines.append(f"**Run:** `{report['run_id']}` · **Job:** `{report.get('job_id')}`  ")
    lines += ["", "## Steps", ""]
    for st in report.get("steps") or steps:
        lines.append(f"- **{st.get('status')}** `{st.get('step')}`")
    if report.get("costs"):
        c = report["costs"]
        lines += [
            "",
            "## Costs",
            "",
            f"| DataForSEO | `${c.get('dataforseo_usd')}` |",
            f"| WhoisFreaks | `{c.get('whoisfreaks_credits')}` credits / `${c.get('whoisfreaks_usd_ref')}` |",
            "",
        ]
    lines += [
        "## Checklist (TZ §17)",
        "",
        "| Step | Result |",
        "|---|---|",
        "| historical SERP | see `serp_run` |",
        "| unique domains | see `unique_domains` |",
        "| batch availability | see `availability_batch` |",
        "| filter Available | see `available_filter` (only PRELIMINARY/CONFIRMED) |",
        "| export | SERP files + `available_domains.txt` / CSV / metadata |",
        "",
        "Machine-readable: `docs/demo_e2e_latest.json`",
        "",
        "Procedure: `docs/demo_e2e_checklist.md`",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("WROTE", OUT_MD)


if __name__ == "__main__":
    sys.exit(main())
