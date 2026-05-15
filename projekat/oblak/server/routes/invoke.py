from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from models import Function, FunctionStatus, User
from security import get_current_user

router = APIRouter(prefix="/invoke", tags=["invoke"])


@router.post("/{function_id}")
def invoke_function(
    function_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    func = db.query(Function).filter(Function.id == function_id).first()
    if not func:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")
    if func.status != FunctionStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Function is not ready (status={func.status})")
    # Implementuje Član 3 (Firecracker Orchestrator)
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Invoke not implemented yet")
