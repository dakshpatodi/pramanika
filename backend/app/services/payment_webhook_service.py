"""
Razorpay webhooks: the server hears about payments directly from Razorpay.

The browser can close the tab, lose its network, or never call
`/payment/verify`; the money may still have been taken. The webhook is how
the server finds out regardless, so an order paid at Razorpay gets paid here
too, with no customer involved.

    handle(raw_body, signature_header, event_id_header)

In this order:

  1. the webhook secret must be configured (503 otherwise - Razorpay retries);
  2. the body must be a sane size;
  3. the SIGNATURE of the raw bytes must match (400, nothing else happens);
  4. the body is read; unknown event types are acknowledged and ignored;
  5. ONE transaction:
       a. claim the event id in `payment_webhook_events` - a repeat delivery
          (Razorpay retries until it gets a 2xx) finds it taken and does nothing;
       b. find the payment by Razorpay order id, lock the ORDER, then the
          payment (the same order as verification and expiry: no deadlocks);
       c. apply the event through the payment state machine;
       d. record what happened, commit.
     Any failure rolls back the claim too, so Razorpay's retry starts clean.

What each event does (never trusting the event's own idea of the order's state):

  captured / order.paid  -> CAPTURED; a live order is paid and its reservation
                            consumed, a closed one is flagged `refund_required`
                            (the order is never revived). Already captured: nothing.
  authorized             -> AUTHORIZED if still INITIATED; otherwise nothing.
  failed                 -> FAILED if still open and it is the attempt we track;
                            NEVER moves a captured payment, never touches the
                            order or its stock (a failed attempt can be retried).

The amount and currency in the event must equal what we stored; a mismatch is
recorded as rejected and nothing changes. The body is never stored or logged.
"""

import enum
import hashlib
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import (
    PaymentsNotConfiguredError,
    WebhookPayloadError,
    WebhookSignatureError,
    WebhookTooLargeError,
)
from app.core.money import to_paise
from app.models import Payment, PaymentTransactionStatus as S
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.payment_webhook_repository import PaymentWebhookRepository
from app.services.payment_capture import apply_capture
from app.services.payment_rules import CaptureDisposition, is_paid
from app.services.payment_state import transition
from app.services.razorpay_signature import is_valid_webhook_signature
from app.services.razorpay_webhook import (
    CAPTURE_EVENTS,
    EVENT_AUTHORIZED,
    HANDLED_EVENTS,
    MalformedWebhookError,
    WebhookEvent,
    parse_webhook,
)

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 256 * 1024
MAX_EVENT_ID = 100
DEFAULT_FAILURE_REASON = "The payment failed."


class WebhookOutcome(str, enum.Enum):
    """What the handler did. Stored (as text) next to the event id."""

    PAID = "paid"                              # captured and the order is now paid
    LATE_PAYMENT = "late_payment"              # captured after the order closed: flagged for refund
    AUTHORIZED = "authorized"
    FAILED = "failed"
    ALREADY_RECORDED = "already_recorded"      # the payment was already in that state
    IGNORED_STALE = "ignored_stale"            # out of order / another attempt: nothing to do
    IGNORED_EVENT = "ignored_event"            # an event type we do not act on
    IGNORED_UNKNOWN = "ignored_unknown"        # not one of our payments (or unreadable ids)
    REJECTED_MISMATCH = "rejected_mismatch"    # amount or currency differ from what we stored
    MANUAL_REVIEW = "manual_review"            # a second payment id captured on an already paid Razorpay order
    DUPLICATE = "duplicate"                    # this delivery was already processed (not stored)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def event_key(event_id_header: Optional[str], raw_body: bytes) -> str:
    """The idempotency key: Razorpay's `X-Razorpay-Event-Id` (the same on every
    retry of one event). If it is missing or unusable, a hash of the body -
    a retry sends the same bytes, so it still deduplicates."""
    candidate = (event_id_header or "").strip()
    if candidate and len(candidate) <= MAX_EVENT_ID and candidate.isprintable():
        return candidate
    return "sha256:" + hashlib.sha256(raw_body).hexdigest()


