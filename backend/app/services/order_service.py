"""
Reading and cancelling orders (creating them is CheckoutService's job).

Every method takes the authenticated user's id; an order that belongs to
someone else is reported exactly like one that does not exist.

Cancelling (customer, unpaid orders only)
-----------------------------------------
Inside one transaction, in this lock order (the same order checkout uses,
so the two can never deadlock):

  1. the order row   - `cancel_pending`: ONE conditional UPDATE that flips
                       status -> cancelled and inventory_state -> released
                       only if the order is still pending, unpaid and still
                       holding its reservation. Exactly one caller can win it.
  2. the coupon      - the winner alone gives the coupon use back.
  3. the inventory   - the winner alone releases the reserved units
                       (ascending product id).

A second cancel (double click, retry, two tabs) finds the order already
cancelled and changes nothing: the call is idempotent and returns the
order. Anything that makes the order uncancellable (paid, shipped...)
is a 409. If any step fails the whole cancel is rolled back.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import OrderNotCancellableError, OrderNotFoundError
from app.core.money import money_to_float
from app.models import Order, OrderPaymentStatus, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import (
    OrderItemResponse,
    OrderListResponse,
    OrderResponse,
    OrderShippingAddressResponse,
    OrderSummaryResponse,
    OrderTotalsResponse,
)
from app.schemas.product import PaginationMeta
from app.services.coupon_usage import CouponUsageService
from app.services.order_rules import can_cancel
from app.services.reservation_service import ReservationService

SUMMARY_ITEM_NAMES = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_order_response(order: Order) -> OrderResponse:
    items = [
        OrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product_name_snapshot,
            sku=item.sku_snapshot,
            unit_price=money_to_float(item.unit_price),
            quantity=item.quantity,
            line_total=money_to_float(item.subtotal),
        )
        for item in order.items
    ]
    return OrderResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        can_cancel=can_cancel(order.status, order.payment_status),
        coupon_code=order.coupon_code,
        items=items,
        item_count=sum(i.quantity for i in items),
        totals=OrderTotalsResponse(
            subtotal=money_to_float(order.subtotal),
            discount=money_to_float(order.discount_amount),
            taxable_amount=money_to_float(order.taxable_amount),
            gst_rate=float(order.gst_rate),
            gst=money_to_float(order.tax_amount),
            delivery_charge=money_to_float(order.delivery_charge),
            total=money_to_float(order.total_amount),
        ),
        shipping_address=OrderShippingAddressResponse(
            full_name=order.shipping_full_name,
            phone_number=order.shipping_phone_number,
            address_line_1=order.shipping_address_line_1,
            address_line_2=order.shipping_address_line_2,
            city=order.shipping_city,
            state=order.shipping_state,
            postal_code=order.shipping_postal_code,
            country=order.shipping_country,
        ),
        created_at=order.created_at,
        cancelled_at=order.cancelled_at,
    )


def _to_summary(order: Order) -> OrderSummaryResponse:
    return OrderSummaryResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        total=money_to_float(order.total_amount),
        item_count=sum(i.quantity for i in order.items),
        item_names=[i.product_name_snapshot for i in order.items][:SUMMARY_ITEM_NAMES],
        created_at=order.created_at,
    )


class OrderService:
    def __init__(self, db: Session, *, clock: Optional[Callable[[], datetime]] = None):
        self.db = db
        self.orders = OrderRepository(db)
        self.reservations = ReservationService(db)
        self.coupon_usage = CouponUsageService(db)
        self.clock = clock or _utcnow

    # --- reads --------------------------------------------------------------

    def list_orders(self, user_id: uuid.UUID, *, page: int, page_size: int) -> OrderListResponse:
        orders, total = self.orders.list_for_user(user_id, page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return OrderListResponse(
            orders=[_to_summary(o) for o in orders],
            pagination=PaginationMeta(
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    def get_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> OrderResponse:
        """Raises OrderNotFoundError for an unknown id OR someone else's order."""
        order = self.orders.get_for_user(order_id, user_id)
        if order is None:
            raise OrderNotFoundError()
        return to_order_response(order)

    # --- cancel -------------------------------------------------------------

    def cancel_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> OrderResponse:
        """Cancel an unpaid order, release its stock and give back its
        coupon use - each exactly once, however many times or however
        concurrently this is called.

        Raises:
            OrderNotFoundError: unknown id or not this user's order.
            OrderNotCancellableError: paid, shipped, delivered, refunded...
        """
        with self._transaction():
            order = self.orders.get_for_user(order_id, user_id)
            if order is None:
                raise OrderNotFoundError()

            if order.status != OrderStatus.CANCELLED:
                if not can_cancel(order.status, order.payment_status):
                    raise OrderNotCancellableError(self._describe(order))

                if self.orders.cancel_pending(order.id, self.clock()):
                    # We won the gate: only we restore the coupon and release stock.
                    if order.coupon_id is not None:
                        self.coupon_usage.restore(order.coupon_id)
                    self.reservations.release_items(order)
                else:
                    # Lost a race (another cancel, or a payment landing). Look again.
                    order = self.orders.get_for_user(order_id, user_id, for_update=True)
                    if order.status != OrderStatus.CANCELLED:
                        raise OrderNotCancellableError(self._describe(order))

        # Committed: return a fresh copy.
        return self.get_order(user_id, order_id)

    # --- internals ----------------------------------------------------------

    @staticmethod
    def _describe(order: Order) -> str:
        if order.status == OrderStatus.PENDING and order.payment_status != OrderPaymentStatus.PENDING:
            return order.payment_status.value
        return order.status.value

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise