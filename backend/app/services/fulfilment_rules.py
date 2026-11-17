"""
Fulfilment rules (Phase 9 M5) - the one place that says how an order may move.

An administrator can only walk a PAID order forward along

    confirmed -> processing -> shipped -> delivered

one step at a time. Anything else is refused: skipping a step, going back,
touching an unpaid / cancelled / expired / refunded order. Cancelling,
refunding and marking an order paid are NOT admin actions at all (payment
state comes from the gateway; cancellation and expiry belong to the customer
and the expiry job), so no function here can produce those statuses.

"Paid" means payment_status = paid AND inventory_state = consumed - the exact
pair the payment flow leaves behind - so a half-written order is never shipped.
"""

from typing import Optional

from app.models import OrderInventoryState, OrderPaymentStatus, OrderStatus

NEXT_STEP = {
    OrderStatus.CONFIRMED: OrderStatus.PROCESSING,
    OrderStatus.PROCESSING: OrderStatus.SHIPPED,
    OrderStatus.SHIPPED: OrderStatus.DELIVERED,
}

FULFILMENT_TARGETS = (OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED)

_ORDER = (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED)


def _is_paid(payment_status: OrderPaymentStatus, inventory_state: OrderInventoryState) -> bool:
    return payment_status == OrderPaymentStatus.PAID and inventory_state == OrderInventoryState.CONSUMED


def next_status(
    status: OrderStatus, payment_status: OrderPaymentStatus, inventory_state: OrderInventoryState
) -> Optional[OrderStatus]:
    """The only status an admin may set now, or None."""
    if not _is_paid(payment_status, inventory_state):
        return None
    return NEXT_STEP.get(status)


def is_fulfillable(status: OrderStatus, payment_status: OrderPaymentStatus, inventory_state: OrderInventoryState) -> bool:
    return next_status(status, payment_status, inventory_state) is not None


def on_fulfilment_path(
    status: OrderStatus, payment_status: OrderPaymentStatus, inventory_state: OrderInventoryState
) -> bool:
    """A paid order at any fulfilment step, delivered included."""
    return _is_paid(payment_status, inventory_state) and status in _ORDER


def refusal_reason(
    status: OrderStatus,
    payment_status: OrderPaymentStatus,
    inventory_state: OrderInventoryState,
    target: OrderStatus,
) -> str:
    """Why `target` cannot be set now (shown to the admin in a 409)."""
    if status == OrderStatus.CANCELLED:
        return "This order is cancelled, so it cannot be fulfilled."
    if status == OrderStatus.REFUNDED:
        return "This order is refunded, so it cannot be fulfilled."
    if not _is_paid(payment_status, inventory_state) or status not in _ORDER:
        return "This order has not been paid, so it cannot be fulfilled yet."
    if status == OrderStatus.DELIVERED:
        return "This order is already delivered; there is no further step."
    if target in _ORDER and _ORDER.index(target) <= _ORDER.index(status):
        return f"An order cannot move backward: it is {status.value}, not {target.value}."
    return f"The next step after {status.value} is {NEXT_STEP[status].value}."
