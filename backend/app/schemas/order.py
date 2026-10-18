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

from app.models import OrderCancellationReason, OrderPaymentStatus, OrderStatus
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


class OrderPaymentInfo(BaseModel):
    """What the customer may be told about the payment attempts on an order.
    No gateway ids, no amounts, no failure text from the bank."""

    last_attempt: Optional[str] = None
    """Status of the most recent Razorpay attempt: initiated, authorized,
    failed, expired, captured, refunded - or null if none was ever started.
    "failed" on a payable order means: the last try did not go through, try again."""
    refund_pending: bool = False
    """True if money was received for this order AFTER it closed (cancelled or
    expired) and is waiting to be refunded."""


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_number: Optional[str] = None
    status: OrderStatus
    payment_status: OrderPaymentStatus
    can_cancel: bool
    can_pay: bool
    """The server's verdict: a payment may be started (or resumed) on this order
    right now. False for paid, cancelled, expired - and for an order past its
    deadline that the expiry job has not reached yet."""
    expires_at: Optional[datetime] = None
    """When an unpaid order stops being payable and releases its stock."""
    cancellation_reason: Optional[OrderCancellationReason] = None
    """Why a cancelled order was cancelled: "customer" or "expired"."""
    payment: OrderPaymentInfo
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
    can_pay: bool
    expires_at: Optional[datetime] = None
    cancellation_reason: Optional[OrderCancellationReason] = None
    total: float
    item_count: int
    """Total units across all lines."""
    line_count: int
    """Number of different products (lines) in the order."""
    item_names: List[str]
    """Up to the first three product names, for a one-line description."""
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: List[OrderSummaryResponse]
    pagination: PaginationMeta
