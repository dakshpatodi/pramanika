"""
Unpaid orders expire: after `ORDER_PAYMENT_WINDOW_MINUTES` (30) an order that
was never paid gives its stock and its coupon use back, so one abandoned
checkout cannot hold goods hostage.

Per order, ONE transaction, in the lock order used everywhere else
(order -> payments -> inventory):

  1. lock the order with SKIP LOCKED - if verification, a webhook, a cancel or
     another worker has it, skip it; the next pass looks again
  2. compare-and-set: still pending + unpaid + holding stock + past its deadline?
     (`expire_pending`; exactly one caller can win) -> status cancelled,
     reason `expired`, stock marked released
  3. only the winner continues: close the open payment attempt (EXPIRED, so a
     stale Razorpay order is not payable), give the coupon use back once,
     release the reserved units once
  4. commit

Safety properties, each covered by tests:
  * atomic - a failure at any step rolls the whole order back to untouched;
  * idempotent - running it twice, or twenty workers at once, changes nothing
    the second time (stock released once, coupon restored once);
  * a paid order is never expired, and an expired one can never be paid:
    `mark_paid` requires status pending, and a payment that arrives later is
    recorded as a late payment and flagged for refund (M5/M7);
  * one bad order never blocks the others: each has its own transaction.

Nothing here talks to Razorpay: a payment attempt that is still open at the
gateway cannot be cancelled by this job, it is only closed on our side.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.repositories.order_expiry_repository import OrderExpiryRepository
from app.repositories.payment_repository import PaymentRepository
from app.services.coupon_usage import CouponUsageService
from app.services.payment_state import REASON_ORDER_EXPIRED, close_open_payments
from app.services.reservation_service import ReservationService

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
MAX_BATCHES_PER_RUN = 100
"""A pass drains a backlog batch by batch, but never loops forever."""


class ExpireOutcome(str, enum.Enum):
    EXPIRED = "expired"
    BUSY = "busy"        # locked by someone else, or gone: left for the next pass
    NOT_DUE = "not_due"  # paid, cancelled, expired already, or its deadline moved


@dataclass
class ExpiryRun:
    expired: int = 0
    busy: int = 0
    not_due: int = 0
    failed: int = 0
    batches: int = 0

    def __iadd__(self, other: "ExpiryRun") -> "ExpiryRun":
        self.expired += other.expired
        self.busy += other.busy
        self.not_due += other.not_due
        self.failed += other.failed
        self.batches += other.batches
        return self


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderExpiryService:
    def __init__(self, db: Session, *, clock: Callable[[], datetime] = _utcnow):
        self.db = db
        self.clock = clock
        self.orders = OrderExpiryRepository(db)
        self.payments = PaymentRepository(db)
        self.reservations = ReservationService(db)
        self.coupon_usage = CouponUsageService(db)

    def due_order_ids(self, limit: int = DEFAULT_BATCH_SIZE, exclude=()):
        try:
            return self.orders.list_due_ids(self.clock(), limit, exclude)
        finally:
            self.db.rollback()  # read-only: release the snapshot

    def expire_order(self, order_id: uuid.UUID) -> ExpireOutcome:
        """Expire one order in its own transaction. Raises on a real failure
        (after rolling back), so the caller can count it and carry on."""
        try:
            outcome = self._expire(order_id)
            self.db.commit()
            return outcome
        except BaseException:
            self.db.rollback()
            raise

    def _expire(self, order_id: uuid.UUID) -> ExpireOutcome:
        order = self.orders.lock_skipping_busy(order_id)
        if order is None:
            return ExpireOutcome.BUSY
        now = self.clock()
        if not self.orders.expire_pending(order.id, now):
            return ExpireOutcome.NOT_DUE

        # We won the gate: only we close the payment, restore the coupon and
        # release the stock.
        closed = close_open_payments(self.payments, order.id, reason=REASON_ORDER_EXPIRED)
        if order.coupon_id is not None:
            self.coupon_usage.restore(order.coupon_id)
        self.reservations.release_items(order)
        logger.info("Order %s expired unpaid (closed %d open payment attempt(s))", order.id, closed)
        return ExpireOutcome.EXPIRED


def run_expiry_pass(
    session_factory: Callable[[], Session],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    clock: Callable[[], datetime] = _utcnow,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> ExpiryRun:
    """Expire everything that is due, a batch at a time (oldest deadline first).

    Each order gets a session of its own, so a failure poisons nothing else.
    An order is tried at most once per pass: busy or failing ones are skipped
    by the following batches (so a handful of stuck orders cannot keep the
    orders behind them from expiring) and are simply tried again on the next
    pass. Stops when no due order is left to try, or after `max_batches`.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    total = ExpiryRun()
    attempted = set()
    for _ in range(max_batches):
        lister = session_factory()
        try:
            ids = OrderExpiryService(lister, clock=clock).due_order_ids(batch_size, attempted)
        finally:
            lister.close()
        if not ids:
            break
        batch = ExpiryRun(batches=1)
        for order_id in ids:
            attempted.add(order_id)
            session = session_factory()
            try:
                outcome = OrderExpiryService(session, clock=clock).expire_order(order_id)
            except Exception:  # noqa: BLE001 - one bad order must not stop the rest
                logger.exception("Expiring order %s failed; it will be retried on the next pass", order_id)
                batch.failed += 1
            else:
                if outcome is ExpireOutcome.EXPIRED:
                    batch.expired += 1
                elif outcome is ExpireOutcome.BUSY:
                    batch.busy += 1
                else:
                    batch.not_due += 1
            finally:
                session.close()
        total += batch
        if len(ids) < batch_size:
            break
    if total.expired or total.failed:
        logger.info(
            "Order expiry pass: %d expired, %d busy, %d not due, %d failed", total.expired, total.busy, total.not_due, total.failed
        )
    return total
