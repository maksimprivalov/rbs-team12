"""
Audit log pristup (revizija).

  GET /audit/      - SVI logovi, samo admin, sa filtrima i paginacijom
  GET /audit/me    - logovi trenutnog korisnika (svako vidi svoje)

Audit log je append-only (upisuje se kroz ceo sistem); ovde se samo čita.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from db import get_db
from models import AuditLog, User
from security import get_current_user, require_admin

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    action: str
    details: str | None
    timestamp: datetime


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditLogResponse]


def _serialize(logs: list[AuditLog]) -> list[AuditLogResponse]:
    return [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            username=log.user.username if log.user else None,
            action=log.action,
            details=log.details,
            timestamp=log.timestamp,
        )
        for log in logs
    ]


def _paginate(query, limit: int, offset: int) -> AuditLogPage:
    total = query.count()
    logs = query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()
    return AuditLogPage(total=total, limit=limit, offset=offset, items=_serialize(logs))


@router.get("/", response_model=AuditLogPage)
def list_all_audit_logs(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    user_id: int | None = Query(None, description="Filter po korisniku"),
    action: str | None = Query(None, description="Filter po akciji (npr. FUNCTION_INVOKE_DONE)"),
    function_id: int | None = Query(None, description="Filter po funkciji (traži u details)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AuditLogPage:
    """Svi audit logovi (admin). Najnoviji prvi."""
    query = db.query(AuditLog)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if function_id is not None:
        # details format: "function_id=<id> ..." -> izbegni da 5 hvata 50
        token = f"function_id={function_id}"
        query = query.filter(
            or_(AuditLog.details.like(f"%{token} %"), AuditLog.details.like(f"%{token}"))
        )
    return _paginate(query, limit, offset)


@router.get("/me", response_model=AuditLogPage)
def my_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    action: str | None = Query(None, description="Filter po akciji"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AuditLogPage:
    """Audit logovi trenutnog korisnika. Najnoviji prvi."""
    query = db.query(AuditLog).filter(AuditLog.user_id == current_user.id)
    if action:
        query = query.filter(AuditLog.action == action)
    return _paginate(query, limit, offset)
