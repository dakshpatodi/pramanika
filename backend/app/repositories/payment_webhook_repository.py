"""
Processed webhook deliveries. Like the other repositories it only stages
changes (never commits); `PaymentWebhookService` owns the transaction.
"""

from typing import Optional

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import PaymentWebhookEvent


class PaymentWebhookRepository:
    def __init__(self, db: Session):
        self.db = db

    def claim(
        self,
        event_id: str,
        event_type: str,
        gateway_order_id: Optional[str],
        gateway_payment_id: Optional[str],
    ) -> bool:
        """Try to be the one delivery that processes `event_id`.

        True: this call inserted the row - go ahead. False: the event was
        already processed (or is being processed and has committed by now).

        `INSERT ... ON CONFLICT DO NOTHING` rather than catching an
        IntegrityError, so losing the race does not poison the session. If
        another delivery of the same event is mid-transaction, this blocks
        until it commits (then returns False) or rolls back (then inserts).
        The row lives in the same transaction as the state change: both
        happen or neither, so a failed attempt is simply retried by Razorpay.
        """
        result = self.db.execute(
            pg_insert(PaymentWebhookEvent)
            .values(
                event_id=event_id,
                event_type=event_type,
                gateway_order_id=gateway_order_id,
                gateway_payment_id=gateway_payment_id,
                outcome="received",
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(PaymentWebhookEvent.event_id)
        )
        return result.scalar_one_or_none() is not None

    def set_outcome(self, event_id: str, outcome: str) -> None:
        self.db.execute(
            update(PaymentWebhookEvent)
            .where(PaymentWebhookEvent.event_id == event_id)
            .values(outcome=outcome)
            .execution_options(synchronize_session=False)
        )
