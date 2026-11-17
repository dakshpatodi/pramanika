"""
Admin inventory queries and stock writes (Phase 9 M4).

Writes follow the Phase 6 convention: ONE conditional UPDATE whose WHERE clause
holds the rule, so the database checks and applies it atomically under the row
lock. Each returns True if a row changed, False if its condition did not hold.
None commits - the service owns the transaction.

  set_quantity   quantity = :new   WHERE quantity = :expected AND :new >= reserved
  add_quantity   quantity += :n    WHERE quantity + :n >= reserved AND <= MAX
                 (reserved >= 0 makes "not below zero" implicit)
  set_threshold  low_stock_threshold = :n
"""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, contains_eager

from app.models import Inventory, Order, OrderInventoryState, OrderItem, Product
from app.repositories.admin_product_repository import _AVAILABLE, AdminProductRepository
from app.schemas.admin_catalog import SortOrder
from app.schemas.admin_inventory import MAX_QUANTITY, InventorySortKey


class AdminInventoryRepository:
    def __init__(self, db: Session):
        self.db = db
        self.products = AdminProductRepository(db)

    # ---- reads (never write, never lock)
    def list(
        self, *, search, category_id, is_active, stock, sort: InventorySortKey, order: SortOrder, page: int, page_size: int
    ) -> Tuple[List[Product], int]:
        conditions = self.products.conditions(search, category_id, is_active, stock)
        total = self.db.execute(self.products._joined(select(func.count(Product.id))).where(*conditions)).scalar_one()
        column = {
            InventorySortKey.NAME: func.lower(Product.name),
            InventorySortKey.SKU: Product.sku,
            InventorySortKey.AVAILABLE: _AVAILABLE,
            InventorySortKey.QUANTITY: func.coalesce(Inventory.quantity, 0),
            InventorySortKey.UPDATED_AT: func.coalesce(Inventory.updated_at, Product.updated_at),
        }[sort]
        direction = column.desc() if order == SortOrder.DESC else column.asc()
        stmt = (
            self.products._joined(select(Product))
            .options(contains_eager(Product.category), contains_eager(Product.inventory))
            .where(*conditions)
            .order_by(direction, Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.execute(stmt).unique().scalars().all()), total

    def open_reservations(self, product_id: uuid.UUID) -> Tuple[int, int]:
        """(orders, units) currently holding a reservation on this product:
        orders whose stock is still 'reserved' (unpaid, not cancelled/expired)."""
        orders, units = self.db.execute(
            select(func.count(func.distinct(Order.id)), func.coalesce(func.sum(OrderItem.quantity), 0))
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id == product_id, Order.inventory_state == OrderInventoryState.RESERVED)
        ).one()
        return orders, int(units)

    # ---- locking
    def lock(self, product_id: uuid.UUID) -> Optional[Inventory]:
        return self.db.execute(
            select(Inventory)
            .where(Inventory.product_id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def create_missing(self, product_id: uuid.UUID) -> Optional[Inventory]:
        """A product with no inventory row (should not happen: creating a product
        creates one). Serialise on the PRODUCT row, re-check, then insert. None if
        the product itself does not exist."""
        product = self.db.execute(
            select(Product.id).where(Product.id == product_id).with_for_update()
        ).first()
        if product is None:
            return None
        existing = self.lock(product_id)
        if existing is not None:
            return existing
        row = Inventory(product_id=product_id, quantity=0, reserved_quantity=0, low_stock_threshold=10)
        self.db.add(row)
        self.db.flush()
        return row

    # ---- conditional writes
    def set_quantity(self, product_id: uuid.UUID, expected: int, new: int) -> bool:
        result = self.db.execute(
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.quantity == expected,
                Inventory.reserved_quantity <= new,
            )
            .values(quantity=new)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def add_quantity(self, product_id: uuid.UUID, delta: int) -> bool:
        result = self.db.execute(
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.quantity + delta >= Inventory.reserved_quantity,
                Inventory.quantity + delta <= MAX_QUANTITY,
            )
            .values(quantity=Inventory.quantity + delta)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def set_threshold(self, product_id: uuid.UUID, threshold: int) -> bool:
        result = self.db.execute(
            update(Inventory)
            .where(Inventory.product_id == product_id)
            .values(low_stock_threshold=threshold)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
