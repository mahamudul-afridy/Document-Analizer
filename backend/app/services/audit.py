"""Audit logging helper. Call inside the request's transaction so the log commits with the change."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User


def audit(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    entity_type: str | None = None,
    entity_id: object | None = None,
    request: Request | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            ip=(request.client.host if request and request.client else None),
            user_agent=(request.headers.get("user-agent", "")[:255] if request else None),
            details=details or {},
        )
    )
