"""
Payment repository. Like the others it only stages changes (flush, never
commit); `PaymentService` owns the transaction.
"""

import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Payment, PaymentTransactionStatus

OPEN = (PaymentTransactionStatus.INITIATED, PaymentTransactionStatus.AUTHORIZED)


class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()  # assigns the id and fires the unique indexes, no commit
        return payment

    def get_open_for_order(self, order_id: uuid.UUID) -> Optional[Payment]:
        """The order's initiated/authorized payment, if any. The database
        guarantees there is at most one (`uq_payments_one_open_per_order`)."""
        return (
            self.db.query(Payment)
            .filter(Payment.order_id == order_id, Payment.status.in_(OPEN))
            .populate_existing()
            .first()
        )

    def has_captured(self, order_id: uuid.UUID) -> bool:
        return bool(
            self.db.execute(
                select(
                    select(Payment.id)
                    .where(Payment.order_id == order_id, Payment.status == PaymentTransactionStatus.CAPTURED)
                    .exists()
                )
            ).scalar()
        )

    def count_for_order(self, order_id: uuid.UUID) -> int:
        return self.db.execute(select(func.count(Payment.id)).where(Payment.order_id == order_id)).scalar_one()

    def get_for_order_by_gateway_order_id(
        self, order_id: uuid.UUID, gateway_order_id: str, *, for_update: bool = False
    ) -> Optional[Payment]:
        """The payment row of THIS order for that Razorpay order id. Scoped by
        order id on purpose: a Razorpay order id that belongs to another order
        simply is not found."""
        query = self.db.query(Payment).filter(
            Payment.order_id == order_id, Payment.gateway_order_id == gateway_order_id
        )
        if for_update:
            query = query.with_for_update(of=Payment).populate_existing()
        return query.first()

    def list_open_for_order(self, order_id: uuid.UUID, *, for_update: bool = False) -> List[Payment]:
        """The order's initiated/authorized payments (at most one, enforced by
        the database; a list so callers do not depend on that)."""
        query = self.db.query(Payment).filter(Payment.order_id == order_id, Payment.status.in_(OPEN))
        if for_update:
            query = query.with_for_update(of=Payment).populate_existing()
        return query.order_by(Payment.created_at).all()

    def get_by_gateway_order_id(self, gateway_order_id: str) -> Optional[Payment]:
        """The payment row for a Razorpay order id, from any order, unlocked.
        Used by the webhook to find out WHICH Pramanika order to lock; the row
        is then read again, locked, once the order lock is held."""
        return self.db.query(Payment).filter(Payment.gateway_order_id == gateway_order_id).first()
