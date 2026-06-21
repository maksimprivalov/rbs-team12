"""
Sandbox Orchestrator

Izvršava korisničku Python funkciju u izolovanom subprocess okruženju.
Arhitekturno odgovara Firecracker MicroVM: orchestrator → izolovano izvršavanje
→ capture output → cleanup. U produkciji se zamenjuje Firecracker + jailer.

Izolacioni mehanizmi:
  - Novi process session (start_new_session=True) — izolacija od parent grupe
  - Minimalan environment (bez HOME, PATH, kredencijala servera)
  - CPU time limit via resource.RLIMIT_CPU (Linux)
  - Memory limit via resource.RLIMIT_AS (Linux)
  - Process count limit via resource.RLIMIT_NPROC (Linux, sprečava fork bomb)
  - Hard timeout via subprocess timeout=30s
  - Privremeni radni direktorijum, uvek se briše po završetku
"""

import logging
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT_S = 30
MAX_CPU_SECONDS = 30
MAX_MEMORY_BYTES = 128 * 1024 * 1024   # 128 MB
MAX_NPROC = 50
MAX_OUTPUT_BYTES = 64 * 1024            # 64 KB


@dataclass
class ExecutionResult:
    output: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


def _apply_resource_limits() -> None:
    """Postavlja OS resource limite za child process. Samo Linux/Mac."""
    try:
        import resource  # noqa: PLC0415
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (MAX_NPROC, MAX_NPROC))
    except Exception:  # noqa: BLE001
        pass  # Windows ili nedostupno — timeout je fallback


def run_function(function_dir: Path) -> ExecutionResult:
    """
    Izvršava main.py iz function_dir u sandbox okruženju.
    Uvek briše privremeni radni direktorijum po završetku.
    """
    main_py = function_dir / "main.py"
    if not main_py.exists():
        return ExecutionResult(
            output="Error: main.py not found in function directory",
            exit_code=1,
            duration_ms=0,
        )

    # Kopiramo u privremeni dir — sandbox ne može da menja originalne fajlove
    work_dir = Path(tempfile.mkdtemp(prefix="oblak_exec_"))
    try:
        shutil.copy2(main_py, work_dir / "main.py")

        # Minimalan environment — ne curimo kredencijale servera
        exec_env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "TMPDIR": str(work_dir),
            "HOME": str(work_dir),
        }

        # PYTHONPATH na pre-instalirani venv (iz pipeline.py pip install koraka)
        venv_dir = function_dir / "venv"
        if venv_dir.exists():
            exec_env["PYTHONPATH"] = str(venv_dir)

        preexec_fn = _apply_resource_limits if sys.platform != "win32" else None

        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "main.py"],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=EXECUTION_TIMEOUT_S,
                env=exec_env,
                start_new_session=True,
                preexec_fn=preexec_fn,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            combined = proc.stdout + proc.stderr
            if len(combined.encode("utf-8", errors="replace")) > MAX_OUTPUT_BYTES:
                combined = (
                    combined.encode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
                    .decode("utf-8", errors="replace")
                    + "\n[output truncated]"
                )

            return ExecutionResult(
                output=combined,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("sandbox: execution timed out after %ds", EXECUTION_TIMEOUT_S)
            return ExecutionResult(
                output=f"Execution timed out after {EXECUTION_TIMEOUT_S} seconds.",
                exit_code=-1,
                duration_ms=duration_ms,
                timed_out=True,
            )

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
