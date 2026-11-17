"""Read-only view of the admin audit trail (Phase 9)."""

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.audit_repository import AuditRepository
from app.schemas.admin import AuditEventListResponse, AuditEventResponse
from app.schemas.common import APIResponse
from app.schemas.product import PaginationMeta

router = APIRouter(tags=["Admin"])

MAX_PAGE_SIZE = 50


@router.get(
    "/audit-events",
    response_model=APIResponse[AuditEventListResponse],
    summary="Recent administrator changes, newest first",
)
def list_audit_events(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    entity_type: Optional[str] = Query(None, min_length=1, max_length=40, pattern=r"^[a-z_]+$"),
    entity_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None, min_length=3, max_length=60, pattern=r"^[a-z_]+\.[a-z_]+$"),
    db: Session = Depends(get_db),
) -> APIResponse[AuditEventListResponse]:
    events, total = AuditRepository(db).list_events(
        page=page, page_size=page_size, entity_type=entity_type, entity_id=entity_id, action=action
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return APIResponse(
        success=True,
        message="OK",
        data=AuditEventListResponse(
            events=[AuditEventResponse.model_validate(e) for e in events],
            pagination=PaginationMeta(
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        ),
    )
