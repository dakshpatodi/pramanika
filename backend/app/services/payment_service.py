"""
Starting a payment: turning a pending Pramanika order into a Razorpay order.

    create_razorpay_order(user_id, order_id)   (M3)
    verify_payment(user_id, order_id, ...)     (M5, see "Verifying" at the bottom of this docstring)

The amount is NEVER taken from the request. It is `order.total_amount`
read from the database inside the transaction, converted to paise with
`to_paise` (exact Decimal arithmetic - Rs 406.21 -> 40621).

One transaction, in this order:

  1. lock the order row (`SELECT ... FOR UPDATE`), scoped to its owner.
     Someone else's order looks exactly like a missing one.
  2. refuse unless the order is payable (`payment_rules.payment_block`):
     paid, cancelled, expired, stock no longer held, nothing to pay.
  3. if the order already has an open payment, hand that one back -
     idempotent: ten clicks, two tabs or a retried request still mean ONE
     Razorpay order.
  4. otherwise create the Razorpay order and store a Payment row
     (INITIATED) pointing at it, then commit.

The row lock in step 1 is what stops two simultaneous requests from both
reaching step 4: the second waits, then finds the first one's payment in
step 3. The price of that is that the lock is held during the Razorpay
call - at most the gateway timeout (10 s by default) - and it only ever
delays other requests for THE SAME order (cancel, pay, expire), never
other customers. If the commit fails after Razorpay accepted the order,
that Razorpay order is simply never used (an unpaid Razorpay order costs
nothing and can never be charged without our Checkout opening it).

Backstops, because "should be impossible" deserves a second line of
defence: the database's partial unique index allows only one open
payment per order, and an IntegrityError at insert time is answered by
re-reading and returning the winner's payment.

Verifying (M5)
--------------
The browser reports "I paid" with three values. Nothing it says is trusted:

  1. the HMAC signature is checked (no database, no network) - a wrong one
     is rejected before anything else happens;
  2. the order row is locked, then this order's payment row for that
     Razorpay order id (an id from some other order is simply not found);
  3. a payment that is already recorded as captured is answered from the
     database (idempotent - repeating costs nothing and changes nothing);
  4. otherwise Razorpay is ASKED about the payment (id, order, amount and
     currency must match what we stored, and its status decides):
        captured   -> the money is ours
        authorized -> not taken yet; recorded, order stays unpaid
        anything else -> rejected
  5. captured money either PAYS the order (order -> confirmed/paid and its
     reservation is CONSUMED: the units are sold, the coupon use stays) or,
     if the order is no longer alive, is recorded with `refund_required`
     and the order is left exactly as it was (see `capture_disposition`).

All of it is one transaction; the order lock is held while Razorpay is asked
(bounded by the gateway timeout), which is also what keeps the expiry job
and a customer cancel from changing the order half-way through.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    LatePaymentError,
    OrderAlreadyPaidError,
    OrderNotFoundError,
    OrderNotPayableError,
    PaymentGatewayError,
    PaymentVerificationError,
    PaymentVerificationUnavailableError,
)
from app.core.money import to_money, to_paise
from app.models import Order, Payment, PaymentTransactionStatus
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.order import OrderResponse
from app.schemas.payment import PaymentIntentResponse
from app.services.order_service import to_order_response
from app.services.payment_rules import (
    CaptureDisposition,
    PaymentBlock,
    can_transition,
    is_paid,
    payment_block,
)
from app.services.payment_capture import apply_capture
from app.services.payment_state import transition
from app.services.razorpay_gateway import MAX_RECEIPT_LENGTH, PaymentGateway
from app.services.reservation_service import ReservationService

logger = logging.getLogger(__name__)

GATEWAY = "razorpay"
CURRENCY = "INR"

_BLOCK_MESSAGES = {
    PaymentBlock.CANCELLED: "This order was cancelled and can no longer be paid.",
    PaymentBlock.EXPIRED: "This order has expired and can no longer be paid. Please place a new order.",
    PaymentBlock.NOT_PAYABLE: "This order can no longer be paid.",
    PaymentBlock.STOCK_NOT_HELD: "This order can no longer be paid. Please place a new order.",
    PaymentBlock.NOTHING_TO_PAY: "There is nothing to pay on this order.",
}


@dataclass(frozen=True)
class PaymentIntentResult:
    intent: PaymentIntentResponse
    created: bool
    """True if a new Razorpay order was created, False if the order's
    existing open one was returned."""


class VerifyOutcome(str, enum.Enum):
    PAID = "paid"                      # this call paid the order
    ALREADY_PAID = "already_paid"      # a repeat of a payment already recorded
    PENDING_CAPTURE = "pending_capture"  # Razorpay has only authorized it; not paid yet
    LATE = "late"                      # money taken, order closed: flagged for refund


@dataclass(frozen=True)
class VerifyResult:
    order: OrderResponse
    outcome: VerifyOutcome


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_receipt(order: Order, attempt: int) -> str:
    """Razorpay's `receipt` (<= 40 chars): our order number plus the attempt
    number, so each Razorpay order for one Pramanika order is distinguishable
    in the Razorpay dashboard."""
    base = order.order_number or order.id.hex
    suffix = f"-{attempt}"
    return base[: MAX_RECEIPT_LENGTH - len(suffix)] + suffix


class PaymentService:
    def __init__(self, db: Session, gateway: PaymentGateway, *, clock: Callable[[], datetime] = _utcnow):
        self.db = db
        self.gateway = gateway
        self.clock = clock
        self.orders = OrderRepository(db)
        self.payments = PaymentRepository(db)
        self.reservations = ReservationService(db)

    def create_razorpay_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> PaymentIntentResult:
        try:
            result = self._create_razorpay_order(user_id, order_id)
            self.db.commit()
            return result
        except IntegrityError:
            # Someone else's payment for this order got in first (the order
            # lock should make that impossible; the unique index guarantees it).
            self.db.rollback()
            existing = self.payments.get_open_for_order(order_id)
            if existing is None:
                raise
            order = self.db.get(Order, order_id)
            logger.warning("Payment insert lost a race for order %s; returning the existing payment", order_id)
            result = PaymentIntentResult(intent=self._intent(order, existing), created=False)
            self.db.rollback()  # read-only from here; release the snapshot
            return result
        except BaseException:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------

    def _create_razorpay_order(self, user_id: uuid.UUID, order_id: uuid.UUID) -> PaymentIntentResult:
        order = self.orders.get_for_user(order_id, user_id, for_update=True)
        if order is None:
            raise OrderNotFoundError()

        block = payment_block(order, self.clock())
        if block is PaymentBlock.ALREADY_PAID:
            raise OrderAlreadyPaidError()
        if block is not None:
            raise OrderNotPayableError(_BLOCK_MESSAGES[block])
        if self.payments.has_captured(order.id):
            # Money is already recorded for this order (defensive: the
            # order's own payment_status normally says so too).
            raise OrderAlreadyPaidError()

        open_payment = self.payments.get_open_for_order(order.id)
        if open_payment is not None:
            return PaymentIntentResult(intent=self._intent(order, open_payment), created=False)

        amount = to_money(order.total_amount)
        try:
            amount_paise = to_paise(amount)
        except ValueError:
            raise OrderNotPayableError("This order's amount cannot be paid online.") from None

        attempt = self.payments.count_for_order(order.id) + 1
        gateway_order = self.gateway.create_order(
            amount_paise=amount_paise,
            currency=CURRENCY,
            receipt=build_receipt(order, attempt),
            # Identifiers only: no name, email, phone or address goes to Razorpay.
            notes={"pramanika_order_id": str(order.id), "order_number": order.order_number or ""},
        )

        payment = self.payments.add(
            Payment(
                order_id=order.id,
                payment_gateway=GATEWAY,
                gateway_order_id=gateway_order.id,
                amount=amount,
                currency=gateway_order.currency,
                status=PaymentTransactionStatus.INITIATED,
            )
        )
        logger.info(
            "Created Razorpay order %s for order %s (attempt %s, %s paise)",
            gateway_order.id, order.id, attempt, amount_paise,
        )
        return PaymentIntentResult(intent=self._intent(order, payment), created=True)

    def _intent(self, order: Order, payment: Payment) -> PaymentIntentResponse:
        return PaymentIntentResponse(
            order_id=order.id,
            order_number=order.order_number,
            razorpay_order_id=payment.gateway_order_id,
            razorpay_key_id=self.gateway.key_id,
            amount_paise=to_paise(payment.amount),
            currency=payment.currency,
        )

    # --- verification (M5) ---------------------------------------------------

    def verify_payment(
        self,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> VerifyResult:
        """Verify what Razorpay Checkout reported and, if the money is really
        captured, pay the order. See "Verifying" in the module docstring.

        Raises:
            PaymentVerificationError: bad signature, not this order's Razorpay
                order, or Razorpay does not confirm the payment (400).
            PaymentVerificationUnavailableError: Razorpay could not be asked (502).
            OrderNotFoundError: unknown or someone else's order (404).
            OrderAlreadyPaidError: the order was paid by a different payment (409).
            LatePaymentError: the money arrived after the order closed; it is
                recorded and flagged for refund first, then this is raised (409).
        """
        # 1. The signature first: it needs no database and no network, so a
        #    forged request is turned away before it costs anything.
        if not self.gateway.verify_checkout_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            logger.warning("Payment verification rejected for order %s: signature does not match", order_id)
            raise PaymentVerificationError()

        try:
            result = self._verify_payment(
                user_id, order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            logger.error("Payment verification for order %s hit a uniqueness conflict", order_id)
            raise PaymentVerificationError() from None
        except BaseException:
            self.db.rollback()
            raise

        # Raised AFTER the commit on purpose: the late payment must be on record.
        if result.outcome is VerifyOutcome.LATE:
            raise LatePaymentError()
        return result

    def _verify_payment(
        self,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> VerifyResult:
        # 2. Lock the order, then this order's payment row (always in this
        #    order: order first, payment second - the webhook and the expiry
        #    job take them the same way, so they cannot deadlock).
        order = self.orders.get_for_user(order_id, user_id, for_update=True)
        if order is None:
            raise OrderNotFoundError()
        payment = self.payments.get_for_order_by_gateway_order_id(order.id, razorpay_order_id, for_update=True)
        if payment is None:
            logger.warning("Payment verification for order %s names a Razorpay order that is not its own", order.id)
            raise PaymentVerificationError()

        # 3. Already recorded: answer from the database, change nothing.
        if is_paid(payment.status):
            if payment.gateway_payment_id != razorpay_payment_id:
                # A signed payment id, but not the one that paid this Razorpay order.
                logger.warning("Order %s: a second payment id was reported for an already paid Razorpay order", order.id)
                raise OrderAlreadyPaidError()
            outcome = VerifyOutcome.LATE if payment.refund_required else VerifyOutcome.ALREADY_PAID
            return VerifyResult(order=to_order_response(order, now=self.clock()), outcome=outcome)

        # 4. Ask Razorpay what really happened.
        try:
            remote = self.gateway.fetch_payment(razorpay_payment_id)
        except PaymentGatewayError:
            raise PaymentVerificationUnavailableError() from None
        if (
            remote.id != razorpay_payment_id
            or remote.order_id != razorpay_order_id
            or remote.amount_paise != to_paise(payment.amount)
            or remote.currency != payment.currency
        ):
            logger.error("Razorpay's record of payment %s does not match our payment for order %s", razorpay_payment_id, order.id)
            raise PaymentVerificationError()

        if remote.status == "authorized":
            return self._record_authorized(order, payment, razorpay_payment_id, razorpay_signature)
        if remote.status != "captured":
            logger.warning("Payment %s for order %s is '%s' at Razorpay, not captured", razorpay_payment_id, order.id, remote.status)
            raise PaymentVerificationError()

        # 5. The money is ours. Does it pay the order, or is it a late payment?
        return self._record_captured(order, payment, razorpay_payment_id, razorpay_signature)

    def _record_authorized(self, order: Order, payment: Payment, payment_id: str, signature: str) -> VerifyResult:
        """Razorpay holds the money but has not captured it. Record that much
        (so a later capture finds the payment), and leave the order unpaid."""
        if can_transition(payment.status, PaymentTransactionStatus.AUTHORIZED):
            transition(
                payment, PaymentTransactionStatus.AUTHORIZED, gateway_payment_id=payment_id, gateway_signature=signature
            )
            self.db.flush()
        logger.info("Payment %s for order %s is authorized, not captured yet", payment_id, order.id)
        return VerifyResult(order=to_order_response(order, now=self.clock()), outcome=VerifyOutcome.PENDING_CAPTURE)

    def _record_captured(self, order: Order, payment: Payment, payment_id: str, signature: str) -> VerifyResult:
        disposition = apply_capture(
            self.db, order, payment, payment_id=payment_id, signature=signature, now=self.clock()
        )
        outcome = VerifyOutcome.PAID if disposition is CaptureDisposition.PAYS_ORDER else VerifyOutcome.LATE
        return VerifyResult(order=to_order_response(order, now=self.clock()), outcome=outcome)
