"""
Order queries for the expiry job. Like the other repositories it only stages
changes (never commits); `OrderExpiryService` owns the transactions.

Kept apart from `OrderRepository` so Phase 6's repository stays as it was.
"""

import uuid
from datetime import datetime
from typing import Collection, List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Order,
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
)


def _is_open(*, now: datetime):
    """An unpaid order that still holds its stock and whose deadline has passed.
    The first three conditions are the predicate of the partial index
    `ix_orders_open_expires_at`, so finding due orders never scans the table."""
    return (
        Order.status == OrderStatus.PENDING,
        Order.payment_status == OrderPaymentStatus.PENDING,
        Order.inventory_state == OrderInventoryState.RESERVED,
        Order.expires_at.is_not(None),
        Order.expires_at <= now,
    )


class OrderExpiryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_due_ids(self, now: datetime, limit: int, exclude: Collection[uuid.UUID] = ()) -> List[uuid.UUID]:
        """Oldest deadline first, skipping `exclude` (orders this pass already
        tried, so a few that always fail or stay busy cannot hold up the rest).
        A plain read: it only nominates candidates; every one is locked and
        re-checked before anything changes."""
        query = select(Order.id).where(*_is_open(now=now))
        if exclude:
            query = query.where(Order.id.not_in(list(exclude)))
        return list(self.db.execute(query.order_by(Order.expires_at, Order.id).limit(limit)).scalars().all())

    def lock_skipping_busy(self, order_id: uuid.UUID) -> Optional[Order]:
        """Lock the order, or return None if somebody else holds it right now
        (a verification, a webhook, a cancel, another expiry worker) or it no
        longer exists. A busy order is simply left for the next pass: whoever
        has it is about to decide its fate, and may well pay it."""
        return (
            self.db.query(Order)
            .options(selectinload(Order.items))
            .filter(Order.id == order_id)
            .with_for_update(of=Order, skip_locked=True)
            .populate_existing()
            .first()
        )

    def expire_pending(self, order_id: uuid.UUID, now: datetime) -> bool:
        """Cancel-because-expired an order that is STILL unpaid, STILL holding
        its reservation and STILL past its deadline - one atomic statement,
        the sibling of `OrderRepository.cancel_pending` (reason EXPIRED
        instead of CUSTOMER). True for exactly one caller; a paid, cancelled or
        already expired order, or one whose deadline is in the future, is not
        touched."""
        result = self.db.execute(
            update(Order)
            .where(Order.id == order_id, *_is_open(now=now))
            .values(
                status=OrderStatus.CANCELLED,
                cancellation_reason=OrderCancellationReason.EXPIRED,
                inventory_state=OrderInventoryState.RELEASED,
                cancelled_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
