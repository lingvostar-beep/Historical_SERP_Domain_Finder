"""
Bootstrap HSDF on dashboard VPS.

Uses company .env for SSH (VPS_PW) and this project's .env for API keys.
Does not touch /opt/gambling_sites_company or Rybbit compose.
"""

from __future__ import annotations

import io
import os
import secrets
import stat
import sys
import tarfile
import time
from pathlib import Path

import paramiko
from dotenv import dotenv_values, load_dotenv

HSDF_ROOT = Path(__file__).resolve().parents[1]
COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
REMOTE_ROOT = "/opt/historical_serp_domain_finder"

SKIP_DIRS = {".venv", "__pycache__", ".git", "spike/results", "data/raw", "data/cache", "agent-tools"}
SKIP_NAMES = {".env"}  # write server .env separately


def _ssh() -> paramiko.SSHClient:
    load_dotenv(COMPANY_ENV)
    host = os.getenv("VPS_HOST") or "89.163.221.244"
    user = os.getenv("VPS_USER") or "root"
    pw = os.getenv("VPS_PW")
    if not pw:
        raise SystemExit("VPS_PW missing in company .env")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=pw, timeout=45)
    return client


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> str:
    print(f"$ {cmd}")
    _i, out, err = client.exec_command(cmd, timeout=timeout)
    exit_status = out.channel.recv_exit_status()
    text = out.read().decode("utf-8", "replace")
    etext = err.read().decode("utf-8", "replace")
    if text:
        print(text.rstrip())
    if etext.strip():
        print(etext.rstrip())
    if exit_status != 0:
        raise RuntimeError(f"remote exit {exit_status}: {cmd}")
    return text


def _should_add(path: Path) -> bool:
    rel = path.relative_to(HSDF_ROOT).as_posix()
    if path.name in SKIP_NAMES:
        return False
    parts = rel.split("/")
    if any(p == "__pycache__" or p.endswith(".pyc") for p in parts):
        return False
    if parts[0] in {".venv", ".git"}:
        return False
    if rel.startswith("spike/results/") and path.name != ".gitkeep":
        return False
    if rel.startswith("data/raw/") and path.name != ".gitkeep":
        return False
    if rel.startswith("data/cache/") and path.name != ".gitkeep":
        return False
    return True


def _build_tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in HSDF_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if not _should_add(path):
                continue
            arcname = path.relative_to(HSDF_ROOT).as_posix()
            tar.add(path, arcname=arcname)
    return buf.getvalue()


def _server_env(pg_password: str, basic_password: str) -> str:
    local = dotenv_values(HSDF_ROOT / ".env")
    def g(key: str, default: str = "") -> str:
        return (local.get(key) or default).strip()

    return f"""APP_ENV=vps
APP_HOST=127.0.0.1
APP_PORT=8872
APP_BASIC_USER=admin
APP_BASIC_PASSWORD={basic_password}

HSDF_PG_PASSWORD={pg_password}
DATABASE_URL=postgresql+psycopg://hsdf:{pg_password}@127.0.0.1:5434/hsdf
REDIS_URL=redis://127.0.0.1:6381/0

DATAFORSEO_LOGIN={g('DATAFORSEO_LOGIN')}
DATAFORSEO_PASSWORD={g('DATAFORSEO_PASSWORD')}
DATAFORSEO_MAX_HISTORY_DAYS=365
DATAFORSEO_PRIMARY_SOURCE=dataforseo_google_current
DATAFORSEO_REFERENCE_PRICE_PER_SNAPSHOT=0.00012
DATAFORSEO_CONCURRENCY=5

WHOISFREAKS_API_KEY={g('WHOISFREAKS_API_KEY')}
WHOISFREAKS_CACHE_TTL_HOURS=24
WHOISFREAKS_REFERENCE_USD_PER_CREDIT=0.004

GODADDY_PAT={g('GODADDY_PAT')}

RAW_STORAGE_DIR=data/raw
LOCATIONS_CACHE_PATH=data/cache/locations_and_languages.json
LOCATIONS_CACHE_TTL_HOURS=24
"""


