import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from models import AuditLog, Function, FunctionStatus, User
from security import get_current_user
from services.firecracker import (
    FirecrackerError,
    FirecrackerUnavailable,
    run_microvm,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoke", tags=["invoke"])


class InvokeResponse(BaseModel):
    function_id: int
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    error: str | None = None


@router.post("/{function_id}", response_model=InvokeResponse)
def invoke_function(
    function_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvokeResponse:
    func = db.query(Function).filter(Function.id == function_id).first()
    if not func:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")
    if func.user_id != current_user.id and not getattr(current_user, "is_admin", False):
        # Ne otkrivamo postojanje tuđe funkcije
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")
    if func.status != FunctionStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Function is not ready (status={func.status})",
        )

    function_dir = Path(settings.storage_path) / str(func.user_id) / str(func.id)

    db.add(AuditLog(
        user_id=current_user.id,
        action="FUNCTION_INVOKE_START",
        details=f"function_id={func.id}",
        timestamp=datetime.utcnow(),
    ))
    db.commit()

    try:
        result = run_microvm(function_dir)
    except FirecrackerUnavailable as exc:
        logger.error("Firecracker nedostupan za function_id=%d: %s", func.id, exc)
        db.add(AuditLog(
            user_id=current_user.id,
            action="FUNCTION_INVOKE_UNAVAILABLE",
            details=f"function_id={func.id} reason={str(exc)[:300]}",
            timestamp=datetime.utcnow(),
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Izvršno okruženje nije dostupno: {exc}",
        ) from exc
    except FirecrackerError as exc:
        logger.exception("Firecracker greška za function_id=%d", func.id)
        db.add(AuditLog(
            user_id=current_user.id,
            action="FUNCTION_INVOKE_ERROR",
            details=f"function_id={func.id} error={str(exc)[:300]}",
            timestamp=datetime.utcnow(),
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Greška pri izvršavanju: {exc}",
        ) from exc

    db.add(AuditLog(
        user_id=current_user.id,
        action="FUNCTION_INVOKE_DONE",
        details=(
            f"function_id={func.id} exit_code={result.exit_code} "
            f"timed_out={result.timed_out} duration_ms={result.duration_ms}"
        ),
        timestamp=datetime.utcnow(),
    ))
    db.commit()

    return InvokeResponse(
        function_id=func.id,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
        error=result.error,
    )
