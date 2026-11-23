"""Rotate APP_BASIC_PASSWORD on VPS + local credentials file. Prints nothing secret."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sys
from pathlib import Path

import paramiko
from dotenv import load_dotenv

HSDF = Path(__file__).resolve().parents[1]
CREDS = HSDF / "deploy" / "vps_bootstrap_credentials.txt"
COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
REMOTE_ENV = "/opt/historical_serp_domain_finder/.env"


def main() -> int:
    load_dotenv(COMPANY_ENV)
    new_pw = secrets.token_urlsafe(18)
    new_sha = hashlib.sha256(new_pw.encode()).hexdigest()[:16]

    # local credentials file
    text = CREDS.read_text(encoding="utf-8")
    if "APP_BASIC_PASSWORD=" not in text:
        raise SystemExit("APP_BASIC_PASSWORD missing in credentials file")
    text2, n = re.subn(
        r"(?m)^APP_BASIC_PASSWORD=.*$",
        f"APP_BASIC_PASSWORD={new_pw}",
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit("failed to rewrite local APP_BASIC_PASSWORD")
    CREDS.write_text(text2, encoding="utf-8", newline="\n")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        os.getenv("VPS_HOST") or "89.163.221.244",
        username=os.getenv("VPS_USER") or "root",
        password=os.getenv("VPS_PW"),
        timeout=30,
    )
    try:
        # rewrite remote .env line via python to avoid shell quoting
        remote_py = f"""
import re, pathlib, hashlib
p = pathlib.Path({REMOTE_ENV!r})
t = p.read_text(encoding='utf-8')
t2, n = re.subn(r'(?m)^APP_BASIC_PASSWORD=.*$', 'APP_BASIC_PASSWORD=' + {new_pw!r}, t, count=1)
assert n == 1, n
p.write_text(t2, encoding='utf-8')
pw = next(line.split('=',1)[1].strip() for line in t2.splitlines() if line.startswith('APP_BASIC_PASSWORD='))
print('vps_pw_sha', hashlib.sha256(pw.encode()).hexdigest()[:16])
print('vps_pw_len', len(pw))
"""
        _i, o, e = client.exec_command(f"python3 - <<'PY'\n{remote_py}\nPY", timeout=30)
        out = o.read().decode()
        err = e.read().decode()
        print(out.strip())
        if err.strip():
            print(err.strip(), file=sys.stderr)
        if f"vps_pw_sha {new_sha}" not in out:
            raise SystemExit("VPS password rewrite mismatch")
        _i, o, e = client.exec_command(
            "systemctl restart hsdf-api.service && sleep 2 && curl -sf http://127.0.0.1:8872/health",
            timeout=60,
        )
        print(o.read().decode().strip())
        print(e.read().decode().strip())
    finally:
        client.close()

    print("local_pw_sha", new_sha)
    print("OK — copy APP_BASIC_PASSWORD from deploy/vps_bootstrap_credentials.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
