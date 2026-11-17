"""Admin order endpoints (Phase 9 M5). Two reads and ONE write: a fulfilment
step. There is no cancel, refund, mark-paid or edit endpoint by design."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database.session import get_db
from app.models import OrderInventoryState, OrderPaymentStatus, OrderStatus, User
from app.schemas.admin_catalog import SortOrder
from app.schemas.admin_orders import AdminOrderDetail, AdminOrderListResponse, AdminOrderSort, OrderStatusUpdate
from app.schemas.common import APIResponse
from app.services.admin_order_service import AdminOrderService

router = APIRouter(prefix="/orders", tags=["Admin - Orders"])
MAX_PAGE_SIZE = 100


def _service(db: Session = Depends(get_db)) -> AdminOrderService:
    return AdminOrderService(db)


@router.get("", response_model=APIResponse[AdminOrderListResponse], summary="All orders, newest first; filter, search, sort and page")
def list_orders(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    status: Optional[OrderStatus] = Query(None),
    payment_status: Optional[OrderPaymentStatus] = Query(None),
    inventory_state: Optional[OrderInventoryState] = Query(None),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Order number, customer name/email/phone, or shipping name/phone"),
    created_from: Optional[datetime] = Query(None, description="Placed at or after (ISO 8601)"),
    created_to: Optional[datetime] = Query(None, description="Placed at or before (ISO 8601)"),
    sort: AdminOrderSort = Query(AdminOrderSort.CREATED_AT),
    order: SortOrder = Query(SortOrder.DESC),
    service: AdminOrderService = Depends(_service),
):
    data = service.list(
        status=status, payment_status=payment_status, inventory_state=inventory_state, search=search,
        created_from=created_from, created_to=created_to, sort=sort, order=order, page=page, page_size=page_size,
    )
    return APIResponse(success=True, message="OK", data=data)


@router.get("/{order_id}", response_model=APIResponse[AdminOrderDetail], summary="One order in full: customer, lines, totals, address, payment attempts")
def get_order(order_id: uuid.UUID, service: AdminOrderService = Depends(_service)):
    return APIResponse(success=True, message="OK", data=service.get(order_id))


@router.post(
    "/{order_id}/status",
    response_model=APIResponse[AdminOrderDetail],
    summary="Move a paid order one step forward: processing, then shipped, then delivered",
)
def advance_order(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    admin: User = Depends(require_admin),
    service: AdminOrderService = Depends(_service),
):
    return APIResponse(success=True, message="Order updated.", data=service.advance(admin, order_id, payload))
