"""Pull VPS .env fields into local gitignored credentials file; smoke-test health."""

from __future__ import annotations

import os
from pathlib import Path

import paramiko
from dotenv import dotenv_values, load_dotenv

HSDF = Path(__file__).resolve().parents[1]
COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
REMOTE = "/opt/historical_serp_domain_finder/.env"

load_dotenv(COMPANY_ENV)
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    os.getenv("VPS_HOST") or "89.163.221.244",
    username=os.getenv("VPS_USER") or "root",
    password=os.getenv("VPS_PW"),
    timeout=30,
)
sftp = client.open_sftp()
local_tmp = HSDF / "deploy" / ".vps_env_tmp"
sftp.get(REMOTE, str(local_tmp))
sftp.close()

vals = dotenv_values(local_tmp)
local_tmp.unlink(missing_ok=True)

basic_user = vals.get("APP_BASIC_USER") or "admin"
basic_password = vals.get("APP_BASIC_PASSWORD") or ""
db_url = vals.get("DATABASE_URL") or ""

creds = HSDF / "deploy" / "vps_bootstrap_credentials.txt"
creds.write_text(
    f"""# Generated after VPS bootstrap — DO NOT COMMIT
VPS=89.163.221.244
REMOTE_ROOT=/opt/historical_serp_domain_finder
APP_ON_SERVER=http://127.0.0.1:8872/
TUNNEL=ssh -L 8872:127.0.0.1:8872 root@89.163.221.244
THEN_OPEN=http://127.0.0.1:8872/docs
APP_BASIC_USER={basic_user}
APP_BASIC_PASSWORD={basic_password}
DATABASE_URL={db_url}
POSTGRES_PORT=5434
REDIS_PORT=6381
SERVICE=hsdf-api.service
COMPOSE=docker compose -f docker-compose.vps.yml --env-file .env
""",
    encoding="utf-8",
)

# smoke
for cmd in [
    "curl -sS http://127.0.0.1:8872/health",
    f"curl -sS -u '{basic_user}:{basic_password}' http://127.0.0.1:8872/api/meta/serp-window",
    "curl -sS -u admin:wrong http://127.0.0.1:8872/api/health/db; echo",
    f"curl -sS -u '{basic_user}:{basic_password}' http://127.0.0.1:8872/api/health/db",
]:
    print(">>>", cmd.split(" -u ")[0], "...")
    _i, o, e = client.exec_command(cmd, timeout=30)
    print(o.read().decode("utf-8", "replace"))
    err = e.read().decode("utf-8", "replace")
    if err.strip():
        print(err)

client.close()
print("Wrote", creds)
