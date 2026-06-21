"""
Firecracker MicroVM Orchestrator

Izvršava korisničku Python funkciju u Firecracker MicroVM-u.

Preduslovi (Linux sa KVM):
  - /dev/kvm dostupan
  - firecracker binarni fajl (FIRECRACKER_BIN env var ili /usr/local/bin/firecracker)
  - Kernel image  (FC_KERNEL env var ili /opt/firecracker/vmlinux.bin)
  - Base rootfs   (FC_ROOTFS env var ili /opt/firecracker/python.ext4)
    Kreira se sa: scripts/setup-firecracker.sh
  - debugfs (e2fsprogs paket) — za inject koda u ext4 sliku

Tok izvršavanja:
  1. Kreira malu ext4 sliku sa korisničkim main.py (code drive)
  2. Pokreće Firecracker proces sa API socketom
  3. Konfigurira VM: vCPU, RAM, kernel, rootfs drive, code drive
  4. Startuje VM — guest init čita kod sa /dev/vdb i pokreće ga
  5. Čita output sa serial konzole (Firecracker stdout)
  6. Čeka završetak ili ubija VM pri timeoutu
  7. Briše sve privremene fajlove
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FIRECRACKER_BIN = os.environ.get("FIRECRACKER_BIN", "/usr/local/bin/firecracker")
KERNEL_IMAGE    = os.environ.get("FC_KERNEL",       "/opt/firecracker/vmlinux.bin")
BASE_ROOTFS     = os.environ.get("FC_ROOTFS",       "/opt/firecracker/python.ext4")

VCPU_COUNT        = 1
MEM_SIZE_MIB      = 128
EXECUTION_TIMEOUT = 30
MAX_OUTPUT_BYTES  = 64 * 1024    # 64 KB
CODE_IMG_MB       = 8            # veličina ext4 slike sa kodom


@dataclass
class ExecutionResult:
    output: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


def is_available() -> bool:
    """Vraća True ako su svi preduslovi za Firecracker ispunjeni."""
    return (
        Path(FIRECRACKER_BIN).exists()
        and Path(KERNEL_IMAGE).exists()
        and Path(BASE_ROOTFS).exists()
        and os.path.exists("/dev/kvm")
    )


# --- Firecracker REST API (Unix socket) ---

def _api_call(sock_path: str, method: str, endpoint: str, body: dict | None = None) -> int:
    """
    Šalje HTTP zahtev Firecracker API-ju preko Unix socketa.
    Vraća HTTP status kod.
    """
    payload = json.dumps(body).encode() if body is not None else b""
    request = (
        f"{method} {endpoint} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Accept: application/json\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"\r\n"
    ).encode() + payload

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect(sock_path)
        s.sendall(request)

        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\r\n\r\n" in response:
                break

    status_line = response.split(b"\r\n")[0].decode()
    status_code = int(status_line.split()[1])
    return status_code


def _wait_for_socket(sock_path: str, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(sock_path):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    s.connect(sock_path)
                return True
            except OSError:
                pass
        time.sleep(0.05)
    return False


# --- Code drive ---

def _create_code_drive(code_dir: Path, main_py: Path, venv_dir: Path | None) -> Path:
    """
    Kreira malu ext4 sliku koja sadrži korisnikov main.py.
    Guest init montira ovu sliku kao /dev/vdb i pokreće /code/main.py.
    """
    img_path = code_dir / "code.ext4"

    # Pravi praznu ext4 sliku
    subprocess.run(
        ["dd", "if=/dev/zero", f"of={img_path}", "bs=1M", f"count={CODE_IMG_MB}"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["mkfs.ext4", "-F", "-L", "code", str(img_path)],
        check=True, capture_output=True,
    )

    # Upisuje main.py u sliku koristeći debugfs
    subprocess.run(
        ["debugfs", "-w", str(img_path), "-R", f"write {main_py} /main.py"],
        check=True, capture_output=True, timeout=10,
    )

    # Ako postoji venv, kopira samo site-packages direktorijum
    if venv_dir and venv_dir.exists():
        subprocess.run(
            ["debugfs", "-w", str(img_path), "-R", "mkdir /venv"],
            check=True, capture_output=True, timeout=5,
        )
        for pkg in venv_dir.iterdir():
            subprocess.run(
                ["debugfs", "-w", str(img_path), "-R", f"write {pkg} /venv/{pkg.name}"],
                capture_output=True, timeout=30,
            )

    return img_path


# --- Glavni orchestrator ---

def run_function(function_dir: Path) -> ExecutionResult:
    """
    Izvršava main.py iz function_dir u Firecracker MicroVM-u.
    Vraća ExecutionResult sa outputom, exit kodom i trajanjem.
    """
    main_py = function_dir / "main.py"
    if not main_py.exists():
        return ExecutionResult(
            output="Error: main.py not found in function directory",
            exit_code=1,
            duration_ms=0,
        )

    work_dir   = Path(tempfile.mkdtemp(prefix="fc_"))
    sock_path  = str(work_dir / "fc.sock")
    fc_log     = work_dir / "fc.log"
    serial_out = work_dir / "serial.log"
    fc_proc    = None

    try:
        # 1. Kreiramo code drive
        venv_dir = function_dir / "venv"
        code_img = _create_code_drive(work_dir, main_py, venv_dir if venv_dir.exists() else None)

        # 2. Startujemo Firecracker
        #    Bez --no-seccomp jer je sandbox u defaultu bezbedan
        #    Serial konzola ide na stdout Firecrackera → čitamo iz pipe-a
        fc_proc = subprocess.Popen(
            [
                FIRECRACKER_BIN,
                "--api-sock", sock_path,
                "--log-path", str(fc_log),
                "--level", "Error",
            ],
            stdout=open(serial_out, "wb"),  # noqa: WPS515 — serial output za kasniji čitanje
            stderr=subprocess.DEVNULL,
        )

        if not _wait_for_socket(sock_path):
            raise RuntimeError("Firecracker API socket nije spreman na vreme")

        # 3. Konfigurišemo VM
        _api_call(sock_path, "PUT", "/machine-config", {
            "vcpu_count": VCPU_COUNT,
            "mem_size_mib": MEM_SIZE_MIB,
            "track_dirty_pages": False,
        })

        _api_call(sock_path, "PUT", "/boot-source", {
            "kernel_image_path": KERNEL_IMAGE,
            # console=ttyS0 — serial output ide na ttyS0 → Firecracker stdout
            # init=/init — naš custom init koji pokreće Python
            # quiet — eliminišemo kernel boot spam iz outputa
            "boot_args": (
                "console=ttyS0 reboot=k panic=1 pci=off nomodules "
                "init=/init quiet loglevel=0"
            ),
        })

        # Rootfs — sadrži Python, busybox i naš /init skripta
        _api_call(sock_path, "PUT", "/drives/rootfs", {
            "drive_id": "rootfs",
            "path_on_host": BASE_ROOTFS,
            "is_root_device": True,
            "is_read_only": True,   # read-only — zaštita od izmene base slike
        })

        # Code drive — sadrži korisnikov main.py, montira se kao /dev/vdb
        _api_call(sock_path, "PUT", "/drives/code", {
            "drive_id": "code",
            "path_on_host": str(code_img),
            "is_root_device": False,
            "is_read_only": True,
        })

        # Mrežni interfejs NIJE konfigurisan — VM nema outbound pristup po defaultu
        # Za buduću implementaciju: TAP device sa iptables DROP policy

        # 4. Startujemo VM
        start = time.monotonic()
        status = _api_call(sock_path, "PUT", "/actions", {"action_type": "InstanceStart"})
        if status not in (200, 204):
            raise RuntimeError(f"InstanceStart vratio status {status}")

        # 5. Čekamo završetak ili timeout
        timed_out = False
        try:
            fc_proc.wait(timeout=EXECUTION_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            logger.warning("fc: VM timeout — šaljemo SendCtrlAltDel pa kill")
            try:
                _api_call(sock_path, "PUT", "/actions", {"action_type": "SendCtrlAltDel"})
                fc_proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                fc_proc.kill()

        duration_ms = int((time.monotonic() - start) * 1000)

        # 6. Čitamo serial output
        output = ""
        if serial_out.exists():
            raw = serial_out.read_bytes()
            output = raw.decode("utf-8", errors="replace")
            if len(raw) > MAX_OUTPUT_BYTES:
                output = (
                    raw[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
                    + "\n[output truncated]"
                )

        # Parsiramo exit kod koji init skripta upisuje na kraj outputa
        exit_code = 0 if not timed_out else -1
        if "EXIT_CODE:" in output:
            lines = output.splitlines()
            for line in reversed(lines):
                if line.startswith("EXIT_CODE:"):
                    try:
                        exit_code = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                    # Uklanjamo EXIT_CODE liniju iz output-a koji vidji korisnik
                    output = "\n".join(l for l in lines if not l.startswith("EXIT_CODE:"))
                    break

        if timed_out:
            output = f"Execution timed out after {EXECUTION_TIMEOUT} seconds.\n" + output

        return ExecutionResult(
            output=output.strip(),
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    finally:
        # 7. Uvek čistimo VM i temp fajlove
        if fc_proc and fc_proc.poll() is None:
            fc_proc.kill()
            try:
                fc_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        shutil.rmtree(work_dir, ignore_errors=True)
