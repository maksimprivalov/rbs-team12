#!/usr/bin/env python3
"""
Smoke test za Firecracker orchestrator - pokreće jednu microVM bez servera.

Pravi privremeni "function_dir" sa malim main.py i izvršava ga kroz
services.firecracker.run_microvm. Korisno za ručno testiranje na Arch/WSL
nakon setup.sh + build-rootfs.sh.

Pokretanje (iz oblak/ root-a):
    python scripts/firecracker/smoke_test.py
    python scripts/firecracker/smoke_test.py path/do/main.py
"""

import sys
import tempfile
from pathlib import Path

# Omogući import server modula
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from services.firecracker import FirecrackerUnavailable, run_microvm  # noqa: E402

DEFAULT_CODE = """\
import sys, platform
print("Pozdrav iz Firecracker microVM-a!")
print("python:", sys.version.split()[0], "| platforma:", platform.machine())
sys.stderr.write("ovo ide na stderr\\n")
sys.exit(7)
"""


def main() -> int:
    if len(sys.argv) > 1:
        src = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        src = DEFAULT_CODE

    with tempfile.TemporaryDirectory(prefix="oblak-smoke-") as d:
        (Path(d) / "main.py").write_text(src, encoding="utf-8")
        try:
            result = run_microvm(Path(d))
        except FirecrackerUnavailable as exc:
            print(f"[NEDOSTUPNO] {exc}", file=sys.stderr)
            return 2

    print("=== REZULTAT ===")
    print("exit_code  :", result.exit_code)
    print("timed_out  :", result.timed_out)
    print("duration_ms:", result.duration_ms)
    print("error      :", result.error)
    print("--- stdout ---")
    print(result.stdout, end="")
    print("--- stderr ---")
    print(result.stderr, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
