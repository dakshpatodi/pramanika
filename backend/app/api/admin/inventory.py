"""Admin inventory endpoints (Phase 9 M4). Reads are side-effect free. There is
no endpoint that writes `reserved_quantity`: reservations belong to checkout."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database.session import get_db
from app.models import User
from app.schemas.admin_catalog import SortOrder, StockFilter
from app.schemas.admin_inventory import (
    AdminInventoryDetail,
    AdminInventoryListResponse,
    InventorySortKey,
    InventoryUpdate,
)
from app.schemas.common import APIResponse
from app.services.admin_inventory_service import AdminInventoryService

router = APIRouter(prefix="/inventory", tags=["Admin - Inventory"])
MAX_PAGE_SIZE = 100


def _service(db: Session = Depends(get_db)) -> AdminInventoryService:
    return AdminInventoryService(db)


@router.get(
    "",
    response_model=APIResponse[AdminInventoryListResponse],
    summary="Stock levels; use stock=low or stock=out for the low-stock and out-of-stock lists",
)
def list_inventory(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Name, SKU or slug"),
    category_id: Optional[uuid.UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    stock: Optional[StockFilter] = Query(None, description="ok = above the threshold, low, out"),
    sort: InventorySortKey = Query(InventorySortKey.NAME),
    order: SortOrder = Query(SortOrder.ASC),
    service: AdminInventoryService = Depends(_service),
):
    data = service.list(
        search=search, category_id=category_id, is_active=is_active, stock=stock,
        sort=sort, order=order, page=page, page_size=page_size,
    )
    return APIResponse(success=True, message="OK", data=data)


@router.get("/{product_id}", response_model=APIResponse[AdminInventoryDetail], summary="One product's stock and what reserves it")
def get_inventory(product_id: uuid.UUID, service: AdminInventoryService = Depends(_service)):
    return APIResponse(success=True, message="OK", data=service.get(product_id))


@router.patch(
    "/{product_id}",
    response_model=APIResponse[AdminInventoryDetail],
    summary="Set stock (with expected_quantity), adjust it by +/-n, and/or change the low-stock threshold",
)
def update_inventory(
    product_id: uuid.UUID,
    payload: InventoryUpdate,
    admin: User = Depends(require_admin),
    service: AdminInventoryService = Depends(_service),
):
    return APIResponse(success=True, message="Stock updated.", data=service.update(admin, product_id, payload))
