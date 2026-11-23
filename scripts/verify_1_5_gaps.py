"""Verify 1.5 gap fixes on VPS via tunnel (list projects + hostname export + auto_after_serp)."""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / "deploy" / "vps_bootstrap_credentials.txt"
BASE = "http://127.0.0.1:8872"


def auth() -> tuple[str, str]:
    user, pw = "admin", ""
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        if line.startswith("APP_BASIC_USER="):
            user = line.split("=", 1)[1].strip()
        if line.startswith("APP_BASIC_PASSWORD="):
            pw = line.split("=", 1)[1].strip()
    return user, pw


def main() -> int:
    s = requests.Session()
    s.auth = auth()
    s.headers["Content-Type"] = "application/json"

    # 1) list projects
    lst = s.get(f"{BASE}/api/projects?page_size=5", timeout=30)
    lst.raise_for_status()
    body = lst.json()
    assert "items" in body and "total" in body, body
    print("list_projects_ok", body["total"], "sample", len(body["items"]))

    # 2) mini run with auto_after_serp + hostname dedupe
    p = s.post(f"{BASE}/api/projects", json={"name": "verify-1.5-auto"}, timeout=30).json()
    pid = p["id"]
    s.post(f"{BASE}/api/projects/{pid}/keywords/import", json={"text": "amazon"}, timeout=30).raise_for_status()
    s.put(
        f"{BASE}/api/projects/{pid}/targets",
        json={"targets": [{"location_code": 2036, "location_name": "Australia", "language_code": "en"}]},
        timeout=30,
    ).raise_for_status()

    run = s.post(
        f"{BASE}/api/projects/{pid}/runs",
        json={
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
            "depth": 10,
            "budget_cap": "1.00",
            "dedupe_mode": "hostname",
            "availability_mode": "auto_after_serp",
            "start": True,
        },
        timeout=30,
    ).json()
    rid = run["id"]
    print("run", rid)

    deadline = time.time() + 180
    prog = None
    while time.time() < deadline:
        prog = s.get(f"{BASE}/api/runs/{rid}", timeout=30).json()
        if prog.get("status") in {"COMPLETED", "COMPLETED_WITH_GAPS", "FAILED", "BUDGET_EXCEEDED"}:
            break
        time.sleep(3)
    print("serp_done", prog.get("status"), "snapshots", prog.get("snapshots"))
    if prog.get("status") not in {"COMPLETED", "COMPLETED_WITH_GAPS"} or not prog.get("snapshots"):
        print("FAIL serp", prog)
        return 2

    # wait for auto availability job to appear and finish
    job_id = None
    deadline = time.time() + 120
    while time.time() < deadline:
        # discover via availability list / estimate side-effect: poll OpenAPI-less —
        # GET domains then check availability rows OR probe jobs via estimate + known pattern
        avail = s.get(f"{BASE}/api/runs/{rid}/availability?page_size=50", timeout=30).json()
        if avail.get("total"):
            print("auto_avail_rows", avail["total"])
            break
        time.sleep(3)
    else:
        # one more chance: maybe job still running with 0 rows until apply
        print("WARN no availability rows yet; checking export hostname")

    exp = s.post(f"{BASE}/api/runs/{rid}/exports", timeout=60).json()
    eid = exp["export_id"]
    meta = s.get(
        f"{BASE}/api/exports/{eid}",
        params={"run_id": rid},
        timeout=30,
    )
    # FileResponse of metadata
    meta.raise_for_status()
    mjson = meta.json()
    kind = (mjson.get("counts") or {}).get("unique_list_kind")
    print("export_unique_kind", kind, "unique_count", (mjson.get("counts") or {}).get("unique_domains"))
    if kind != "hostname":
        print("FAIL expected unique_list_kind=hostname", mjson.get("counts"))
        return 3

    # confirm availability eventually populated by auto job
    deadline = time.time() + 90
    while time.time() < deadline:
        avail = s.get(f"{BASE}/api/runs/{rid}/availability?page_size=50", timeout=30).json()
        if avail.get("total"):
            print("VERIFY_OK", {"project": pid, "run": rid, "avail": avail["total"], "export": eid})
            return 0
        time.sleep(3)

    print("FAIL auto_after_serp did not populate availability")
    return 4


if __name__ == "__main__":
    sys.exit(main())
