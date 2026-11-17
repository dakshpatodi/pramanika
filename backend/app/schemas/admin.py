"""Admin API schemas (Phase 9). Response-only here; every admin write body
added later uses `extra="forbid"`."""

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.product import PaginationMeta


class AdminMeResponse(BaseModel):
    """Who the server believes the caller is - read from the database, not the token."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    role: str


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_user_id: Optional[uuid.UUID]
    admin_email: str
    action: str
    entity_type: str
    entity_id: Optional[uuid.UUID]
    before: Optional[dict[str, Any]]
    after: Optional[dict[str, Any]]
    created_at: datetime


class AuditEventListResponse(BaseModel):
    events: List[AuditEventResponse]
    pagination: PaginationMeta
