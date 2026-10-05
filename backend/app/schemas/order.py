"""
Order request / response schemas.

Money leaves the API as JSON numbers with two decimals (same convention as
the cart). The responses never include the Idempotency-Key, its
fingerprint, the owner's id or any internal reservation bookkeeping.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import OrderPaymentStatus, OrderStatus
from app.schemas.product import PaginationMeta


class CheckoutRequest(BaseModel):
    """POST /api/orders body. The client says WHERE to deliver and (optionally)
    which total it was shown. It never sends prices, discounts, taxes,
    delivery charges, a user id or the items - those all come from the
    server-side cart."""

    shipping_address_id: uuid.UUID
    expected_total: Optional[Decimal] = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="The total the customer saw. If the server's total differs, nothing is ordered (409).",
    )


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    product_id: Optional[uuid.UUID] = None
    product_name: str
    sku: str
    unit_price: float
    quantity: int
    line_total: float


class OrderTotalsResponse(BaseModel):
    subtotal: float
    discount: float
    taxable_amount: float
    gst_rate: float
    gst: float
    delivery_charge: float
    total: float


class OrderShippingAddressResponse(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_number: Optional[str] = None
    status: OrderStatus
    payment_status: OrderPaymentStatus
    can_cancel: bool
    coupon_code: Optional[str] = None
    items: List[OrderItemResponse]
    item_count: int
    totals: OrderTotalsResponse
    shipping_address: OrderShippingAddressResponse
    created_at: datetime
    cancelled_at: Optional[datetime] = None


class OrderSummaryResponse(BaseModel):
    """One row of the order history list."""

    id: uuid.UUID
    order_number: Optional[str] = None
    status: OrderStatus
    payment_status: OrderPaymentStatus
    total: float
    item_count: int
    item_names: List[str]
    """Up to the first three product names, for a one-line description."""
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: List[OrderSummaryResponse]
    pagination: PaginationMeta