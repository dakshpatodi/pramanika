"""Admin dashboard response (Phase 9 M2)."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class OrderMetrics(BaseModel):
    total: int
    by_status: Dict[str, int]


class CustomerMetrics(BaseModel):
    total: int
    new_last_30_days: int


class ProductMetrics(BaseModel):
    total: int
    active: int
    inactive: int
    low_stock: int
    out_of_stock: int


class RevenueMetrics(BaseModel):
    """Money the shop has actually been paid: orders with payment_status 'paid'
    that are not cancelled or refunded. Gross (includes GST and delivery)."""

    currency: str
    all_time: float
    all_time_orders: int
    last_30_days: float
    last_30_days_orders: int


class RecentOrder(BaseModel):
    id: uuid.UUID
    order_number: Optional[str]
    customer_name: str
    customer_email: str
    total_amount: float
    status: str
    payment_status: str
    created_at: datetime


class DashboardResponse(BaseModel):
    generated_at: datetime
    orders: OrderMetrics
    customers: CustomerMetrics
    products: ProductMetrics
    revenue: RevenueMetrics
    recent_orders: List[RecentOrder]
