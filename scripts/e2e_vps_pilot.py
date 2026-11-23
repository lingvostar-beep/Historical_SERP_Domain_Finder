"""Minimal live E2E via local SSH tunnel: project → SERP → domains → availability → exports.

Uses Basic auth from deploy/vps_bootstrap_credentials.txt. Does not print secrets.
Spends a tiny DataForSEO + WhoisFreaks budget (1–2 keywords, 1 GEO, short window).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / "deploy" / "vps_bootstrap_credentials.txt"
BASE = "http://127.0.0.1:8872"


def load_basic() -> tuple[str, str]:
    user, pw = "admin", ""
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_BASIC_USER="):
            user = line.split("=", 1)[1].strip()
        if line.startswith("APP_BASIC_PASSWORD="):
            pw = line.split("=", 1)[1].strip()
    if not pw:
        raise SystemExit("missing APP_BASIC_PASSWORD in credentials file")
    return user, pw


def main() -> int:
    auth = load_basic()
    s = requests.Session()
    s.auth = auth
    s.headers["Content-Type"] = "application/json"

    health = s.get(f"{BASE}/health", timeout=15)
    health.raise_for_status()
    print("health", health.json())

    win = s.get(f"{BASE}/api/meta/serp-window", timeout=15).json()
    print("serp_window", win)
    today = date.fromisoformat(win["today"])
    earliest = date.fromisoformat(win["earliest_allowed_date"])
    # Spike-proven AU window: amazon had organic in 2026-09 (Oct often empty).
    date_from = date(2026, 9, 1)
    date_to = date(2026, 9, 30)
    if date_from < earliest:
        date_from = earliest
    if date_to > today:
        date_to = today

    # 1) Project
    r = s.post(f"{BASE}/api/projects", json={"name": f"e2e-pilot-{today.isoformat()}"}, timeout=30)
    r.raise_for_status()
    project_id = r.json()["id"]
    print("project", project_id)

    # 2) Keywords (spike-proven AU coverage)
    r = s.post(
        f"{BASE}/api/projects/{project_id}/keywords/import",
        json={"text": "amazon\ncasino"},
        timeout=30,
    )
    r.raise_for_status()
    print("keywords", r.json())

    # 3) Target AU / en
    r = s.put(
        f"{BASE}/api/projects/{project_id}/targets",
        json={
            "targets": [
                {
                    "location_code": 2036,
                    "location_name": "Australia",
                    "language_code": "en",
                }
            ]
        },
        timeout=30,
    )
    r.raise_for_status()
    print("targets", r.json())

    # 4) Estimate + create SERP run
    est = s.post(
        f"{BASE}/api/projects/{project_id}/runs/estimate",
        json={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        timeout=30,
    )
    est.raise_for_status()
    print("estimate", est.json())

    run_body = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "depth": 10,
        "budget_cap": "1.00",
        "dedupe_mode": "registrable_domain",
        "availability_mode": "manual_after_serp",
        "start": True,
    }
    r = s.post(f"{BASE}/api/projects/{project_id}/runs", json=run_body, timeout=30)
    r.raise_for_status()
    run = r.json()
    run_id = run["id"]
    print("run", run_id, "started", run.get("worker_started"), "status", run.get("status"))

    # 5) Poll SERP run
    deadline = time.time() + 300
    last = None
    while time.time() < deadline:
        prog = s.get(f"{BASE}/api/runs/{run_id}", timeout=30).json()
        last = prog
        st = prog.get("status")
        print(
            f"  run_poll status={st} queries={prog.get('queries_by_status')} "
            f"snapshots={prog.get('snapshots')} spend={prog.get('spent_usd')}"
        )
        if st in {
            "COMPLETED",
            "COMPLETED_WITH_GAPS",
            "FAILED",
            "CANCELED",
            "BUDGET_EXCEEDED",
        }:
            break
        time.sleep(5)
    else:
        print("FAIL serp timeout", json.dumps(last, default=str)[:800])
        return 2

    if last.get("status") not in {"COMPLETED", "COMPLETED_WITH_GAPS"}:
        print("FAIL serp status", json.dumps(last, default=str)[:1200])
        return 3
    if not last.get("snapshots"):
        print("FAIL serp zero snapshots", json.dumps(last, default=str)[:1200])
        return 3

    # 6) Domains / coverage / positions smoke
    domains = s.get(f"{BASE}/api/runs/{run_id}/domains?page_size=20", timeout=30).json()
    cov = s.get(f"{BASE}/api/runs/{run_id}/coverage?page_size=20", timeout=30).json()
    pos = s.get(f"{BASE}/api/runs/{run_id}/positions?page_size=5", timeout=30).json()
    print(
        "domains_total",
        domains.get("total"),
        "coverage_total",
        cov.get("total"),
        "positions_sample",
        len(pos.get("items") or []),
    )
    if not domains.get("total"):
        print("FAIL no domains extracted")
        print("coverage_sample", json.dumps((cov.get("items") or [])[:5], default=str)[:800])
        return 6

    # 7) SERP export
    exp = s.post(f"{BASE}/api/runs/{run_id}/exports", timeout=60)
    exp.raise_for_status()
    export_meta = exp.json()
    print("serp_export", {k: export_meta.get(k) for k in ("export_id", "files", "path") if k in export_meta or True})
    print("serp_export_keys", sorted(export_meta.keys()))

    # 8) Availability estimate + job (cap small)
    aest = s.post(
        f"{BASE}/api/runs/{run_id}/availability/estimate",
        json={"force_refresh": False, "max_n": 10},
        timeout=60,
    )
    aest.raise_for_status()
    print("avail_estimate", aest.json())

    job_body = {
        "budget_cap_credits": 20,
        "force_refresh": False,
        "mode": "max_n",
        "max_n": 10,
        "start": True,
    }
    jr = s.post(f"{BASE}/api/runs/{run_id}/availability/jobs", json=job_body, timeout=30)
    jr.raise_for_status()
    job = jr.json()
    job_id = job["job_id"]
    print("avail_job", job_id)

    deadline = time.time() + 180
    jlast = None
    while time.time() < deadline:
        jlast = s.get(f"{BASE}/api/availability/jobs/{job_id}", timeout=30).json()
        st = jlast.get("status")
        print(f"  avail_poll {json.dumps(jlast, default=str)[:300]}")
        if st in {"COMPLETED", "FAILED", "CANCELED", "BUDGET_EXCEEDED"}:
            break
        time.sleep(3)
    else:
        print("FAIL avail timeout", json.dumps(jlast, default=str)[:800])
        return 4

    if jlast.get("status") not in {"COMPLETED", "BUDGET_EXCEEDED"}:
        print("FAIL avail status", json.dumps(jlast, default=str)[:1200])
        return 5

    avail_rows = s.get(f"{BASE}/api/runs/{run_id}/availability?page_size=20", timeout=30).json()
    print(
        "availability_rows",
        avail_rows.get("total"),
        "sample",
        json.dumps((avail_rows.get("items") or [])[:3], default=str)[:500],
    )
    if not avail_rows.get("total"):
        print("FAIL availability empty after job")
        return 7

    aexp = s.get(f"{BASE}/api/runs/{run_id}/availability/export", timeout=60)
    aexp.raise_for_status()
    print("avail_export", aexp.json())

    print(
        "E2E_OK",
        json.dumps(
            {
                "project_id": project_id,
                "run_id": run_id,
                "job_id": job_id,
                "domains": domains.get("total"),
                "availability_rows": avail_rows.get("total"),
                "serp_export_id": export_meta.get("export_id"),
                "avail_export_id": aexp.json().get("export_id"),
            }
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
