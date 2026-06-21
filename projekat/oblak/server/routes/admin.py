from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models import AuditLog, User
from security import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    action: str
    details: str | None
    timestamp: datetime

    model_config = {"from_attributes": True}


@router.get("/audit", response_model=list[AuditLogResponse])
def get_audit_log(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditLog]:
    """
    Lista audit log unosa. Samo admin korisnici.
    Logovi su append-only i ne mogu se brisati kroz API.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
