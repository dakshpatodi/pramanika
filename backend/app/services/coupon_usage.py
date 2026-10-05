"""
Recording coupon usage when orders are placed and cancelled.

`used_count` is only ever changed here, inside the same transaction as the
order itself:

  consume()  - an order using the coupon was created (+1)
  restore()  - that order was cancelled (-1)

consume() is the last line of defence against two checkouts taking the
final use: the increment only happens if the coupon is active and under
its limit, in one atomic statement, so exactly one of them succeeds.

Policy: cancelling an unpaid order gives the coupon use back. Callers
must only call restore() for the one caller that won the order's
cancellation gate (OrderRepository.cancel_pending), so it can never be
restored twice for one order.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCouponError
from app.repositories.coupon_repository import CouponRepository


class CouponUsageService:
    def __init__(self, db: Session):
        self.coupons = CouponRepository(db)

    def consume(self, coupon_id: uuid.UUID) -> None:
        if not self.coupons.increment_usage(coupon_id):
            raise InvalidCouponError("This coupon is no longer available.")

    def restore(self, coupon_id: uuid.UUID) -> bool:
        return self.coupons.decrement_usage(coupon_id)