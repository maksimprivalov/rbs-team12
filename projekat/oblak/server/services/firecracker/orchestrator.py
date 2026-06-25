"""
Firecracker orchestrator (host strana).

Za svaki invoke pokreće se nov, jednokratan Firecracker microVM:

  1. Od korisnikovog `function_dir` (main.py + venv/) napravi se "job" ext4
     image (bez root privilegija, preko `mkfs.ext4 -d`).
  2. Pokrene se `firecracker` proces sa Unix API socket-om.
  3. Preko REST API-ja (HTTP preko UDS) konfigurišu se: kernel, rootfs (ro),
     job drive (ro), CPU/RAM limiti, pa se VM startuje.
  4. Guest agent (oblak-run.py, PID1 u VM-u) izvrši kod i emituje rezultat na
     serijsku konzolu; host čita stdout Firecracker procesa i parsira rezultat.
  5. VM se gasi (guest reboot -> Firecracker izlazi); host briše privremene
     fajlove. Ako VM pređe wall-clock timeout, host ga ubije.

Mrežna izolacija: nijedan network interfejs se ne konfiguriše -> guest nema
mrežu. Rootfs je read-only i deljiv između VM-ova; upisi idu u tmpfs.

Modul je import-safe na svim platformama. Sve što zavisi od Linux/KVM dešava
se tek u `run_microvm()`; `preflight()` daje jasnu grešku ako okruženje nije
spremno (npr. pokretanje na Windows-u bez Firecracker-a).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger(__name__)

_SENTINEL_BEGIN = "===OBLAK-RESULT-BEGIN==="
_SENTINEL_END = "===OBLAK-RESULT-END==="
_RESULT_RE = re.compile(
    re.escape(_SENTINEL_BEGIN) + r"\s*(?P<json>\{.*?\})\s*" + re.escape(_SENTINEL_END),
    re.DOTALL,
)

# Minimalna veličina job image-a; realna = 2x sadržaj + rezerva.
_MIN_JOB_IMAGE_BYTES = 32 * 1024 * 1024
_JOB_IMAGE_MARGIN_BYTES = 16 * 1024 * 1024


@dataclass
class ExecutionResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    error: str | None = None


class FirecrackerError(RuntimeError):
    """Bazna greška orkestratora."""


class FirecrackerUnavailable(FirecrackerError):
    """Okruženje nije spremno za Firecracker (nema binarke/kernela/KVM-a)."""


def _asset_paths() -> tuple[Path, Path]:
    """Izvodi (kernel, rootfs) putanje iz konfigurisanog assets foldera."""
    base = Path(settings.firecracker_assets)
    return base / "vmlinux", base / "rootfs.ext4"


def _resolve_bin() -> Path | None:
    """
    Razrešava firecracker binarku: puna/relativna putanja ako je data,
    inače traži po PATH-u. Vraća None ako nije pronađena.
    """
    raw = settings.firecracker_bin
    if "/" in raw or "\\" in raw or os.path.isabs(raw):
        p = Path(raw)
        return p if p.exists() else None
    found = shutil.which(raw)
    return Path(found) if found else None


def preflight() -> None:
    """
    Proverava da li je host spreman za pokretanje microVM-ova.
    Diže FirecrackerUnavailable sa opisom prvog problema.
    """
    if not settings.firecracker_enabled:
        raise FirecrackerUnavailable("Firecracker je onemogućen (FIRECRACKER_ENABLED=false)")

    fc_bin = _resolve_bin()
    if fc_bin is None:
        raise FirecrackerUnavailable(
            f"firecracker binarka nije pronađena (firecracker_bin={settings.firecracker_bin!r}; "
            "nije na PATH-u). Pokreni scripts/firecracker/setup.sh."
        )
    if not os.access(fc_bin, os.X_OK):
        raise FirecrackerUnavailable(f"firecracker binarka nije izvršna: {fc_bin}")

    kernel, rootfs = _asset_paths()
    if not kernel.exists():
        raise FirecrackerUnavailable(
            f"kernel image nije pronađen: {kernel} (pokreni scripts/firecracker/setup.sh)"
        )
    if not rootfs.exists():
        raise FirecrackerUnavailable(
            f"rootfs image nije pronađen: {rootfs} (pokreni scripts/firecracker/build-rootfs.sh)"
        )

    kvm = Path("/dev/kvm")
    if not kvm.exists():
        raise FirecrackerUnavailable("/dev/kvm ne postoji (nema KVM-a; Firecracker traži Linux + virtualizaciju)")
    if not os.access(kvm, os.R_OK | os.W_OK):
        raise FirecrackerUnavailable("/dev/kvm nije čitljiv/upisiv za ovog korisnika (dodaj korisnika u 'kvm' grupu)")

    if shutil.which("mkfs.ext4") is None:
        raise FirecrackerUnavailable("mkfs.ext4 nije dostupan (instaliraj e2fsprogs)")


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def _build_job_image(function_dir: Path, dest: Path) -> None:
    """
    Pravi ext4 image od sadržaja function_dir (main.py, venv/, ...) bez root-a,
    koristeći `mkfs.ext4 -d`. Sadržaj postaje koren job drive-a (-> /job u VM-u).
    """
    size = max(_MIN_JOB_IMAGE_BYTES, _dir_size(function_dir) * 2 + _JOB_IMAGE_MARGIN_BYTES)

    with open(dest, "wb") as fh:
        fh.truncate(size)

    proc = subprocess.run(
        ["mkfs.ext4", "-F", "-q", "-d", str(function_dir), str(dest)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise FirecrackerError(f"mkfs.ext4 nije uspeo: {proc.stderr.strip() or proc.stdout.strip()}")


def _wait_for_socket(sock_path: Path, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if sock_path.exists() and stat.S_ISSOCK(sock_path.stat().st_mode):
            return
        time.sleep(0.05)
    raise FirecrackerError("Firecracker API socket se nije pojavio na vreme")


def _api_put(client: httpx.Client, path: str, body: dict) -> None:
    resp = client.put(path, json=body)
    if resp.status_code not in (200, 204):
        raise FirecrackerError(f"Firecracker API {path} -> {resp.status_code}: {resp.text}")


def _configure_vm(client: httpx.Client, kernel: Path, rootfs: Path, job_img: Path, timeout_s: int) -> None:
    boot_args = (
        "console=ttyS0 root=/dev/vda ro reboot=k panic=-1 pci=off "
        "i8042.noaux=1 i8042.nomux=1 i8042.nopnp=1 i8042.dumbkbd=1 "
        "random.trust_cpu=on "
        "init=/usr/local/bin/oblak-run.py "
        f"OBLAK_TIMEOUT={timeout_s}"
    )
    _api_put(client, "/boot-source", {
        "kernel_image_path": str(kernel),
        "boot_args": boot_args,
    })
    _api_put(client, "/drives/rootfs", {
        "drive_id": "rootfs",
        "path_on_host": str(rootfs),
        "is_root_device": True,
        "is_read_only": True,
    })
    _api_put(client, "/drives/job", {
        "drive_id": "job",
        "path_on_host": str(job_img),
        "is_root_device": False,
        "is_read_only": True,
    })
    _api_put(client, "/machine-config", {
        "vcpu_count": settings.firecracker_vcpu,
        "mem_size_mib": settings.firecracker_mem_mib,
        "smt": False,
    })
    _api_put(client, "/actions", {"action_type": "InstanceStart"})


def _parse_result(console_output: str, fc_logs: str, timed_out: bool) -> ExecutionResult:
    import base64

    match = _RESULT_RE.search(console_output)
    if not match:
        tail = (console_output[-800:] or fc_logs[-800:]).strip()
        return ExecutionResult(
            exit_code=None,
            stdout="",
            stderr="",
            duration_ms=0,
            timed_out=timed_out,
            error=(
                "VM nije vratio rezultat (wall-clock timeout)" if timed_out
                else f"rezultat nije pronađen u izlazu VM-a. Poslednje linije:\n{tail}"
            ),
        )

    try:
        data = json.loads(match.group("json"))
    except json.JSONDecodeError as exc:
        return ExecutionResult(None, "", "", 0, timed_out, error=f"neispravan JSON rezultat: {exc}")

    def _dec(field: str) -> str:
        try:
            return base64.b64decode(data.get(field, "")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""

    return ExecutionResult(
        exit_code=data.get("exit_code"),
        stdout=_dec("stdout"),
        stderr=_dec("stderr"),
        duration_ms=int(data.get("duration_ms", 0)),
        timed_out=bool(data.get("timed_out", False)),
        error=data.get("error"),
    )


def run_microvm(function_dir: Path) -> ExecutionResult:
    """
    Izvršava korisnikov kod iz `function_dir` u jednokratnom Firecracker VM-u.
    Sinhrono (blokira do završetka VM-a). Diže FirecrackerUnavailable ako host
    nije spreman, FirecrackerError za operativne greške.
    """
    preflight()

    function_dir = Path(function_dir)
    if not (function_dir / "main.py").exists():
        raise FirecrackerError(f"main.py ne postoji u {function_dir}")

    fc_bin = _resolve_bin()
    kernel, rootfs = _asset_paths()
    guest_timeout = settings.firecracker_exec_timeout
    host_timeout = guest_timeout + 20  # rezerva za boot/shutdown

    workdir = Path(tempfile.mkdtemp(prefix="oblak-vm-"))
    sock_path = workdir / "firecracker.sock"
    job_img = workdir / "job.ext4"
    vm_id = uuid.uuid4().hex[:12]
    proc: subprocess.Popen | None = None

    try:
        _build_job_image(function_dir, job_img)

        proc = subprocess.Popen(
            [str(fc_bin), "--id", vm_id, "--api-sock", str(sock_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            cwd=str(workdir),
            text=True,
        )

        _wait_for_socket(sock_path)

        transport = httpx.HTTPTransport(uds=str(sock_path))
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            _configure_vm(client, kernel, rootfs, job_img, guest_timeout)

        timed_out = False
        try:
            console_output, fc_logs = proc.communicate(timeout=host_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            console_output, fc_logs = proc.communicate()

        result = _parse_result(console_output or "", fc_logs or "", timed_out)
        logger.info(
            "microVM vm_id=%s završen: exit=%s timed_out=%s duration=%dms",
            vm_id, result.exit_code, result.timed_out, result.duration_ms,
        )
        return result

    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(workdir, ignore_errors=True)
