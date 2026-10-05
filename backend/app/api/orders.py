"""
Order endpoints.

Every route depends on `get_current_active_user`, and every order lookup is
scoped to that user, so nobody can read or cancel another customer's order
(it simply looks like it does not exist).

    POST  /api/orders                     place an order from the current cart
    GET   /api/orders                     order history, newest first (paginated)
    GET   /api/orders/{order_id}          one order
    POST  /api/orders/{order_id}/cancel   cancel an unpaid order

POST /api/orders needs an `Idempotency-Key` header (8-64 characters; a UUID
is ideal). Re-sending the same key with the same body returns the original
order (200) instead of creating another; the first request returns 201.
The client sends only the delivery address id (and optionally the total it
was shown) - prices, items and discounts always come from the server-side
cart. Nothing here takes payment: new orders are pending / unpaid.
"""

import uuid

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.order import CheckoutRequest, OrderListResponse, OrderResponse
from app.services.checkout_service import CheckoutService
from app.services.order_service import OrderService, to_order_response

router = APIRouter(prefix="/api/orders", tags=["Orders"])

MAX_PAGE_SIZE = 50


def get_checkout_service(db: Session = Depends(get_db)) -> CheckoutService:
    return CheckoutService(db)


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)


@router.post(
    "",
    response_model=APIResponse[OrderResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Place an order from the current cart (idempotent via the Idempotency-Key header)",
)
def place_order(
    payload: CheckoutRequest,
    response: Response,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        max_length=200,
        description="Unique per checkout attempt, 8-64 characters (letters, digits, . _ : -). A UUID works well.",
    ),
    current_user: User = Depends(get_current_active_user),
    service: CheckoutService = Depends(get_checkout_service),
) -> APIResponse[OrderResponse]:
    result = service.place_order(
        current_user.id,
        shipping_address_id=payload.shipping_address_id,
        idempotency_key=idempotency_key,
        expected_total=payload.expected_total,
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return APIResponse(
        success=True,
        message="Order placed." if result.created else "This order was already placed.",
        data=to_order_response(result.order),
    )


@router.get(
    "",
    response_model=APIResponse[OrderListResponse],
    summary="List the current user's orders, newest first",
)
def list_orders(
    page: int = Query(1, ge=1, description="Page number, starting at 1"),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description=f"Orders per page, max {MAX_PAGE_SIZE}"),
    current_user: User = Depends(get_current_active_user),
    service: OrderService = Depends(get_order_service),
) -> APIResponse[OrderListResponse]:
    return APIResponse(
        success=True,
        message="Orders retrieved.",
        data=service.list_orders(current_user.id, page=page, page_size=page_size),
    )


@router.get(
    "/{order_id}",
    response_model=APIResponse[OrderResponse],
    summary="Get one of the current user's orders",
)
def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: OrderService = Depends(get_order_service),
) -> APIResponse[OrderResponse]:
    return APIResponse(success=True, message="Order retrieved.", data=service.get_order(current_user.id, order_id))


@router.post(
    "/{order_id}/cancel",
    response_model=APIResponse[OrderResponse],
    summary="Cancel an unpaid order (releases its stock and coupon use; safe to repeat)",
)
def cancel_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: OrderService = Depends(get_order_service),
) -> APIResponse[OrderResponse]:
    return APIResponse(
        success=True,
        message="Order cancelled.",
        data=service.cancel_order(current_user.id, order_id),
    )