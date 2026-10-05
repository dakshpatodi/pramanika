"""
Order repository.

Like the other repositories it only stages changes; the service owns
commit / rollback. Customer-facing lookups are always scoped by
`user_id` in the query itself, so an order that belongs to someone else
is indistinguishable from one that does not exist.

The two `UPDATE ... WHERE` methods at the bottom are compare-and-set
gates. They are what turns "release the stock" / "restore the coupon"
into things that can happen at most once per order: the first caller
flips the state and gets True, every later (or concurrent) caller finds
the condition false and gets False.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import Order, OrderInventoryState, OrderPaymentStatus, OrderStatus
from app.models.order import order_number_seq
from app.services.order_rules import format_order_number


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- creation ---------------------------------------------------------

    def next_order_number(self, now: datetime) -> str:
        """PRM-<year>-<6 digit sequence>. The sequence is a database
        object, so concurrent checkouts always get different numbers."""
        value = self.db.execute(select(order_number_seq.next_value())).scalar_one()
        return format_order_number(now.year, int(value))

    def add(self, order: Order) -> Order:
        self.db.add(order)
        self.db.flush()  # assigns ids and fires the unique-key checks, no commit
        return order

    # --- reads (always scoped to the owner) -------------------------------

    def get_for_user(self, order_id: uuid.UUID, user_id: uuid.UUID, *, for_update: bool = False) -> Optional[Order]:
        query = (
            self.db.query(Order)
            .options(selectinload(Order.items))
            .filter(Order.id == order_id, Order.user_id == user_id)
        )
        if for_update:
            query = query.with_for_update(of=Order).populate_existing()
        return query.first()

    def get_by_idempotency_key(self, user_id: uuid.UUID, key: str) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(selectinload(Order.items))
            .filter(Order.user_id == user_id, Order.idempotency_key == key)
            .populate_existing()
            .first()
        )

    def list_for_user(self, user_id: uuid.UUID, *, page: int, page_size: int) -> Tuple[List[Order], int]:
        """Newest first. Items are loaded in one extra query, not per order."""
        base = self.db.query(Order).filter(Order.user_id == user_id)
        total = base.with_entities(func.count(Order.id)).scalar() or 0
        orders = (
            base.options(selectinload(Order.items))
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return orders, total

    # --- compare-and-set gates --------------------------------------------

    def claim_inventory_state(
        self, order_id: uuid.UUID, from_state: OrderInventoryState, to_state: OrderInventoryState
    ) -> bool:
        """Move the reservation state only if it is currently `from_state`.
        True for exactly one caller, however many race."""
        result = self.db.execute(
            update(Order)
            .where(Order.id == order_id, Order.inventory_state == from_state)
            .values(inventory_state=to_state)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def cancel_pending(self, order_id: uuid.UUID, now: datetime) -> bool:
        """Cancel an order that is still unpaid AND still holds its
        reservation, and mark the reservation released - one atomic
        statement. True for exactly one caller; a second cancel (double
        click, retry) finds nothing to change."""
        result = self.db.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status == OrderStatus.PENDING,
                Order.payment_status == OrderPaymentStatus.PENDING,
                Order.inventory_state == OrderInventoryState.RESERVED,
            )
            .values(
                status=OrderStatus.CANCELLED,
                inventory_state=OrderInventoryState.RELEASED,
                cancelled_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1