"""
Payment state rules (pure - no database, no Razorpay).

One Payment row is one Razorpay order. Its status only moves along the arrows
below, and every writer (verification, webhook, expiry) must ask
`can_transition` first, so a late or duplicate event can never put a row
into an impossible state.

    INITIATED --> AUTHORIZED --> CAPTURED --> REFUNDED
        |   \\          |            ^
        |    \\         v            |
        |     +----> FAILED -------+   (a retry or a late success can still capture)
        |     +----> EXPIRED ------+   (money taken after the order closed:
        v                                recorded as captured + refund_required)
     CAPTURED

Rules worth stating plainly:
  * CAPTURED is the only state that pays an order, and nothing moves a row
    OUT of it except to REFUNDED. A late FAILED or EXPIRED event for a
    captured payment is ignored - money that arrived is never "un-paid".
  * FAILED and EXPIRED are NOT final: Razorpay may still capture a payment
    on that Razorpay order later (a second tab, a slow bank). Real money is
    the truth, so FAILED/EXPIRED --> CAPTURED is allowed.
  * Whether a captured payment PAYS the order or is flagged for refund is
    decided from the ORDER's state (see `PaymentService`), not from here.
"""

import enum
from datetime import datetime
from typing import Dict, FrozenSet, Optional

from app.models import (
        OrderCancellationReason,
        OrderInventoryState,
        OrderPaymentStatus,
        OrderStatus,
        PaymentTransactionStatus as S,
    )

ALLOWED_TRANSITIONS: Dict[S, FrozenSet[S]] = {
    S.INITIATED: frozenset({S.AUTHORIZED, S.CAPTURED, S.FAILED, S.EXPIRED}),
    S.AUTHORIZED: frozenset({S.CAPTURED, S.FAILED, S.EXPIRED}),
    S.FAILED: frozenset({S.CAPTURED}),
    S.EXPIRED: frozenset({S.CAPTURED}),
    S.CAPTURED: frozenset({S.REFUNDED}),
    S.REFUNDED: frozenset(),
}

OPEN_STATUSES: FrozenSet[S] = frozenset({S.INITIATED, S.AUTHORIZED})
"""A customer may still be paying: at most one such row per order (DB-enforced)."""

PAID_STATUSES: FrozenSet[S] = frozenset({S.CAPTURED, S.REFUNDED})
"""Money was taken. `paid_at` is set exactly for these (DB-enforced)."""


def can_transition(current: S, new: S) -> bool:
    """True if moving from `current` to `new` is a legal step. Staying in
    the same state is NOT a transition - callers treat it as "already done"."""
    return new in ALLOWED_TRANSITIONS[current]


def is_open(status: S) -> bool:
    return status in OPEN_STATUSES


def is_paid(status: S) -> bool:
    return status in PAID_STATUSES


# --- may this ORDER be paid right now? ------------------------------------


class PaymentBlock(str, enum.Enum):
    """Why an order cannot be paid. None of these is ever "retry later" -
    the customer must act (or the order is simply gone)."""

    ALREADY_PAID = "already_paid"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOT_PAYABLE = "not_payable"  # some other state (confirmed, shipped, refunded...)
    STOCK_NOT_HELD = "stock_not_held"
    NOTHING_TO_PAY = "nothing_to_pay"


def payment_block(order, now: datetime) -> Optional[PaymentBlock]:
    """None if `order` may start a payment, else the first reason it may not.

    Duck-typed on the order's columns so it stays pure and easy to test.
    The checks run from "most useful for the customer to be told" to
    "least", so e.g. a cancelled order says "cancelled", not "no stock".
    """
    if order.payment_status == OrderPaymentStatus.PAID:
        return PaymentBlock.ALREADY_PAID
    if order.status == OrderStatus.CANCELLED:
        return (
            PaymentBlock.EXPIRED
            if order.cancellation_reason == OrderCancellationReason.EXPIRED
            else PaymentBlock.CANCELLED
        )
    # Only a pending order with a pending payment can be paid. A failed
    # ATTEMPT leaves the order's payment_status PENDING (so it can be
    # retried and can still expire), so this does not block retries.
    if order.status != OrderStatus.PENDING or order.payment_status != OrderPaymentStatus.PENDING:
        return PaymentBlock.NOT_PAYABLE
    if order.inventory_state != OrderInventoryState.RESERVED:
        return PaymentBlock.STOCK_NOT_HELD
    if order.expires_at is not None and order.expires_at <= now:
        # Past its deadline but the expiry job has not run yet: already
        # unpayable, exactly as it will be a moment from now.
        return PaymentBlock.EXPIRED
    if order.total_amount is None or order.total_amount <= 0:
        return PaymentBlock.NOTHING_TO_PAY
    return None


# --- money has arrived: does it PAY the order, or is it flagged for refund? -----


class CaptureDisposition(str, enum.Enum):
    PAYS_ORDER = "pays_order"
    REFUND_REQUIRED = "refund_required"


def capture_disposition(order) -> CaptureDisposition:
    """What a CAPTURED payment means for `order`, decided from the ORDER's state.

    It pays the order only if the order is still alive: pending, unpaid, and
    still holding its stock. Anything else - cancelled by the customer, expired,
    stock already given back, or already paid by another payment - means the
    money cannot buy this order, and is recorded with `refund_required`. The
    order is never revived: its stock may already belong to someone else.

    (An order that is past its `expires_at` but has not been expired by the
    background job yet is still alive: the customer did pay within the window
    they were given, and the stock is still held.)
    """
    alive = (
        order.status == OrderStatus.PENDING
        and order.payment_status == OrderPaymentStatus.PENDING
        and order.inventory_state == OrderInventoryState.RESERVED
    )
    return CaptureDisposition.PAYS_ORDER if alive else CaptureDisposition.REFUND_REQUIRED
