"""Public nginx + TLS for HSDF at https://hsdf.datamonosite.com

Idempotent: DNS A (CF DNS-only) → nginx vhost → certbot → reload.
Does not touch dashboard / Rybbit / plan / domains sites, and does not overwrite
the app tree or VPS .env. App stays on 127.0.0.1:8872 with existing Basic auth.

  python scripts/deploy_nginx_vps.py
  python scripts/deploy_nginx_vps.py --nginx-only   # skip DNS (record already set)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import paramiko
from dotenv import load_dotenv

HSDF_ROOT = Path(__file__).resolve().parents[1]
COMPANY_ROOT = Path(r"d:\Cursor\gambling_sites_company")
COMPANY_ENV = COMPANY_ROOT / ".env"

HOST = "89.163.221.244"
ZONE = "datamonosite.com"
CF_LOGIN = "miyata_shea@gmx.com"
DOMAIN = f"hsdf.{ZONE}"
PORT = 8872
CERT_DIR = f"/etc/letsencrypt/live/{DOMAIN}"
SITE = f"/etc/nginx/sites-available/{DOMAIN}"
NOINDEX = "noindex, nofollow, noarchive, nosnippet, noimageindex"


def nginx_config(*, tls: bool) -> str:
    body = f"""
    client_max_body_size 32m;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    add_header X-Robots-Tag "{NOINDEX}" always;
    add_header Referrer-Policy "no-referrer" always;

    location = /robots.txt {{
        default_type text/plain;
        return 200 "User-agent: *\\nDisallow: /\\n";
    }}

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        proxy_pass http://127.0.0.1:{PORT};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
"""
    if not tls:
        return (
            f"server {{\n"
            f"    listen 80;\n"
            f"    listen [::]:80;\n"
            f"    server_name {DOMAIN};\n"
            f"{body}}}\n"
        )
    return f"""server {{
    listen 80;
    listen [::]:80;
    server_name {DOMAIN};
    add_header X-Robots-Tag "{NOINDEX}" always;

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {DOMAIN};
    ssl_certificate {CERT_DIR}/fullchain.pem;
    ssl_certificate_key {CERT_DIR}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
{body}}}
"""


def ensure_dns() -> None:
    sys.path.insert(0, str(COMPANY_ROOT))
    from pipeline.cloudflare_client import CloudflareClient  # noqa: WPS433
    from pipeline.dm_client import DmClient, load_dm_config  # noqa: WPS433
    from pipeline.env_loader import load_dotenv as company_load_dotenv  # noqa: WPS433

    company_load_dotenv()
    dm = DmClient.from_env(load_dm_config())
    info = dm.get_cf_account_info(login=CF_LOGIN)
    cf = CloudflareClient(info["api_key"], email=info["login"])
    zones = [z for z in cf.find_zone_any_account(ZONE) if z.get("name") == ZONE]
    if not zones:
        raise SystemExit(f"zone {ZONE} not found")
    zid = zones[0]["id"]
    want = {"type": "A", "name": DOMAIN, "content": HOST, "proxied": False, "ttl": 1}
    match = next(
        (r for r in cf.list_dns_records(zid) if r.get("type") == "A" and r.get("name") == DOMAIN),
        None,
    )
    if match is None:
        cf.create_dns_record(zid, want)
        print("DNS: created A", DOMAIN, "->", HOST, "(DNS only)")
    elif match.get("content") != HOST or bool(match.get("proxied")):
        cf.update_dns_record(zid, match["id"], want)
        print("DNS: updated A", DOMAIN, "->", HOST, "(DNS only)")
    else:
        print("DNS: A", DOMAIN, "->", HOST, "already there")


def _ssh() -> paramiko.SSHClient:
    load_dotenv(COMPANY_ENV)
    pw = os.getenv("VPS_PW")
    if not pw:
        raise SystemExit("VPS_PW missing in company .env")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=os.getenv("VPS_USER") or "root", password=pw, timeout=45)
    return client


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> str:
    print(f"$ {cmd}")
    _i, out, err = client.exec_command(cmd, timeout=timeout)
    text = (out.read() + err.read()).decode("utf-8", "replace")
    status = out.channel.recv_exit_status()
    if text.strip():
        print(text.rstrip())
    if status != 0:
        raise RuntimeError(f"remote exit {status}: {cmd}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nginx-only", action="store_true", help="skip Cloudflare DNS ensure")
    args = ap.parse_args()

    if not args.nginx_only:
        ensure_dns()

    client = _ssh()
    try:
        health = _run(client, f"curl -sf http://127.0.0.1:{PORT}/health")
        if "ok" not in health.lower() and '"status"' not in health.lower():
            # accept any 200 body; curl -sf already failed on non-2xx
            print("local health:", health.strip()[:200] or "(empty 200)")

        sftp = client.open_sftp()
        has_cert = _run(client, f"test -f {CERT_DIR}/fullchain.pem && echo yes || echo no").strip().endswith("yes")
        if not has_cert:
            with sftp.open(SITE, "w") as fh:
                fh.write(nginx_config(tls=False))
            _run(client, f"ln -sfn {SITE} /etc/nginx/sites-enabled/{DOMAIN}")
            _run(client, "nginx -t && systemctl reload nginx")
            # DNS may need a few seconds after create
            _run(
                client,
                f"for i in 1 2 3 4 5 6 7 8 9 10; do "
                f"getent hosts {DOMAIN} >/dev/null && break; sleep 3; done; "
                f"getent hosts {DOMAIN} || true",
            )
            _run(
                client,
                f"certbot certonly --webroot -w /var/www/html -d {DOMAIN} "
                f"--non-interactive --agree-tos --register-unsafely-without-email",
                timeout=600,
            )

        _run(client, f"cp -p {SITE} {SITE}.bak-hsdf 2>/dev/null || true")
        with sftp.open(SITE, "w") as fh:
            fh.write(nginx_config(tls=True))
        sftp.close()
        test = _run(client, "nginx -t 2>&1")
        if "successful" not in test:
            _run(client, f"cp -p {SITE}.bak-hsdf {SITE} 2>/dev/null || true")
            raise SystemExit("nginx -t failed — previous site file restored if backup existed")
        _run(client, f"ln -sfn {SITE} /etc/nginx/sites-enabled/{DOMAIN} && systemctl reload nginx")

        code = _run(
            client,
            f"curl -sS -o /dev/null -w '%{{http_code}}' --resolve {DOMAIN}:443:127.0.0.1 "
            f"https://{DOMAIN}/health",
        ).strip()
        print(f"HTTPS /health via local resolve: {code}")
        if code != "200":
            raise SystemExit(f"expected 200 from https://{DOMAIN}/health, got {code}")
        print(f"OK — https://{DOMAIN}/  (Basic auth as before)")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
