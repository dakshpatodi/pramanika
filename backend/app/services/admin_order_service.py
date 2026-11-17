"""
Admin order management (Phase 9 M5): view orders, and move PAID orders forward
through fulfilment. See `fulfilment_rules` for the rules.

What this service never does: change payment status, touch stock, restore a
coupon, cancel, refund or edit an order. The one write is a conditional UPDATE
of `status` under the order's row lock - the same lock the payment and expiry
paths take - plus one audit row in the same transaction. Repeating the step an
order is already at is a quiet success (no second audit row), so a double click
or two admins pressing the same button do no harm.
"""

import math
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import AdminConflictError, AdminValidationError, OrderNotFoundError
from app.models import Order, OrderInventoryState, OrderPaymentStatus, OrderStatus, User
from app.repositories.admin_orders_repository import AdminOrdersRepository
from app.schemas.admin_catalog import SortOrder
from app.schemas.admin_orders import (
    AdminCustomer,
    AdminOrderDetail,
    AdminOrderLine,
    AdminOrderListItem,
    AdminOrderListResponse,
    AdminOrderSort,
    AdminOrderTotals,
    AdminPaymentAttempt,
    AdminShippingAddress,
    FulfilmentTarget,
    OrderStatusUpdate,
)
from app.schemas.product import PaginationMeta
from app.services.admin_common import admin_transaction
from app.services.audit_service import AuditService
from app.services.fulfilment_rules import next_status, on_fulfilment_path, refusal_reason


def _next(order: Order) -> Optional[FulfilmentTarget]:
    step = next_status(order.status, order.payment_status, order.inventory_state)
    return FulfilmentTarget(step.value) if step is not None else None


class AdminOrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminOrdersRepository(db)
        self.audit = AuditService(db)

    # ---- reads
    def list(
        self, *, status, payment_status, inventory_state, search, created_from, created_to,
        sort: AdminOrderSort, order: SortOrder, page: int, page_size: int,
    ) -> AdminOrderListResponse:
        if created_from is not None and created_to is not None and created_to < created_from:
            raise AdminValidationError("created_to: must not be before created_from.")
        rows, total = self.repository.list(
            status=status, payment_status=payment_status, inventory_state=inventory_state, search=search,
            created_from=created_from, created_to=created_to, sort=sort, order=order, page=page, page_size=page_size,
        )
        pages = math.ceil(total / page_size) if total else 0
        return AdminOrderListResponse(
            orders=[
                AdminOrderListItem(
                    id=o.id, order_number=o.order_number, status=o.status, payment_status=o.payment_status,
                    inventory_state=o.inventory_state, cancellation_reason=o.cancellation_reason,
                    customer_name=f"{u.first_name} {u.last_name}".strip(), customer_email=u.email,
                    customer_phone=u.phone_number, item_count=units, total_amount=float(o.total_amount),
                    next_status=_next(o), created_at=o.created_at,
                )
                for o, u, units in rows
            ],
            pagination=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=pages,
                has_next=page < pages, has_previous=page > 1,
            ),
        )

    def get(self, order_id: uuid.UUID) -> AdminOrderDetail:
        order = self.repository.get_detail(order_id)
        if order is None:
            raise OrderNotFoundError()
        return self._detail(order)

    # ---- the one write
    def advance(self, admin: User, order_id: uuid.UUID, payload: OrderStatusUpdate) -> AdminOrderDetail:
        target = OrderStatus(payload.status.value)
        with admin_transaction(self.db):
            order = self.repository.lock(order_id)
            if order is None:
                raise OrderNotFoundError()
            state = (order.status, order.payment_status, order.inventory_state)
            already_there = order.status == target and on_fulfilment_path(*state)
            if not already_there:
                if next_status(*state) != target:
                    raise AdminConflictError(refusal_reason(*state, target))
                if not self.repository.advance_status(order.id, order.status, target):
                    raise AdminConflictError("This order changed while you were updating it. Refresh and try again.")
                after = {"status": target.value}
                if payload.note:
                    after["note"] = payload.note
                self.audit.record(
                    admin=admin, action="order.status_change", entity_type="order", entity_id=order.id,
                    before={"status": order.status.value}, after=after,
                )
        return self.get(order_id)

    # ---- helpers
    def _detail(self, order: Order) -> AdminOrderDetail:
        user = order.user
        units = sum(item.quantity for item in order.items)
        gst = float(order.tax_amount)
        step = _next(order)
        return AdminOrderDetail(
            id=order.id, order_number=order.order_number, status=order.status, payment_status=order.payment_status,
            inventory_state=order.inventory_state, cancellation_reason=order.cancellation_reason,
            customer=AdminCustomer(
                id=user.id, name=f"{user.first_name} {user.last_name}".strip(), email=user.email,
                phone_number=user.phone_number,
            ),
            coupon_code=order.coupon_code,
            items=[
                AdminOrderLine(
                    product_id=i.product_id, name=i.product_name_snapshot, sku=i.sku_snapshot,
                    unit_price=float(i.unit_price), quantity=i.quantity, subtotal=float(i.subtotal),
                )
                for i in sorted(order.items, key=lambda i: (i.created_at, str(i.id)))
            ],
            item_count=units,
            totals=AdminOrderTotals(
                subtotal=float(order.subtotal), discount=float(order.discount_amount),
                taxable_amount=float(order.taxable_amount), gst_rate=float(order.gst_rate), gst=gst,
                delivery_charge=float(order.delivery_charge), total=float(order.total_amount),
            ),
            shipping_address=AdminShippingAddress(
                full_name=order.shipping_full_name, phone_number=order.shipping_phone_number,
                address_line_1=order.shipping_address_line_1, address_line_2=order.shipping_address_line_2,
                city=order.shipping_city, state=order.shipping_state, postal_code=order.shipping_postal_code,
                country=order.shipping_country,
            ),
            payments=[
                AdminPaymentAttempt(
                    id=p.id, gateway=p.payment_gateway, gateway_order_id=p.gateway_order_id,
                    gateway_payment_id=p.gateway_payment_id, status=p.status.value, amount=float(p.amount),
                    currency=p.currency, failure_reason=p.failure_reason, refund_required=p.refund_required,
                    paid_at=p.paid_at, created_at=p.created_at,
                )
                for p in sorted(order.payments, key=lambda p: (p.created_at, str(p.id)))
            ],
            reserved_units=units if order.inventory_state == OrderInventoryState.RESERVED else 0,
            next_status=step, can_advance=step is not None, expires_at=order.expires_at,
            created_at=order.created_at, cancelled_at=order.cancelled_at, updated_at=order.updated_at,
        )
