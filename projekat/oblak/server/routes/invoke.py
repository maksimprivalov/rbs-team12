from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from models import AuditLog, Function, FunctionStatus, User
from security import get_current_user
from services import firecracker, sandbox

router = APIRouter(prefix="/invoke", tags=["invoke"])


class InvokeResponse(BaseModel):
    output: str
    exit_code: int
    duration_ms: int
    runtime: str   # "firecracker" | "sandbox"


@router.post("/{token}")
def invoke_function(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvokeResponse:
    """
    Pokreće funkciju po function_id (integer) ili UUID invoke tokenu.
    Koristi Firecracker MicroVM ako je dostupan, inače subprocess sandbox.
    Svaki poziv se upisuje u audit_log.
    """
    func: Function | None = None

    # Pokušaj po integer ID-u (vlasnik mora biti current_user)
    try:
        fid = int(token)
        func = (
            db.query(Function)
            .filter(Function.id == fid, Function.user_id == current_user.id)
            .first()
        )
    except ValueError:
        pass

    # Pokušaj po UUID invoke_url tokenu
    if func is None:
        invoke_url = f"/invoke/{token}"
        func = db.query(Function).filter(Function.invoke_url == invoke_url).first()

    if func is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")

    if func.status != FunctionStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Function is not ready (status={func.status})",
        )

    function_dir = Path(settings.storage_path) / str(func.user_id) / str(func.id)

    # Biramo runtime: Firecracker > subprocess sandbox
    if firecracker.is_available():
        result = firecracker.run_function(function_dir)
        runtime = "firecracker"
    else:
        result = sandbox.run_function(function_dir)
        runtime = "sandbox"

    db.add(AuditLog(
        user_id=current_user.id,
        action="FUNCTION_INVOKE",
        details=(
            f"function_id={func.id} "
            f"runtime={runtime} "
            f"exit_code={result.exit_code} "
            f"duration_ms={result.duration_ms} "
            f"timed_out={result.timed_out}"
        ),
        timestamp=datetime.utcnow(),
    ))
    db.commit()

    return InvokeResponse(
        output=result.output,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        runtime=runtime,
    )
