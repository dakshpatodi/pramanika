"""
Money has been captured for a payment: what does that mean for its order?

Shared by the two writers that can learn about a capture - the customer's
browser (`PaymentService.verify_payment`, M5) and Razorpay's own webhook
(`PaymentWebhookService`, M7) - so they cannot disagree:

  * the payment becomes CAPTURED (through `payment_state.transition`);
  * if the order is still alive it is marked paid and its reservation is
    CONSUMED (the units are sold, the coupon use stays);
  * if it is not (cancelled, expired, stock already given back, already paid
    by another payment) the payment is flagged `refund_required` and the
    order and its stock are left exactly as they were - the order is never
    revived, because its stock may already belong to someone else.

The caller holds the order lock (and the payment lock) and owns the
transaction; nothing here commits.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Order, Payment, PaymentTransactionStatus
from app.repositories.order_repository import OrderRepository
from app.services.payment_rules import CaptureDisposition, capture_disposition
from app.services.payment_state import transition
from app.services.reservation_service import ReservationInvariantError, ReservationService

logger = logging.getLogger(__name__)


def apply_capture(
    db: Session,
    order: Order,
    payment: Payment,
    *,
    payment_id: str,
    signature: Optional[str],
    now: datetime,
) -> CaptureDisposition:
    """Record the capture and settle the order. Returns what happened to it.

    Raises `IllegalPaymentTransitionError` if the payment cannot be captured
    from where it is (callers return earlier for already-paid payments), and
    `ReservationInvariantError` if the books do not balance - either one rolls
    the caller's whole transaction back.
    """
    transition(
        payment,
        PaymentTransactionStatus.CAPTURED,
        now=now,
        gateway_payment_id=payment_id,
        gateway_signature=signature,
    )

    if capture_disposition(order) is CaptureDisposition.REFUND_REQUIRED:
        payment.refund_required = True
        db.flush()
        logger.warning(
            "Payment %s was captured for order %s, which is %s/%s/%s: recorded and flagged for refund",
            payment_id, order.id, order.status.value, order.payment_status.value, order.inventory_state.value,
        )
        return CaptureDisposition.REFUND_REQUIRED

    # Pay the order and turn its reservation into sold stock. Both gates are
    # compare-and-set, and we hold the order lock, so each can only succeed
    # here; a failure means the books are wrong and the whole thing rolls back.
    # A failure below means the books are wrong while the customer's money WAS captured at
    # Razorpay. The transaction rolls back (so no half state is stored), the caller answers 5xx
    # (Razorpay retries the webhook for ~24h), and this line is the alert: someone must look.
    if not OrderRepository(db).mark_paid(order.id):
        logger.critical("CAPTURED MONEY NOT RECORDED: order %s could not be marked paid (payment %s)", order.id, payment_id)
        raise ReservationInvariantError(f"order {order.id} could not be marked paid")
    if not ReservationService(db).consume_for_order(order):
        logger.critical("CAPTURED MONEY NOT RECORDED: order %s had no reservation to consume (payment %s)", order.id, payment_id)
        raise ReservationInvariantError(f"order {order.id} had no reservation to consume")
    db.flush()
    db.refresh(order, ["status", "payment_status", "inventory_state"])
    logger.info("Order %s paid by payment %s", order.id, payment_id)
    return CaptureDisposition.PAYS_ORDER
