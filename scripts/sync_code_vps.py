"""Re-upload code to VPS and restart hsdf-api (keeps server .env / DB volumes)."""

from __future__ import annotations

import io
import os
import sys
import tarfile
import time
from pathlib import Path

import paramiko
from dotenv import load_dotenv

HSDF_ROOT = Path(__file__).resolve().parents[1]
COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
REMOTE_ROOT = "/opt/historical_serp_domain_finder"
SKIP_NAMES = {".env"}


def _should_add(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return False
    rel = path.relative_to(HSDF_ROOT).as_posix()
    parts = rel.split("/")
    if parts[0] in {".venv", ".git", ".pytest_cache", ".mypy_cache"}:
        return False
    if "node_modules" in parts:
        return False
    if any(p == "__pycache__" or p.endswith(".pyc") for p in parts):
        return False
    # Source lives in frontend/; ship built SPA from app/static only
    if parts[0] == "frontend":
        return len(parts) == 2 and parts[1] in {"package.json", "package-lock.json"}
    if rel.startswith("spike/results/") and path.name != ".gitkeep":
        return False
    if rel.startswith("data/") and path.name != ".gitkeep":
        return False
    if rel.startswith("deploy/") and "credentials" in path.name:
        return False
    return path.is_file()


def main() -> int:
    load_dotenv(COMPANY_ENV)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in HSDF_ROOT.rglob("*"):
            if _should_add(path):
                tar.add(path, arcname=path.relative_to(HSDF_ROOT).as_posix())
    data = buf.getvalue()
    print(f"tarball {len(data)} bytes")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        os.getenv("VPS_HOST") or "89.163.221.244",
        username=os.getenv("VPS_USER") or "root",
        password=os.getenv("VPS_PW"),
        timeout=45,
    )
    sftp = client.open_sftp()
    remote_tar = "/tmp/hsdf_sync.tar.gz"
    with sftp.file(remote_tar, "wb") as rf:
        rf.write(data)
    sftp.close()

    def run(cmd: str) -> None:
        print("$", cmd)
        _i, o, e = client.exec_command(cmd, timeout=300)
        code = o.channel.recv_exit_status()
        print(o.read().decode("utf-8", "replace"), end="")
        err = e.read().decode("utf-8", "replace")
        if err.strip():
            print(err, end="")
        if code != 0:
            raise RuntimeError(f"exit {code}: {cmd}")

    run(f"tar -xzf {remote_tar} -C {REMOTE_ROOT} && rm -f {remote_tar}")
    run(f"cd {REMOTE_ROOT} && .venv/bin/alembic upgrade head")
    run("systemctl restart hsdf-api.service")
    for _ in range(20):
        time.sleep(1)
        _i, o, e = client.exec_command("curl -sf http://127.0.0.1:8872/health", timeout=30)
        if o.channel.recv_exit_status() == 0:
            print(o.read().decode())
            break
    else:
        run("journalctl -u hsdf-api.service -n 40 --no-pager")
        raise RuntimeError("health failed")
    client.close()
    print("SYNC OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
