"""
Coupon repository - read-only in Phase 5.

`used_count` is deliberately never touched here: it is incremented only
when an order is actually placed (Phase 6), not when a coupon is applied
to a cart.
"""

import uuid
from typing import Optional

from sqlalchemy import func
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

    def get_by_id(self, coupon_id: uuid.UUID) -> Optional[Coupon]:
        return self.db.query(Coupon).filter(Coupon.id == coupon_id).first()