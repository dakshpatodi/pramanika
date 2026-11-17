"""Read access to the admin audit trail (Phase 9). Writing goes through
`AuditService` so every write is in the caller's transaction."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdminAuditEvent


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_events(
        self,
        *,
        page: int,
        page_size: int,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
    ) -> Tuple[List[AdminAuditEvent], int]:
        """Newest first (ties broken by id so paging is stable). One count query
        and one page query - never the whole table."""
        conditions = []
        if entity_type:
            conditions.append(AdminAuditEvent.entity_type == entity_type)
        if entity_id:
            conditions.append(AdminAuditEvent.entity_id == entity_id)
        if action:
            conditions.append(AdminAuditEvent.action == action)

        total = self.db.execute(select(func.count()).select_from(AdminAuditEvent).where(*conditions)).scalar_one()
        rows = (
            self.db.execute(
                select(AdminAuditEvent)
                .where(*conditions)
                .order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(rows), total
