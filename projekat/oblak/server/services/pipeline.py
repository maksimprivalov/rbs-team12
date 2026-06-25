"""
Analysis pipeline
Poziva se kao FastAPI BackgroundTask odmah nakon uploada
Tok statusa:
  PENDING → ANALYZING → READY   (analiza prošla + pip install + invoke_url generisan)
                      → REJECTED (analiza odbila ili pip install pao)
"""

import logging
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from config import settings
from models import AuditLog, Function, FunctionStatus
from models.analysis import AnalysisResult
from services.verifier import analyze_function_code
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _install_requirements(
    function_dir: Path, function_id: int
) -> tuple[bool, str | None]:
    """
    Pokreće pip install -r requirements.txt u izolovanom venv poddirektorijumu
    Vraća (uspeh, poruka_greške)
    """
    req_file = function_dir / "requirements.txt"
    if not req_file.exists():
        logger.info("function_id=%d: nema requirements.txt", function_id)
        return True, None

    venv_dir = function_dir / "venv"
    venv_dir.mkdir(exist_ok=True)

    try:
        result = subprocess.run(
            [
                "pip",
                "install",
                "-r",
                str(req_file),
                "--target",
                str(venv_dir),
                "--quiet",
                "--no-cache-dir",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            err = result.stderr[:1000]
            logger.error("function_id=%d: pip install failed: %s", function_id, err)
            return False, f"pip install failed: {err}"
        return True, None

    except subprocess.TimeoutExpired:
        return False, "pip install timeout (>120s)"


def _generate_invoke_url(function_id: int) -> str:
    """
    Generiše kriptografski nepredvidiv UUID4 invoke URL
    Format: /invoke/<uuid4_hex>
    """
    token = uuid.uuid4().hex
    return f"/invoke/{token}"


def _cleanup_files(function_dir: Path) -> None:
    """Briše sve fajlove funkcije - poziva se pri REJECTED"""
    try:
        if function_dir.exists():
            shutil.rmtree(function_dir)
            logger.info("Obrisani fajlovi: %s", function_dir)
    except Exception as e:  # noqa: BLE001
        logger.error("Greška pri brisanju %s: %s", function_dir, e)


def _reject(func: Function, analysis: AnalysisResult, reason: str, db: Session) -> None:
    """Postavi REJECTED status i upiši audit log"""
    func.status = FunctionStatus.REJECTED
    analysis.final_verdict = "REJECTED"
    analysis.rejection_reason = reason
    db.add(
        AuditLog(
            user_id=func.user_id,
            action="FUNCTION_ANALYSIS_REJECTED",
            details=f"function_id={func.id} reason={reason[:300]}",
            timestamp=datetime.utcnow(),
        )
    )


def run_analysis_pipeline(function_id: int, db: Session) -> None:
    """
    Entry point koji se poziva iz BackgroundTasks u routes/functions.py
    """
    func: Function | None = (
        db.query(Function).filter(Function.id == function_id).first()
    )
    if not func:
        logger.error("pipeline: function_id=%d nije u bazi", function_id)
        return

    func.status = FunctionStatus.ANALYZING
    db.commit()

    function_dir = Path(settings.storage_path) / str(func.user_id) / str(func.id)

    # Placeholder analysis record (da GET /analysis odmah vrati 202 umesto 404)
    analysis = AnalysisResult(
        function_id=func.id,
        final_verdict="PENDING",
        analyzed_at=datetime.utcnow(),
    )
    db.add(analysis)
    db.flush()

    try:
        # Korak 1: Analiza koda
        verdict = analyze_function_code(function_dir)

        analysis.bandit_score = verdict.bandit_score
        analysis.bandit_report = verdict.bandit_report
        analysis.pylint_score = verdict.pylint_score
        analysis.pylint_report = verdict.pylint_report
        analysis.llm_verdict = verdict.llm_verdict
        analysis.llm_report = verdict.llm_report
        analysis.final_verdict = verdict.final_verdict
        analysis.rejection_reason = verdict.rejection_reason
        analysis.analyzed_at = datetime.utcnow()

        if verdict.final_verdict == "REJECTED":
            _reject(func, analysis, verdict.rejection_reason or "analiza odbila", db)
            _cleanup_files(function_dir)
            db.commit()
            return

        # Korak 2: pip install requirements.txt
        install_ok, install_err = _install_requirements(function_dir, func.id)
        if not install_ok:
            _reject(func, analysis, install_err or "pip install failed", db)
            _cleanup_files(function_dir)
            db.commit()
            return

        # Korak 3: Generisanje invoke URL-a
        # invoke_url = _generate_invoke_url(func.id)
        invoke_url = f"/invoke/{func.id}"
        func.invoke_url = invoke_url
        func.status = FunctionStatus.READY

        db.add(
            AuditLog(
                user_id=func.user_id,
                action="FUNCTION_READY",
                details=f"function_id={func.id} invoke_url={invoke_url}",
                timestamp=datetime.utcnow(),
            )
        )
        db.commit()
        logger.info("function_id=%d READY → %s", func.id, invoke_url)

    except Exception as e:  # noqa: BLE001
        logger.exception("pipeline: neočekivana greška za function_id=%d", function_id)
        try:
            func.status = FunctionStatus.REJECTED
            analysis.final_verdict = "REJECTED"
            analysis.rejection_reason = f"Internal error: {str(e)[:200]}"
            db.add(
                AuditLog(
                    user_id=func.user_id,
                    action="FUNCTION_ANALYSIS_ERROR",
                    details=f"function_id={func.id} error={str(e)[:300]}",
                    timestamp=datetime.utcnow(),
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001
            logger.error("pipeline: ne mogu da commitam error state")
