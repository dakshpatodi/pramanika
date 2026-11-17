"""
Admin order schemas (Phase 9 M5).

The ONLY write is a fulfilment step: `status` of processing, shipped or
delivered, plus an optional short note for the audit trail. Nothing else can
be sent (extra fields are refused), so payment status, stock, totals and
ownership are not reachable from this API. Gateway ids are shown to admins,
but never the payment signature.
"""

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import OrderCancellationReason, OrderInventoryState, OrderPaymentStatus, OrderStatus
from app.schemas.product import PaginationMeta


class FulfilmentTarget(str, enum.Enum):
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FulfilmentTarget
    note: Optional[str] = Field(None, max_length=200)

    @field_validator("note", mode="before")
    @classmethod
    def _strip_note(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class AdminOrderSort(str, enum.Enum):
    CREATED_AT = "created_at"
    TOTAL = "total"
    STATUS = "status"
    ORDER_NUMBER = "order_number"


class AdminCustomer(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone_number: Optional[str] = None


class AdminOrderListItem(BaseModel):
    id: uuid.UUID
    order_number: Optional[str] = None
    status: OrderStatus
    payment_status: OrderPaymentStatus
    inventory_state: OrderInventoryState
    cancellation_reason: Optional[OrderCancellationReason] = None
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    item_count: int
    total_amount: float
    next_status: Optional[FulfilmentTarget] = None
    created_at: datetime


class AdminOrderListResponse(BaseModel):
    orders: List[AdminOrderListItem]
    pagination: PaginationMeta


class AdminOrderLine(BaseModel):
    product_id: Optional[uuid.UUID] = None
    name: str
    sku: str
    unit_price: float
    quantity: int
    subtotal: float


class AdminOrderTotals(BaseModel):
    subtotal: float
    discount: float
    taxable_amount: float
    gst_rate: float
    gst: float
    delivery_charge: float
    total: float


class AdminShippingAddress(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class AdminPaymentAttempt(BaseModel):
    id: uuid.UUID
    gateway: str
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    status: str
    amount: float
    currency: str
    failure_reason: Optional[str] = None
    refund_required: bool
    paid_at: Optional[datetime] = None
    created_at: datetime


class AdminOrderDetail(BaseModel):
    id: uuid.UUID
    order_number: Optional[str] = None
    status: OrderStatus
    payment_status: OrderPaymentStatus
    inventory_state: OrderInventoryState
    cancellation_reason: Optional[OrderCancellationReason] = None
    customer: AdminCustomer
    coupon_code: Optional[str] = None
    items: List[AdminOrderLine]
    item_count: int
    totals: AdminOrderTotals
    shipping_address: AdminShippingAddress
    payments: List[AdminPaymentAttempt]
    reserved_units: int
    next_status: Optional[FulfilmentTarget] = None
    can_advance: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    cancelled_at: Optional[datetime] = None
    updated_at: datetime
