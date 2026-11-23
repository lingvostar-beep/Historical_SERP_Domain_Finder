"""Dump HSDF Postgres on VPS (hsdf-db) into /opt/.../backups/. Never prints DB password.

Usage:
  python scripts/backup_postgres_vps.py
  python scripts/backup_postgres_vps.py --pull
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import paramiko
from dotenv import load_dotenv

HSDF_ROOT = Path(__file__).resolve().parents[1]
COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
REMOTE_ROOT = "/opt/historical_serp_domain_finder"
REMOTE_BACKUPS = f"{REMOTE_ROOT}/backups"
LOCAL_BACKUPS = HSDF_ROOT / "backups"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup hsdf-db on VPS")
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Download dump into local backups/ (gitignored)",
    )
    args = parser.parse_args()

    load_dotenv(COMPANY_ENV)
    host = os.getenv("VPS_HOST") or "89.163.221.244"
    user = os.getenv("VPS_USER") or "root"
    password = os.getenv("VPS_PW")
    if not password:
        print("VPS_PW missing in company .env", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    remote_name = f"hsdf_{stamp}.dump"
    remote_path = f"{REMOTE_BACKUPS}/{remote_name}"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=45)
    try:
        cmds = [
            f"mkdir -p {REMOTE_BACKUPS}",
            "docker exec hsdf-db pg_dump -U hsdf -d hsdf -Fc -f /tmp/hsdf_backup.dump",
            f"docker cp hsdf-db:/tmp/hsdf_backup.dump {remote_path}",
            "docker exec hsdf-db rm -f /tmp/hsdf_backup.dump",
            f"stat -c '%s' {remote_path}",
        ]
        size = None
        for cmd in cmds:
            _i, o, e = client.exec_command(cmd, timeout=300)
            out = o.read().decode("utf-8", "replace").strip()
            err = e.read().decode("utf-8", "replace").strip()
            code = o.channel.recv_exit_status()
            if code != 0:
                print(f"FAIL ({code}): {cmd}\n{err or out}", file=sys.stderr)
                return 3
            if cmd.startswith("stat"):
                size = out
        print(f"BACKUP_OK remote={remote_path} bytes={size}")

        if args.pull:
            LOCAL_BACKUPS.mkdir(parents=True, exist_ok=True)
            local_path = LOCAL_BACKUPS / remote_name
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, str(local_path))
            finally:
                sftp.close()
            print(f"PULLED local={local_path} bytes={local_path.stat().st_size}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
