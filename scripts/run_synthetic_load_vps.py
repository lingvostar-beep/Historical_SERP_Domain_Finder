"""Sync code to VPS, run synthetic seed+bench there, pull docs/*.json|md back."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import paramiko
from dotenv import load_dotenv

HSDF_ROOT = Path(__file__).resolve().parents[1]
COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
REMOTE_ROOT = "/opt/historical_serp_domain_finder"


def main() -> int:
    load_dotenv(COMPANY_ENV)
    # Ensure latest script is on VPS
    sync = HSDF_ROOT / "scripts" / "sync_code_vps.py"
    print("syncing…")
    rc = subprocess.call([sys.executable, str(sync)], cwd=str(HSDF_ROOT))
    if rc != 0:
        return rc

    host = os.getenv("VPS_HOST") or "89.163.221.244"
    user = os.getenv("VPS_USER") or "root"
    password = os.getenv("VPS_PW")
    if not password:
        print("VPS_PW missing", file=sys.stderr)
        return 2

    cmd = (
        f"cd {REMOTE_ROOT} && .venv/bin/python scripts/seed_synthetic_load.py "
        f"--replace --keywords 500 --months 12 --locations 2 --depth 10 --domains 5000"
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=45)
    try:
        print("$", cmd)
        _i, o, e = client.exec_command(cmd, timeout=1800)
        code = o.channel.recv_exit_status()
        out = o.read().decode("utf-8", "replace")
        err = e.read().decode("utf-8", "replace")
        print(out, end="")
        if err.strip():
            print(err, end="", file=sys.stderr)
        if code != 0:
            return code

        sftp = client.open_sftp()
        for name in ("synthetic_load_latest.json", "synthetic_load_latest.md"):
            remote = f"{REMOTE_ROOT}/docs/{name}"
            local = HSDF_ROOT / "docs" / name
            sftp.get(remote, str(local))
            print(f"pulled {local}")
        sftp.close()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
