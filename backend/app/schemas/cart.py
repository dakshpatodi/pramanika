"""
Cart request/response schemas.

Requests carry only what the client is allowed to decide: which product,
how many, which coupon code. There is deliberately no user_id, price, GST,
discount or delivery field anywhere in a request - the user comes from the
JWT and every amount is computed server-side.

Money fields are plain floats in responses; by the time a value reaches
these schemas it has already been computed and rounded to 2dp as a Decimal
(see app/core/money.py), so the float is purely the JSON representation.
"""

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

MAX_LINE_QUANTITY = 1000
"""Sanity ceiling on a single request, well below Postgres' integer limit.
The real limit is always available stock; this only stops absurd values."""


class CartItemAddRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=MAX_LINE_QUANTITY)


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(ge=1, le=MAX_LINE_QUANTITY)


class CouponApplyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)

    @field_validator("code")
    @classmethod
    def strip_code(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Coupon code must not be blank.")
        return value


class CartProductSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    sku: str
    image_url: Optional[str] = None


class CartItemResponse(BaseModel):
    id: uuid.UUID
    product: CartProductSummary
    quantity: int
    unit_price: float
    line_subtotal: float
    available_quantity: int
    """Stock the customer could still buy of this product - lets the UI cap
    the quantity stepper. Informational only; the server re-checks."""
    issue: Optional[str] = None
    """Set when this line cannot be purchased as it stands (out of stock,
    over available stock, product deactivated). Such lines are excluded
    from the totals."""


class CartCouponResponse(BaseModel):
    code: str
    description: Optional[str] = None
    applied: bool
    """False when the coupon is attached but not currently discounting
    anything (expired, below minimum order...); `message` says why."""
    message: Optional[str] = None


class CartTotalsResponse(BaseModel):
    subtotal: float
    discount: float
    taxable_amount: float
    gst_rate: float
    gst: float
    delivery_charge: float
    amount_for_free_delivery: float
    total: float
    currency: str = "INR"


class CartResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    """None until the user's cart row exists (it is created lazily on the
    first add) - an empty response for a user with no cart is still valid."""
    items: List[CartItemResponse] = []
    item_count: int = 0
    """Total units across all lines (what a navbar badge shows)."""
    has_issues: bool = False
    coupon: Optional[CartCouponResponse] = None
    totals: CartTotalsResponse