def main() -> int:
    if not (HSDF_ROOT / ".env").exists():
        raise SystemExit("local .env missing")
    if not COMPANY_ENV.exists():
        raise SystemExit(f"company .env missing: {COMPANY_ENV}")

    pg_password = secrets.token_urlsafe(18)
    basic_password = secrets.token_urlsafe(18)
    tarball = _build_tarball()
    print(f"tarball bytes: {len(tarball)}")

    client = _ssh()
    try:
        _run(client, f"mkdir -p {REMOTE_ROOT}")
        sftp = client.open_sftp()
        remote_tar = "/tmp/hsdf_bootstrap.tar.gz"
        with sftp.file(remote_tar, "wb") as rf:
            rf.write(tarball)
        # write .env
        env_body = _server_env(pg_password, basic_password)
        with sftp.file(f"{REMOTE_ROOT}/.env", "w") as ef:
            ef.write(env_body)
        sftp.chmod(f"{REMOTE_ROOT}/.env", 0o600)
        sftp.close()

        _run(
            client,
            f"tar -xzf {remote_tar} -C {REMOTE_ROOT} && rm -f {remote_tar}",
        )
        _run(client, f"mkdir -p {REMOTE_ROOT}/data/raw {REMOTE_ROOT}/data/cache")
        _run(
            client,
            f"cd {REMOTE_ROOT} && docker compose -f docker-compose.vps.yml --env-file .env up -d",
        )
        # wait for postgres
        for _ in range(30):
            try:
                _run(
                    client,
                    "docker exec hsdf-db pg_isready -U hsdf -d hsdf",
                    timeout=30,
                )
                break
            except RuntimeError:
                time.sleep(2)
        else:
            raise RuntimeError("postgres did not become ready")

        _run(client, "apt-get install -y python3-venv python3-pip >/tmp/hsdf_apt.log 2>&1 || true")
        _run(
            client,
            f"cd {REMOTE_ROOT} && python3 -m venv .venv && "
            f".venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt",
            timeout=900,
        )
        _run(client, f"cd {REMOTE_ROOT} && .venv/bin/alembic upgrade head")
        _run(client, f"cp {REMOTE_ROOT}/deploy/hsdf-api.service /etc/systemd/system/hsdf-api.service")
        _run(client, "systemctl daemon-reload && systemctl enable --now hsdf-api.service")
        # uvicorn import can take a few seconds after systemd reports active
        healthy = False
        for _ in range(20):
            time.sleep(1)
            try:
                _run(client, "curl -sf http://127.0.0.1:8872/health")
                healthy = True
                break
            except RuntimeError:
                continue
        if not healthy:
            _run(client, "journalctl -u hsdf-api.service -n 50 --no-pager || true")
            raise RuntimeError("API did not become healthy on :8872")
        _run(client, "systemctl is-active hsdf-api.service")
        _run(
            client,
            "curl -sS -u admin:dummy http://127.0.0.1:8872/api/meta/serp-window >/dev/null 2>&1; "
            f"curl -sS -u 'admin:{basic_password}' http://127.0.0.1:8872/api/meta/serp-window",
        )
        _run(client, "docker ps --filter name=hsdf --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    finally:
        client.close()

    # Save local pointer for operator (not the PG password in chat if avoidable — write to local file)
    creds_path = HSDF_ROOT / "deploy" / "vps_bootstrap_credentials.txt"
    creds_path.write_text(
        f"""# Generated by bootstrap_vps.py — DO NOT COMMIT
VPS=89.163.221.244
REMOTE_ROOT={REMOTE_ROOT}
APP=http://127.0.0.1:8872/  (on server; SSH tunnel: ssh -L 8872:127.0.0.1:8872 root@89.163.221.244)
APP_BASIC_USER=admin
APP_BASIC_PASSWORD={basic_password}
DATABASE_URL=postgresql+psycopg://hsdf:{pg_password}@127.0.0.1:5434/hsdf
POSTGRES_PORT=5434
REDIS_PORT=6381
SERVICE=hsdf-api.service
""",
        encoding="utf-8",
    )
    print(f"Wrote {creds_path} (gitignored via deploy/*.txt pattern if set)")
    print("BOOTSTRAP OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
