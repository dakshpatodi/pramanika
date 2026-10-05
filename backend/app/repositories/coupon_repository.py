"""
Coupon repository.

Phase 5 only read coupons. Phase 6 adds the two statements that change
`used_count`, which happens exactly when an order is placed or cancelled -
never when a coupon is merely applied to a cart.

`increment_usage` and `decrement_usage` are single conditional UPDATEs
(see InventoryRepository for why): the "is there a use left?" check and
the increment are one atomic step, so two checkouts cannot both take the
last use. Neither commits; the calling service owns the transaction.
"""

import uuid
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.models import Coupon


class CouponRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_code(self, code: str) -> Optional[Coupon]:
        """Case-insensitive, so `save10` and `SAVE10` are the same coupon
        for the customer typing it in."""
        return (
            self.db.query(Coupon)
            .filter(func.lower(Coupon.code) == code.strip().lower())
            .first()
        )

    def get_by_id(self, coupon_id: uuid.UUID, *, for_update: bool = False) -> Optional[Coupon]:
        """`for_update=True` locks the coupon row until the transaction
        ends. Checkout uses it so concurrent checkouts with the same
        coupon are validated one at a time against an up-to-date
        `used_count`."""
        query = self.db.query(Coupon).filter(Coupon.id == coupon_id)
        if for_update:
            query = query.with_for_update().populate_existing()
        return query.first()

    def increment_usage(self, coupon_id: uuid.UUID) -> bool:
        """used_count += 1 if the coupon is active and still has a use left."""
        result = self.db.execute(
            update(Coupon)
            .where(
                Coupon.id == coupon_id,
                Coupon.is_active.is_(True),
                or_(Coupon.usage_limit.is_(None), Coupon.used_count < Coupon.usage_limit),
            )
            .values(used_count=Coupon.used_count + 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def decrement_usage(self, coupon_id: uuid.UUID) -> bool:
        """used_count -= 1 (an order that used it was cancelled). Never
        goes below zero. Callers guard against restoring twice for the
        same order - see the order's compare-and-set gate."""
        result = self.db.execute(
            update(Coupon)
            .where(Coupon.id == coupon_id, Coupon.used_count > 0)
            .values(used_count=Coupon.used_count - 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1