class PaymentWebhookService:
    def __init__(self, db: Session, webhook_secret: str, *, clock: Callable[[], datetime] = _utcnow):
        self.db = db
        self._secret = webhook_secret
        self.clock = clock
        self.orders = OrderRepository(db)
        self.payments = PaymentRepository(db)
        self.events = PaymentWebhookRepository(db)

    # ------------------------------------------------------------------

    def handle(
        self, raw_body: bytes, signature: Optional[str], event_id_header: Optional[str] = None
    ) -> WebhookOutcome:
        """Authenticate, then process one delivery. Returns what was done; the
        endpoint answers 2xx for every outcome (including ignored ones, which
        are permanent - a retry would change nothing).

        Raises:
            PaymentsNotConfiguredError: no webhook secret on the server (503).
            WebhookTooLargeError: absurdly large body (413).
            WebhookSignatureError: signature missing or wrong (400).
            WebhookPayloadError: signed but unreadable body (400).
        """
        if not self._secret:
            logger.error("Razorpay webhook received but RAZORPAY_WEBHOOK_SECRET is not set")
            raise PaymentsNotConfiguredError()
        if len(raw_body) > MAX_BODY_BYTES:
            raise WebhookTooLargeError()
        if not is_valid_webhook_signature(self._secret, raw_body, signature):
            logger.warning("Razorpay webhook rejected: signature does not match")
            raise WebhookSignatureError()
        try:
            event = parse_webhook(raw_body)
        except MalformedWebhookError:
            logger.warning("Razorpay webhook rejected: signed body is not a readable event")
            raise WebhookPayloadError() from None

        key = event_key(event_id_header, raw_body)
        try:
            outcome = self._process(key, event)
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        logger.info("Razorpay webhook %s (%s): %s", key, event.type, outcome.value)
        return outcome

    # ------------------------------------------------------------------

    def _process(self, key: str, event: WebhookEvent) -> WebhookOutcome:
        if not self.events.claim(key, event.type, event.gateway_order_id, event.gateway_payment_id):
            return WebhookOutcome.DUPLICATE
        outcome = self._apply(event)
        self.events.set_outcome(key, outcome.value)
        return outcome

    def _apply(self, event: WebhookEvent) -> WebhookOutcome:
        if event.type not in HANDLED_EVENTS:
            return WebhookOutcome.IGNORED_EVENT
        if not event.gateway_order_id or not event.gateway_payment_id:
            return WebhookOutcome.IGNORED_UNKNOWN

        # Which order is this? (unlocked read) Then lock in the one allowed
        # order: ORDER first, PAYMENT second.
        probe = self.payments.get_by_gateway_order_id(event.gateway_order_id)
        if probe is None:
            logger.info("Razorpay webhook for %s: not one of our payments", event.gateway_order_id)
            return WebhookOutcome.IGNORED_UNKNOWN
        order = self.orders.get_for_update(probe.order_id)
        payment = (
            self.payments.get_for_order_by_gateway_order_id(order.id, event.gateway_order_id, for_update=True)
            if order is not None
            else None
        )
        if order is None or payment is None:  # deleted between the two reads: nothing to act on
            return WebhookOutcome.IGNORED_UNKNOWN

        if event.amount_paise != to_paise(payment.amount) or event.currency != payment.currency:
            logger.error(
                "Razorpay webhook %s for payment %s: amount/currency differ from what we stored; nothing changed",
                event.type, event.gateway_payment_id,
            )
            return WebhookOutcome.REJECTED_MISMATCH

        if event.type in CAPTURE_EVENTS:
            return self._captured(order, payment, event)
        if event.type == EVENT_AUTHORIZED:
            return self._authorized(payment, event)
        return self._failed(payment, event)  # the only handled type left: payment.failed

    # --- the three things an event can say ------------------------------

    def _captured(self, order, payment: Payment, event: WebhookEvent) -> WebhookOutcome:
        if is_paid(payment.status):
            if payment.gateway_payment_id == event.gateway_payment_id:
                return WebhookOutcome.ALREADY_RECORDED
            # Our row holds one payment id; money for a second one cannot be
            # stored here. The event row keeps its id so it can be refunded.
            logger.error(
                "Razorpay order %s is already paid by %s, but %s was captured too: needs a manual refund",
                payment.gateway_order_id, payment.gateway_payment_id, event.gateway_payment_id,
            )
            return WebhookOutcome.MANUAL_REVIEW
        disposition = apply_capture(
            self.db, order, payment, payment_id=event.gateway_payment_id, signature=None, now=self.clock()
        )
        return WebhookOutcome.PAID if disposition is CaptureDisposition.PAYS_ORDER else WebhookOutcome.LATE_PAYMENT

    def _authorized(self, payment: Payment, event: WebhookEvent) -> WebhookOutcome:
        if payment.status == S.AUTHORIZED and payment.gateway_payment_id == event.gateway_payment_id:
            return WebhookOutcome.ALREADY_RECORDED
        if payment.status != S.INITIATED:
            return WebhookOutcome.IGNORED_STALE  # e.g. it was captured first: events arrive in any order
        transition(payment, S.AUTHORIZED, gateway_payment_id=event.gateway_payment_id)
        self.db.flush()
        return WebhookOutcome.AUTHORIZED

    def _failed(self, payment: Payment, event: WebhookEvent) -> WebhookOutcome:
        if payment.status == S.FAILED and payment.gateway_payment_id == event.gateway_payment_id:
            return WebhookOutcome.ALREADY_RECORDED
        if payment.status not in (S.INITIATED, S.AUTHORIZED):
            # CAPTURED / REFUNDED: a late failure never un-pays money that arrived.
            # EXPIRED / FAILED: already closed.
            return WebhookOutcome.IGNORED_STALE
        if payment.gateway_payment_id not in (None, event.gateway_payment_id):
            # A different attempt on the same Razorpay order is the one we track
            # (and it may be authorized): this failure is not about it.
            return WebhookOutcome.IGNORED_STALE
        transition(
            payment, S.FAILED, gateway_payment_id=event.gateway_payment_id,
            failure_reason=event.failure_reason or DEFAULT_FAILURE_REASON,
        )
        self.db.flush()
        return WebhookOutcome.FAILED
