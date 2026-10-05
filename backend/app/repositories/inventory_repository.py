"""
Inventory repository - the stock-changing statements for Phase 6.

Every change here is ONE conditional UPDATE, not a read followed by a
write. The condition lives in the WHERE clause, so PostgreSQL checks it
and applies the change atomically while holding the row lock: two
checkouts racing for the last unit are serialised by the database, the
second one finds the condition false, matches zero rows and is told
"no". There is no window between "is there enough?" and "take it".

Each method returns True if it changed a row, False if its condition did
not hold. None of them commits - the calling service owns the
transaction, so a reservation is undone together with everything else if
a later step of checkout fails.

Convention (unchanged from Phase 3): available = quantity - reserved_quantity.
"""

import uuid
from typing import Iterable, List, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Inventory, Product


class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def lock_products(self, product_ids: Iterable[uuid.UUID]) -> List[Product]:
        """Share-lock the given products (ascending id, so two checkouts
        never lock in opposite orders) and return them with fresh column
        values. While held, nobody can change a product's price or
        deactivate it - the prices checkout snapshots are the ones that
        are committed with the order. Other checkouts share the lock, so
        this never serialises buyers against each other."""
        ids = sorted(set(product_ids), key=lambda pid: pid.int)
        if not ids:
            return []
        return (
            self.db.query(Product)
            .filter(Product.id.in_(ids))
            .order_by(Product.id.asc())
            .with_for_update(read=True, of=Product)
            .populate_existing()
            .all()
        )

    def available(self, product_id: uuid.UUID) -> int:
        """Units that could be reserved right now (0 if there is no row)."""
        row: Optional[Inventory] = (
            self.db.query(Inventory)
            .filter(Inventory.product_id == product_id)
            .populate_existing()
            .first()
        )
        if row is None:
            return 0
        return max(row.quantity - row.reserved_quantity, 0)

    def try_reserve(self, product_id: uuid.UUID, quantity: int) -> bool:
        """reserved += quantity, only if that many units are still free."""
        result = self.db.execute(
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.quantity - Inventory.reserved_quantity >= quantity,
            )
            .values(reserved_quantity=Inventory.reserved_quantity + quantity)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def release(self, product_id: uuid.UUID, quantity: int) -> bool:
        """reserved -= quantity (order cancelled / payment failed). Physical
        stock is untouched - the units simply become available again."""
        result = self.db.execute(
            update(Inventory)
            .where(Inventory.product_id == product_id, Inventory.reserved_quantity >= quantity)
            .values(reserved_quantity=Inventory.reserved_quantity - quantity)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def consume(self, product_id: uuid.UUID, quantity: int) -> bool:
        """The reserved units are sold: quantity -= n AND reserved -= n in
        one statement, so `available` is unchanged by the sale itself (it
        was already deducted when the units were reserved)."""
        result = self.db.execute(
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.reserved_quantity >= quantity,
                Inventory.quantity >= quantity,
            )
            .values(
                quantity=Inventory.quantity - quantity,
                reserved_quantity=Inventory.reserved_quantity - quantity,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1