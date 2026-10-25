"""
Invoice reads (Phase 8). Read-only, always scoped to the owner in the query
itself, so someone else's order looks exactly like a missing one.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, OrderPaymentStatus, Payment, PaymentTransactionStatus


class InvoiceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_order_for_user(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(selectinload(Order.items))
            .filter(Order.id == order_id, Order.user_id == user_id)
            .populate_existing()
            .first()
        )

    def paid_at(self, order_id: uuid.UUID) -> Optional[datetime]:
        """When the money was captured for this order, from a payment that
        really paid it (not a late capture flagged for refund)."""
        return self.db.execute(
            select(func.min(Payment.paid_at)).where(
                Payment.order_id == order_id,
                Payment.status == PaymentTransactionStatus.CAPTURED,
                Payment.refund_required.is_(False),
            )
        ).scalar_one_or_none()

    def list_paid_for_user(self, user_id: uuid.UUID, *, page: int, page_size: int) -> Tuple[List[Order], int]:
        base = self.db.query(Order).filter(
            Order.user_id == user_id, Order.payment_status == OrderPaymentStatus.PAID
        )
        total = base.with_entities(func.count(Order.id)).scalar() or 0
        orders = (
            base.options(selectinload(Order.items))
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return orders, total
