"""
Admin order queries (Phase 9 M5). Reads never write or lock; the single write
is one conditional UPDATE (the rule sits in its WHERE clause, as in Phase 6/7).
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Order, OrderInventoryState, OrderItem, OrderPaymentStatus, OrderStatus, User
from app.repositories.admin_category_repository import like_pattern
from app.schemas.admin_catalog import SortOrder
from app.schemas.admin_orders import AdminOrderSort


class AdminOrdersRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        *,
        status: Optional[OrderStatus],
        payment_status: Optional[OrderPaymentStatus],
        inventory_state: Optional[OrderInventoryState],
        search: Optional[str],
        created_from: Optional[datetime],
        created_to: Optional[datetime],
        sort: AdminOrderSort,
        order: SortOrder,
        page: int,
        page_size: int,
    ) -> Tuple[List[Tuple[Order, User, int]], int]:
        """(order, customer, units) rows for one page, and the total count."""
        conditions = []
        if status is not None:
            conditions.append(Order.status == status)
        if payment_status is not None:
            conditions.append(Order.payment_status == payment_status)
        if inventory_state is not None:
            conditions.append(Order.inventory_state == inventory_state)
        if created_from is not None:
            conditions.append(Order.created_at >= created_from)
        if created_to is not None:
            conditions.append(Order.created_at <= created_to)
        if search:
            pattern = like_pattern(search)
            full_name = func.concat(User.first_name, " ", User.last_name)
            conditions.append(
                or_(
                    *[
                        column.ilike(pattern, escape="\\")
                        for column in (
                            Order.order_number,
                            User.email,
                            User.phone_number,
                            full_name,
                            Order.shipping_full_name,
                            Order.shipping_phone_number,
                        )
                    ]
                )
            )

        joined = Order.user_id == User.id
        total = self.db.execute(
            select(func.count(Order.id)).select_from(Order).join(User, joined).where(*conditions)
        ).scalar_one()

        units = (
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .where(OrderItem.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )
        column = {
            AdminOrderSort.CREATED_AT: Order.created_at,
            AdminOrderSort.TOTAL: Order.total_amount,
            AdminOrderSort.STATUS: Order.status,
            AdminOrderSort.ORDER_NUMBER: Order.order_number,
        }[sort]
        direction = column.desc() if order == SortOrder.DESC else column.asc()
        rows = self.db.execute(
            select(Order, User, units.label("units"))
            .join(User, joined)
            .where(*conditions)
            .order_by(direction, Order.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(o, u, int(n)) for o, u, n in rows], total

    def get_detail(self, order_id: uuid.UUID) -> Optional[Order]:
        return (
            self.db.execute(
                select(Order)
                .options(joinedload(Order.user), selectinload(Order.items), selectinload(Order.payments))
                .where(Order.id == order_id)
                .execution_options(populate_existing=True)
            )
            .unique()
            .scalar_one_or_none()
        )

    def lock(self, order_id: uuid.UUID) -> Optional[Order]:
        """The order row FOR UPDATE - the same row the payment and expiry paths lock."""
        return self.db.execute(
            select(Order).where(Order.id == order_id).with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def advance_status(self, order_id: uuid.UUID, current: OrderStatus, new: OrderStatus) -> bool:
        """status = new, only if the order is still `current`, paid and consumed."""
        result = self.db.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status == current,
                Order.payment_status == OrderPaymentStatus.PAID,
                Order.inventory_state == OrderInventoryState.CONSUMED,
            )
            .values(status=new)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
