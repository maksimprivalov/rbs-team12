#!/usr/bin/env python3
"""
End-to-end demo: deploy-uje sve test primere, sačeka analizu, pa pozove one koji
prođu (READY) u Firecracker microVM-u. Pokazuje da:

  - benigni kod prolazi i izvršava se (vraća output),
  - maliciozni kod biva ODBIJEN u analizi (Bandit HIGH),
  - "izolacioni" primeri prođu analizu ali ih VM obuzda (timeout / nema mreže).

Server mora biti pokrenut (scripts/run_server.sh) i Firecracker postavljen
(scripts/firecracker/setup.sh + build-rootfs.sh).

Upotreba:
    python scripts/demo.py
    OBLAK_SERVER=http://localhost:8000 python scripts/demo.py
"""

import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "tests" / "examples"
SERVER = os.environ.get("OBLAK_SERVER", "http://localhost:8000")
USERNAME = os.environ.get("OBLAK_USER", "alice")
PASSWORD = os.environ.get("OBLAK_PASS", "alice123")

# (putanja, requirements|None, očekivani_ishod, da_li_pozvati)
CASES = [
    ("benign/hello.py",        None,                      "READY",    True),
    ("benign/compute.py",      None,                      "READY",    True),
    ("benign/with_deps.py",    "benign/requirements.txt", "READY",    True),
    ("malicious/exfil.py",         None,                  "REJECTED", False),
    ("malicious/reverse_shell.py", None,                  "REJECTED", False),
    ("malicious/destroy.py",       None,                  "REJECTED", False),
    ("isolation/infinite_loop.py", None,                  "READY",    True),
    ("isolation/no_network.py",    None,                  "READY",    True),
]


def login() -> str:
    resp = httpx.post(f"{SERVER}/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


def upload(client: httpx.Client, code: Path, reqs: Path | None, name: str) -> int:
    files = {"file": (code.name, code.read_bytes(), "text/x-python")}
    if reqs:
        files["requirements"] = ("requirements.txt", reqs.read_bytes(), "text/plain")
    resp = client.post("/functions/upload", params={"name": name}, files=files)
    resp.raise_for_status()
    return resp.json()["id"]


def wait_status(client: httpx.Client, fid: int, timeout_s: int = 180) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/functions/{fid}")
        resp.raise_for_status()
        st = resp.json()["status"]
        if st not in ("PENDING", "ANALYZING"):
            return st
        time.sleep(1.5)
    return "TIMEOUT_WAIT"


def rejection_reason(client: httpx.Client, fid: int) -> str:
    resp = client.get(f"/functions/{fid}/analysis")
    if resp.status_code == 200:
        return resp.json().get("rejection_reason") or "(bez razloga)"
    return f"(analysis HTTP {resp.status_code})"


def main() -> int:
    print(f"Server: {SERVER}  | korisnik: {USERNAME}")
    try:
        token = login()
    except Exception as exc:  # noqa: BLE001
        print(f"GREŠKA pri loginu: {exc}\nDa li je server pokrenut i seed-ovan?", file=sys.stderr)
        return 1

    client = httpx.Client(base_url=SERVER, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    results = []

    for rel, reqrel, expected, do_invoke in CASES:
        code = EXAMPLES / rel
        reqs = (EXAMPLES / reqrel) if reqrel else None
        name = rel.replace("/", "-").removesuffix(".py")
        print(f"\n=== {rel} (očekivano: {expected}) ===")

        fid = upload(client, code, reqs, name)
        status = wait_status(client, fid)
        print(f"  status -> {status}")

        outcome = "OK" if status == expected else f"NEOČEKIVANO (dobijeno {status})"

        if status == "REJECTED":
            print(f"  razlog: {rejection_reason(client, fid)}")
        elif status == "READY" and do_invoke:
            r = client.post(f"/invoke/{fid}")
            if r.status_code == 200:
                d = r.json()
                print(f"  invoke -> exit={d['exit_code']} timed_out={d['timed_out']} dur={d['duration_ms']}ms")
                if d.get("stdout"):
                    print("  --- stdout ---")
                    for line in d["stdout"].rstrip().splitlines():
                        print(f"    {line}")
                if d.get("error"):
                    print(f"  error: {d['error']}")
            else:
                detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
                print(f"  invoke -> HTTP {r.status_code}: {detail}")
                outcome = f"INVOKE FAIL ({r.status_code})"

        results.append((rel, expected, status, outcome))

    print("\n================ SAŽETAK ================")
    for rel, expected, status, outcome in results:
        print(f"  {rel:32s} {expected:9s} -> {status:9s} [{outcome}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
