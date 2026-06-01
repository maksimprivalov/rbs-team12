from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models import AuditLog, Function, FunctionFile, FunctionStatus, User
from security import get_current_user
from storage import save_function_files

router = APIRouter(prefix="/functions", tags=["functions"])


class FunctionResponse(BaseModel):
    id: int
    name: str
    status: str
    invoke_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/upload", response_model=FunctionResponse, status_code=status.HTTP_201_CREATED)
async def upload_function(
    name: str,
    file: UploadFile = File(...),
    requirements: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Function:
    func = Function(
        user_id=current_user.id,
        name=name,
        status=FunctionStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    db.add(func)
    db.flush()

    saved = await save_function_files(current_user.id, func.id, file, requirements)
    for filename, storage_path in saved:
        db.add(FunctionFile(function_id=func.id, filename=filename, storage_path=storage_path))

    db.add(AuditLog(
        user_id=current_user.id,
        action="FUNCTION_UPLOAD",
        details=f"function_id={func.id} name={name} files={[f for f, _ in saved]}",
        timestamp=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(func)
    return func


@router.get("/", response_model=list[FunctionResponse])
def list_functions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Function]:
    return db.query(Function).filter(Function.user_id == current_user.id).all()


@router.get("/{function_id}", response_model=FunctionResponse)
def get_function(
    function_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Function:
    func = db.query(Function).filter(Function.id == function_id, Function.user_id == current_user.id).first()
    if not func:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Function not found")
    return func
