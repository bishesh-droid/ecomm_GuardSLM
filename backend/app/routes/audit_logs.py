from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ActivityLog, User
from ..permissions import require_admin

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("")
def audit_logs(decision: str | None = Query(None, pattern="^(ALLOW|BLOCK|ASK)$"), action: str | None = None,
               limit: int = Query(100, le=500), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(ActivityLog).order_by(ActivityLog.id.desc()).limit(limit)
    if decision:
        stmt = stmt.where(ActivityLog.decision == decision)
    if action:
        stmt = stmt.where(ActivityLog.action.like(f"{action}%"))
    return [{"id": l.id, "actor_id": l.actor_id, "actor_role": l.actor_role, "action": l.action, "entity_type": l.entity_type,
             "entity_id": l.entity_id, "decision": l.decision, "detail": l.detail, "created_at": l.created_at.isoformat()}
            for l in db.scalars(stmt)]
