"""
Development seed script for coupons.

Standalone - not imported by the running app. Run from backend/, with the
venv active:

    python -m scripts.seed_coupons

Idempotent: each coupon is looked up by code first, so re-running never
creates duplicates. Existing coupons are left exactly as they are.

The set covers every branch of the cart's coupon rules, so the Phase 5
smoke test has a real coupon for each case:

    WELCOME10   10% off, min order 200, discount capped at 100
    FLAT100     flat 100 off, min order 500
    BIG20       20% off, min order 1500, discount capped at 500
    EXPIRED50   expired yesterday
    INACTIVE20  switched off
    USEDUP      usage limit already reached
    FUTURE15    not valid until next year
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.database.session import SessionLocal
from app.models import Coupon, DiscountType


def _coupons(now: datetime) -> list:
    return [
        {
            "code": "WELCOME10",
            "description": "10% off your order (up to Rs.100) on orders of Rs.200 or more.",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": 10,
            "minimum_order_amount": 200,
            "maximum_discount_amount": 100,
        },
        {
            "code": "FLAT100",
            "description": "Flat Rs.100 off on orders of Rs.500 or more.",
            "discount_type": DiscountType.FIXED_AMOUNT,
            "discount_value": 100,
            "minimum_order_amount": 500,
        },
        {
            "code": "BIG20",
            "description": "20% off (up to Rs.500) on orders of Rs.1500 or more.",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": 20,
            "minimum_order_amount": 1500,
            "maximum_discount_amount": 500,
        },
        {
            "code": "EXPIRED50",
            "description": "Expired test coupon.",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": 50,
            "expires_at": now - timedelta(days=1),
        },
        {
            "code": "INACTIVE20",
            "description": "Inactive test coupon.",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": 20,
            "is_active": False,
        },
        {
            "code": "USEDUP",
            "description": "Usage-limit-reached test coupon.",
            "discount_type": DiscountType.FIXED_AMOUNT,
            "discount_value": 50,
            "usage_limit": 1,
            "used_count": 1,
        },
        {
            "code": "FUTURE15",
            "description": "Not-yet-valid test coupon.",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": 15,
            "starts_at": now + timedelta(days=365),
        },
    ]


def main() -> None:
    now = datetime.now(timezone.utc)
    created = 0
    skipped = 0

    with SessionLocal() as db:
        for data in _coupons(now):
            exists = db.query(Coupon).filter(func.lower(Coupon.code) == data["code"].lower()).first()
            if exists:
                skipped += 1
                continue
            db.add(Coupon(**data))
            created += 1
        db.commit()

    print(f"Coupons: {created} created, {skipped} already present.")


if __name__ == "__main__":
    main()