"""
Cart pricing - pure calculation, no database, no HTTP.

Calculation order (Phase 5 decision):

    1. subtotal        = sum(unit_price * quantity)      product lines only
    2. discount        = coupon discount on the subtotal  (0 if no/invalid coupon)
    3. taxable amount  = subtotal - discount
    4. GST             = taxable amount * GST rate
    5. delivery charge = 0 if taxable amount >= free-delivery threshold, else flat charge
    6. total           = taxable amount + GST + delivery charge

Delivery is not taxed, and coupons discount the product subtotal only.

This module never imports SQLAlchemy models or `settings`. The service layer
hands it plain values (and anything shaped like a Coupon), which is what
makes every rule below unit-testable without a database.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional, Protocol, Tuple

from app.core.money import ZERO, Number, to_decimal, to_money

HUNDRED = Decimal("100")

PERCENTAGE = "percentage"
FIXED_AMOUNT = "fixed_amount"


class CouponLike(Protocol):
    """The subset of the Coupon model the pricing rules read."""

    discount_type: Any
    discount_value: Any
    minimum_order_amount: Any
    maximum_discount_amount: Any
    usage_limit: Optional[int]
    used_count: int
    starts_at: Optional[datetime]
    expires_at: Optional[datetime]
    is_active: bool


@dataclass(frozen=True)
class PricingConfig:
    """Business knobs, injected rather than read from settings inside the
    calculation so tests (and a future per-category GST) can pass their own."""

    gst_rate: Decimal
    free_delivery_threshold: Decimal
    delivery_charge: Decimal

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.gst_rate <= Decimal("1")):
            raise ValueError("gst_rate must be a fraction between 0 and 1 (e.g. 0.05 for 5%).")
        if self.free_delivery_threshold < 0:
            raise ValueError("free_delivery_threshold must not be negative.")
        if self.delivery_charge < 0:
            raise ValueError("delivery_charge must not be negative.")

    @classmethod
    def from_settings(cls, settings: Any) -> "PricingConfig":
        return cls(
            gst_rate=to_decimal(settings.GST_RATE),
            free_delivery_threshold=to_money(settings.FREE_DELIVERY_THRESHOLD),
            delivery_charge=to_money(settings.DELIVERY_CHARGE),
        )


@dataclass(frozen=True)
class CartTotals:
    subtotal: Decimal
    discount: Decimal
    taxable_amount: Decimal
    gst_rate: Decimal
    gst: Decimal
    delivery_charge: Decimal
    amount_for_free_delivery: Decimal
    """How much more product value would make delivery free (0 when it
    already is, or when the cart is empty) - lets the UI say "add Rs.120
    more for free delivery" without doing any maths itself."""
    total: Decimal


@dataclass(frozen=True)
class PricingResult:
    totals: CartTotals
    coupon_problem: Optional[str]
    """None when there is no coupon or it applied cleanly; otherwise the
    reason it is not being applied right now (expired, below minimum...).
    The coupon stays attached to the cart - see cart_service."""


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC so comparisons never raise."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def coupon_problem(coupon: CouponLike, subtotal: Decimal, now: datetime) -> Optional[str]:
    """Return why `coupon` cannot be applied right now, or None if it can.

    The minimum-order check runs against the PRE-discount subtotal - a
    coupon's own discount must not be able to disqualify it.
    """
    if not coupon.is_active:
        return "This coupon is not active."

    if coupon.starts_at is not None and now < _aware(coupon.starts_at):
        return "This coupon is not valid yet."

    if coupon.expires_at is not None and now >= _aware(coupon.expires_at):
        return "This coupon has expired."

    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return "This coupon has reached its usage limit."

    minimum = coupon.minimum_order_amount
    if minimum is not None and subtotal < to_decimal(minimum):
        return f"A minimum order of Rs.{to_money(minimum)} is required to use this coupon."

    return None


def calculate_discount(subtotal: Decimal, coupon: CouponLike) -> Decimal:
    """Discount amount for an already-validated coupon.

    - percentage: subtotal * value / 100, capped by maximum_discount_amount
    - fixed_amount: the value itself
    - never negative and never more than the subtotal (no negative totals)
    - an unrecognised discount type yields 0 rather than guessing
    """
    kind = _enum_value(coupon.discount_type)
    value = to_decimal(coupon.discount_value)

    if kind == PERCENTAGE:
        raw = subtotal * value / HUNDRED
        cap = coupon.maximum_discount_amount
        if cap is not None:
            raw = min(raw, to_decimal(cap))
    elif kind == FIXED_AMOUNT:
        raw = value
    else:
        raw = ZERO

    raw = max(raw, ZERO)
    raw = min(raw, subtotal)
    return to_money(raw)


def calculate_totals(
    lines: Iterable[Tuple[Number, int]],
    coupon: Optional[CouponLike],
    now: datetime,
    config: PricingConfig,
) -> PricingResult:
    """Price a cart.

    `lines` is (unit_price, quantity) for every line that is actually
    purchasable. The coupon is re-validated on every call, so a coupon
    that expired (or a cart that fell below its minimum) since it was
    applied simply stops discounting instead of silently over-discounting.
    """
    line_list = list(lines)
    subtotal = to_money(sum((to_money(price) * quantity for price, quantity in line_list), ZERO))

    discount = ZERO
    problem: Optional[str] = None
    if coupon is not None:
        problem = coupon_problem(coupon, subtotal, now)
        if problem is None:
            discount = calculate_discount(subtotal, coupon)

    taxable = to_money(subtotal - discount)
    gst = to_money(taxable * config.gst_rate)

    if not line_list or taxable >= config.free_delivery_threshold:
        delivery = ZERO
    else:
        delivery = to_money(config.delivery_charge)

    amount_for_free = to_money(config.free_delivery_threshold - taxable) if delivery > 0 else ZERO
    total = to_money(taxable + gst + delivery)

    totals = CartTotals(
        subtotal=subtotal,
        discount=discount,
        taxable_amount=taxable,
        gst_rate=config.gst_rate,
        gst=gst,
        delivery_charge=delivery,
        amount_for_free_delivery=amount_for_free,
        total=total,
    )
    return PricingResult(totals=totals, coupon_problem=problem)