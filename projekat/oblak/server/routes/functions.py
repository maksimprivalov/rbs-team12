import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from models import AuditLog, Function, FunctionFile, FunctionStatus, User
from security import get_current_user

router = APIRouter(prefix="/functions", tags=["functions"])

ALLOWED_FILENAMES = {"main.py", "requirements.txt"}


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
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only .py files are accepted")

    func = Function(
        user_id=current_user.id,
        name=name,
        status=FunctionStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    db.add(func)
    db.flush()

    storage_dir = Path(settings.storage_path) / str(current_user.id) / str(func.id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for upload, target_name in [(file, "main.py"), (requirements, "requirements.txt")]:
        if upload is None:
            continue
        content = await upload.read()
        if len(content) > settings.max_file_size_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 10MB)")
        dest = storage_dir / target_name
        dest.write_bytes(content)
        db.add(FunctionFile(function_id=func.id, filename=target_name, storage_path=str(dest)))
        saved_files.append(target_name)

    db.add(AuditLog(
        user_id=current_user.id,
        action="FUNCTION_UPLOAD",
        details=f"function_id={func.id} name={name} files={saved_files}",
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
