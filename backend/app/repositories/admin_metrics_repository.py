"""
Read-only aggregate queries behind the admin dashboard (Phase 9).

Every number is computed by the database (COUNT / SUM with FILTER, GROUP BY),
never by loading rows into Python. The whole dashboard is five small queries
whatever the size of the shop.

Definitions (also shown in the API docs and the dashboard's help text):

  orders        every order, counted once, by its fulfilment `status`
  customers     accounts whose role is `customer`
  products      all products; the stock figures count ACTIVE products only,
                using the shop's own rule: available = quantity - reserved,
                low stock = 0 < available <= low_stock_threshold (NULL = 0),
                out of stock = available <= 0 (no inventory row counts too)
  revenue       the `total_amount` (what the customer paid: goods + GST +
                delivery, after discounts) of orders whose payment_status is
                'paid' and whose status is not cancelled/refunded. Unpaid,
                failed, cancelled and refunded orders contribute nothing.
                "Last 30 days" is dated by when the payment was captured
                (the order's earliest captured Payment.paid_at; an order
                with no captured payment row falls back to its updated_at).
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Tuple

from sqlalchemy import Integer, and_, case, cast, func, select
from sqlalchemy.orm import Session

from app.models import (
    Inventory,
    Order,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus,
    Product,
    User,
    UserRole,
)

ZERO = Decimal("0.00")


class AdminMetricsRepository:
    def __init__(self, db: Session):
        self.db = db

    def order_counts_by_status(self) -> Dict[str, int]:
        rows = self.db.execute(select(Order.status, func.count(Order.id)).group_by(Order.status)).all()
        counts = {status.value: 0 for status in OrderStatus}
        for status, count in rows:
            counts[status.value] = count
        return counts

    def customer_counts(self, since: datetime) -> Tuple[int, int]:
        """(all customers, customers who registered on or after `since`)."""
        total, recent = self.db.execute(
            select(
                func.count(User.id),
                func.count(User.id).filter(User.created_at >= since),
            ).where(User.role == UserRole.CUSTOMER)
        ).one()
        return total, recent

    def product_counts(self) -> Dict[str, int]:
        available = func.coalesce(Inventory.quantity - Inventory.reserved_quantity, 0)
        threshold = func.coalesce(Inventory.low_stock_threshold, 0)
        row = self.db.execute(
            select(
                func.count(Product.id),
                func.count(Product.id).filter(Product.is_active.is_(True)),
                func.count(Product.id).filter(and_(Product.is_active.is_(True), available <= 0)),
                func.count(Product.id).filter(and_(Product.is_active.is_(True), available > 0, available <= threshold)),
            ).select_from(Product).outerjoin(Inventory, Inventory.product_id == Product.id)
        ).one()
        total, active, out_of_stock, low_stock = row
        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
        }

    def revenue(self, since: datetime) -> Dict[str, object]:
        first_paid = (
            select(Payment.order_id.label("order_id"), func.min(Payment.paid_at).label("paid_at"))
            .where(Payment.status == PaymentTransactionStatus.CAPTURED)
            .group_by(Payment.order_id)
            .subquery()
        )
        paid_at = func.coalesce(first_paid.c.paid_at, Order.updated_at)
        recent = paid_at >= since
        total, count, total_recent, count_recent = self.db.execute(
            select(
                func.coalesce(func.sum(Order.total_amount), ZERO),
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount).filter(recent), ZERO),
                func.count(Order.id).filter(recent),
            )
            .select_from(Order)
            .outerjoin(first_paid, first_paid.c.order_id == Order.id)
            .where(
                Order.payment_status == OrderPaymentStatus.PAID,
                Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.REFUNDED]),
            )
        ).one()
        return {
            "all_time": Decimal(total),
            "all_time_orders": count,
            "last_30_days": Decimal(total_recent),
            "last_30_days_orders": count_recent,
        }

    def recent_orders(self, limit: int) -> List[Tuple[Order, str, str]]:
        """Newest orders with the customer's email and name, in ONE query."""
        rows = self.db.execute(
            select(Order, User.email, func.concat(User.first_name, " ", User.last_name))
            .join(User, User.id == Order.user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
        ).all()
        return [(order, email, name) for order, email, name in rows]
