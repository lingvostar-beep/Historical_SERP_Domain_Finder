from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko
from dotenv import load_dotenv

load_dotenv(Path(r"d:\Cursor\gambling_sites_company\.env"))
creds = Path(__file__).resolve().parents[1] / "deploy" / "vps_bootstrap_credentials.txt"
user, pw = "admin", ""
for line in creds.read_text(encoding="utf-8").splitlines():
    if line.startswith("APP_BASIC_USER="):
        user = line.split("=", 1)[1]
    if line.startswith("APP_BASIC_PASSWORD="):
        pw = line.split("=", 1)[1]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    os.getenv("VPS_HOST") or "89.163.221.244",
    username=os.getenv("VPS_USER") or "root",
    password=os.getenv("VPS_PW"),
    timeout=30,
)
cmd = (
    f"curl -sS -u '{user}:{pw}' http://127.0.0.1:8872/openapi.json"
)
_i, o, e = client.exec_command(cmd, timeout=60)
raw = o.read().decode("utf-8", "replace")
err = e.read().decode("utf-8", "replace")
client.close()
if err.strip():
    print(err)
data = json.loads(raw)
paths = [p for p in data.get("paths", {}) if "availability" in p]
print("availability_paths", len(paths))
for p in paths:
    print(p)
