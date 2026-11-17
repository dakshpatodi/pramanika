"""
AdminAuditEvent ORM model (Phase 9).

An append-only record of what an administrator changed. A row is written in
the SAME transaction as the change it describes (see `AuditService`), so the
trail and the data can never disagree: both commit or both roll back.

The application never updates or deletes these rows. The admin account is
kept as an id (which becomes NULL if that user is ever deleted) AND as the
email it had at the time, so the trail still reads sensibly afterwards.
`before` / `after` hold only the fields that changed - never a password
hash, token or payment secret (the service refuses such keys).
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_events_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_admin_audit_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    admin_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    admin_email: Mapped[str] = mapped_column(String(255), nullable=False)

    action: Mapped[str] = mapped_column(String(60), nullable=False)
    """`<entity>.<verb>`, lower-case, e.g. `product.update`, `order.status_change`."""

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    after: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AdminAuditEvent {self.action} {self.entity_type}={self.entity_id}>"
