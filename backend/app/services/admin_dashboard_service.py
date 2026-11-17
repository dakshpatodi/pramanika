"""Builds the admin dashboard from the metrics repository (Phase 9 M2).
Read-only: it never writes and never touches stock."""

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.admin_metrics_repository import AdminMetricsRepository
from app.schemas.admin_dashboard import (
    CustomerMetrics,
    DashboardResponse,
    OrderMetrics,
    ProductMetrics,
    RecentOrder,
    RevenueMetrics,
)

WINDOW_DAYS = 30
RECENT_ORDERS_LIMIT = 10
CURRENCY = "INR"


def _money(value: Decimal) -> float:
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class AdminDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.metrics = AdminMetricsRepository(db)

    def build(self, now: Optional[datetime] = None) -> DashboardResponse:
        now = now or datetime.now(timezone.utc)
        since = now - timedelta(days=WINDOW_DAYS)

        by_status = self.metrics.order_counts_by_status()
        customers_total, customers_recent = self.metrics.customer_counts(since)
        revenue = self.metrics.revenue(since)
        recent = self.metrics.recent_orders(RECENT_ORDERS_LIMIT)

        return DashboardResponse(
            generated_at=now,
            orders=OrderMetrics(total=sum(by_status.values()), by_status=by_status),
            customers=CustomerMetrics(total=customers_total, new_last_30_days=customers_recent),
            products=ProductMetrics(**self.metrics.product_counts()),
            revenue=RevenueMetrics(
                currency=CURRENCY,
                all_time=_money(revenue["all_time"]),
                all_time_orders=revenue["all_time_orders"],
                last_30_days=_money(revenue["last_30_days"]),
                last_30_days_orders=revenue["last_30_days_orders"],
            ),
            recent_orders=[
                RecentOrder(
                    id=order.id,
                    order_number=order.order_number,
                    customer_name=name.strip(),
                    customer_email=email,
                    total_amount=_money(order.total_amount),
                    status=order.status.value,
                    payment_status=order.payment_status.value,
                    created_at=order.created_at,
                )
                for order, email, name in recent
            ],
        )
