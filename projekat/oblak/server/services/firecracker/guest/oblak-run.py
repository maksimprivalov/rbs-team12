#!/usr/local/bin/python3
"""
Oblak guest agent - pokreće se kao PID 1 (init) unutar Firecracker microVM-a.

Zadatak:
  1. Montira pseudo-fajlsisteme (/proc, /sys, /dev) i tmpfs za /tmp.
  2. Montira "job" drive (/dev/vdb, read-only) na /job - sadrži korisnikov
     main.py i instalirane zavisnosti (venv/).
  3. Pokreće `python main.py` kao zaseban proces sa timeout-om, hvata
     stdout/stderr/exit_code.
  4. Emituje rezultat kao JSON (base64-enkodovan stdout/stderr) na serijsku
     konzolu, okružen sentinelima koje host parsira.
  5. Gasi VM (reboot syscall -> Firecracker proces izlazi).

Namerno nema mrežnog interfejsa (Firecracker ga ne konfiguriše), pa je guest
potpuno mrežno izolovan. Rootfs je read-only -> bezbedno deljenje između VM-ova;
upisi idu samo u tmpfs /tmp.

Pisano da zavisi SAMO od glibc + Python stdlib (bez mount/poweroff binarki),
jer python:3.11-slim rootfs ne garantuje te alate.
"""

import base64
import ctypes
import json
import os
import subprocess
import sys
import time

SENTINEL_BEGIN = "===OBLAK-RESULT-BEGIN==="
SENTINEL_END = "===OBLAK-RESULT-END==="

# Linux mount flag
MS_RDONLY = 1
# glibc reboot() magični cmd: LINUX_REBOOT_CMD_RESTART
LINUX_REBOOT_CMD_RESTART = 0x01234567

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


def _mount(source: str, target: str, fstype: str, flags: int = 0, data: str | None = None) -> None:
    os.makedirs(target, exist_ok=True)
    res = _libc.mount(
        source.encode(),
        target.encode(),
        fstype.encode(),
        ctypes.c_ulong(flags),
        ctypes.c_char_p(data.encode()) if data else None,
    )
    if res != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"mount({source}, {target}, {fstype}) failed: {os.strerror(err)}")


def _shutdown() -> None:
    """Gasi VM. Firecracker presreće restart i izlazi iz procesa."""
    try:
        os.sync()
    except Exception:
        pass
    try:
        _libc.reboot(LINUX_REBOOT_CMD_RESTART)
    except Exception:
        # Ako reboot ne uspe, ostani u petlji da kernel ne panikuje na PID1 exit
        while True:
            time.sleep(3600)


def _cmdline_value(key: str, default: str) -> str:
    try:
        with open("/proc/cmdline", encoding="ascii", errors="replace") as fh:
            for tok in fh.read().split():
                if tok.startswith(key + "="):
                    return tok.split("=", 1)[1]
    except Exception:
        pass
    return default


def _emit(result: dict) -> None:
    payload = dict(result)
    payload["stdout"] = base64.b64encode(result.get("stdout", "").encode("utf-8", "replace")).decode("ascii")
    payload["stderr"] = base64.b64encode(result.get("stderr", "").encode("utf-8", "replace")).decode("ascii")
    sys.stdout.write("\n" + SENTINEL_BEGIN + "\n")
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n" + SENTINEL_END + "\n")
    sys.stdout.flush()


def _run() -> dict:
    result = {
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "duration_ms": 0,
        "timed_out": False,
        "error": None,
    }

    timeout = 30
    try:
        timeout = max(1, int(_cmdline_value("OBLAK_TIMEOUT", "30")))
    except ValueError:
        pass

    # Montiraj job drive (read-only)
    try:
        _mount("/dev/vdb", "/job", "ext4", MS_RDONLY)
    except OSError as exc:
        result["error"] = f"ne mogu da montiram job drive: {exc}"
        return result

    main_py = "/job/main.py"
    if not os.path.exists(main_py):
        result["error"] = "main.py nije pronađen na job drive-u"
        return result

    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "LANG": "C.UTF-8",
    }
    if os.path.isdir("/job/venv"):
        env["PYTHONPATH"] = "/job/venv"

    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "main.py"],
            cwd="/job",
            env=env,
            capture_output=True,
            timeout=timeout,
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = proc.stdout.decode("utf-8", "replace")
        result["stderr"] = proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        result["timed_out"] = True
        result["exit_code"] = -1
        result["stdout"] = (exc.stdout or b"").decode("utf-8", "replace")
        result["stderr"] = (exc.stderr or b"").decode("utf-8", "replace")
        result["error"] = f"izvršavanje prekoračilo {timeout}s"
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"greška pri pokretanju koda: {exc}"

    result["duration_ms"] = int((time.monotonic() - start) * 1000)
    return result


def main() -> None:
    # Pseudo-fajlsistemi. Greške ignorišemo (npr. ako su već montirani).
    for source, target, fstype in (
        ("proc", "/proc", "proc"),
        ("sysfs", "/sys", "sysfs"),
        ("devtmpfs", "/dev", "devtmpfs"),
        ("tmpfs", "/tmp", "tmpfs"),
    ):
        try:
            _mount(source, target, fstype)
        except OSError:
            pass

    result = _run()
    _emit(result)
    _shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - poslednja linija odbrane, uvek emituj nešto
        try:
            _emit({
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "duration_ms": 0,
                "timed_out": False,
                "error": f"fatalna greška guest agenta: {exc}",
            })
        except Exception:
            pass
        _shutdown()
