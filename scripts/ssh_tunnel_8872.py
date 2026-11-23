"""Local SSH tunnel: 127.0.0.1:8872 -> VPS 127.0.0.1:8872 (HSDF API)."""

from __future__ import annotations

import os
import select
import socket
import sys
import threading
from pathlib import Path

import paramiko
from dotenv import load_dotenv

COMPANY_ENV = Path(r"d:\Cursor\gambling_sites_company\.env")
LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8872
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 8872


def _handler(chan: paramiko.Channel, peer: socket.socket) -> None:
    try:
        while True:
            r, _w, _x = select.select([chan, peer], [], [])
            if chan in r:
                data = chan.recv(65536)
                if not data:
                    break
                peer.sendall(data)
            if peer in r:
                data = peer.recv(65536)
                if not data:
                    break
                chan.sendall(data)
    finally:
        try:
            chan.close()
        except Exception:
            pass
        try:
            peer.close()
        except Exception:
            pass


def main() -> int:
    load_dotenv(COMPANY_ENV)
    host = os.getenv("VPS_HOST") or "89.163.221.244"
    user = os.getenv("VPS_USER") or "root"
    pw = os.getenv("VPS_PW")
    if not pw:
        print("VPS_PW missing", file=sys.stderr)
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=pw, timeout=30)
    transport = client.get_transport()
    assert transport is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LOCAL_HOST, LOCAL_PORT))
    sock.listen(100)
    print(f"TUNNEL_UP http://{LOCAL_HOST}:{LOCAL_PORT}/docs  ->  {host}:{REMOTE_PORT}", flush=True)

    try:
        while True:
            peer, addr = sock.accept()
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (REMOTE_HOST, REMOTE_PORT),
                    peer.getpeername(),
                )
            except Exception as exc:
                print(f"open_channel failed from {addr}: {exc}", flush=True)
                peer.close()
                continue
            t = threading.Thread(target=_handler, args=(chan, peer), daemon=True)
            t.start()
    finally:
        sock.close()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
