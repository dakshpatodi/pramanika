"""
The ONE place a Payment's status is changed.

Every writer - verification (M5), customer cancel (M6), the webhook (M7) and
the expiry job (M8) - goes through `transition`, so the rules in
`payment_rules.ALLOWED_TRANSITIONS` cannot be bypassed by a late or duplicate
event, and no writer can forget to keep `paid_at` / `failure_reason` in step
with the status (the database also has CHECKs for the first of those).

The behaviour that matters most:
  * CAPTURED is terminal apart from REFUNDED: nothing - not a late "failed"
    webhook, not an order cancel, not the expiry job - can move it back.
  * moving to the status a payment already has is a quiet no-op (False), so
    a re-delivered event is harmless;
  * any other illegal move raises: it is a bug, never something to guess at.

Nothing here commits; the caller owns the transaction.
"""

import uuid
from datetime import datetime
from typing import Optional

from app.models import Payment, PaymentTransactionStatus as S
from app.repositories.payment_repository import PaymentRepository
from app.services.payment_rules import can_transition

MAX_FAILURE_REASON = 500

REASON_ORDER_CANCELLED = "The order was cancelled before it was paid."
REASON_ORDER_EXPIRED = "The order expired before it was paid."


class IllegalPaymentTransitionError(RuntimeError):
    """A writer tried a move the state machine forbids. Never expected in
    production; raising rolls the whole transaction back instead of storing
    an impossible state."""


def transition(
    payment: Payment,
    new: S,
    *,
    now: Optional[datetime] = None,
    gateway_payment_id: Optional[str] = None,
    gateway_signature: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> bool:
    """Move `payment` to `new`. True if it moved, False if it was already
    there. Raises `IllegalPaymentTransitionError` for a forbidden move.

    CAPTURED needs `now` and `gateway_payment_id` (that is what "money was
    taken" means) and clears any earlier failure reason; FAILED / EXPIRED
    keep `failure_reason`; AUTHORIZED records the payment id if given.
    """
    current = payment.status
    if current == new:
        return False
    if not can_transition(current, new):
        raise IllegalPaymentTransitionError(f"payment {payment.id}: {current.value} -> {new.value} is not allowed")

    if new == S.CAPTURED:
        if now is None or not gateway_payment_id:
            raise ValueError("capturing a payment needs the time and the Razorpay payment id")
        payment.paid_at = now
        payment.failure_reason = None
    elif new in (S.FAILED, S.EXPIRED):
        payment.failure_reason = failure_reason[:MAX_FAILURE_REASON] if failure_reason else None

    if gateway_payment_id:
        payment.gateway_payment_id = gateway_payment_id
    if gateway_signature:
        payment.gateway_signature = gateway_signature
    payment.status = new
    return True


def close_open_payments(payments: PaymentRepository, order_id: uuid.UUID, *, reason: str) -> int:
    """The order is closed (cancelled or expired): no attempt on it is payable
    any more. Every open (initiated / authorized) payment becomes EXPIRED and
    remembers why. Returns how many were closed.

    The rows are locked first, so a verification or webhook that is capturing
    one of them right now finishes before this looks. A payment that was
    already CAPTURED is never open and is never touched. If the customer still
    pays at Razorpay afterwards (a popup left open), that capture is recorded
    as a late payment and flagged for refund - EXPIRED -> CAPTURED is allowed
    exactly for that.
    """
    closed = 0
    for payment in payments.list_open_for_order(order_id, for_update=True):
        if transition(payment, S.EXPIRED, failure_reason=reason):
            closed += 1
    payments.db.flush()
    return closed
