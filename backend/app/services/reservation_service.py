"""
Stock reservation lifecycle for orders.

    reserve()            checkout: take units out of `available`
    release_for_order()  order cancelled / payment failed: give them back
    consume_for_order()  payment confirmed (Phase 7): the units are sold

An order's reservation can end exactly one way. `release_for_order` and
`consume_for_order` both start with the same compare-and-set on
`Order.inventory_state` (RESERVED -> RELEASED / CONSUMED). Only the caller
that wins it touches stock; any other caller - a retry, a double click,
a concurrent request, or the opposite transition - gets False and changes
nothing. That is what makes a double release or a double consume
impossible, and why release-after-consume (or the reverse) is a no-op.

Nothing here commits. The caller owns the transaction, so a reservation
made during checkout disappears with the rest of the order if a later
step fails.

Deadlock safety: every method touches products in ascending id order, so
two transactions that each need A and B always lock A first.
"""

import uuid
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError
from app.models import Order, OrderInventoryState
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository

Line = Tuple[uuid.UUID, int]


class ReservationInvariantError(RuntimeError):
    """The books don't balance (e.g. releasing more than is reserved).
    Never expected; raising rolls the whole transaction back instead of
    letting stock numbers drift."""


def _merge(lines: Iterable[Line]) -> List[Line]:
    """One entry per product (quantities summed), in ascending id order."""
    totals: Dict[uuid.UUID, int] = defaultdict(int)
    for product_id, quantity in lines:
        if quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
        totals[product_id] += quantity
    return sorted(totals.items(), key=lambda pair: pair[0].int)


class ReservationService:
    def __init__(self, db: Session):
        self.db = db
        self.inventory = InventoryRepository(db)
        self.orders = OrderRepository(db)

    def reserve(self, lines: Iterable[Line]) -> None:
        """Reserve every line or raise. Raises `InsufficientStockError` for
        the first product that cannot be covered; the caller then rolls
        back, which also undoes the lines reserved before it."""
        for product_id, quantity in _merge(lines):
            if not self.inventory.try_reserve(product_id, quantity):
                raise InsufficientStockError(available=self.inventory.available(product_id))

    def release_for_order(self, order: Order) -> bool:
        """Give an order's reserved units back. True if this call did it,
        False if the reservation had already been released or consumed."""
        if not self.orders.claim_inventory_state(order.id, OrderInventoryState.RESERVED, OrderInventoryState.RELEASED):
            return False
        self.db.expire(order, ["inventory_state"])
        self.release_items(order)
        return True

    def consume_for_order(self, order: Order) -> bool:
        """Turn an order's reservation into sold stock (called once payment
        is confirmed). True if this call did it, False if it had already
        been consumed or released."""
        if not self.orders.claim_inventory_state(order.id, OrderInventoryState.RESERVED, OrderInventoryState.CONSUMED):
            return False
        self.db.expire(order, ["inventory_state"])
        self._apply(order, self.inventory.consume, "consume")
        return True

    def release_items(self, order: Order) -> None:
        """Release the order's units WITHOUT claiming the state first. Only
        for a caller that already won its own compare-and-set on the order
        (`OrderRepository.cancel_pending` does)."""
        self._apply(order, self.inventory.release, "release")

    def _apply(self, order: Order, operation: Callable[[uuid.UUID, int], bool], verb: str) -> None:
        lines = [(item.product_id, item.quantity) for item in order.items if item.product_id is not None]
        for product_id, quantity in _merge(lines):
            if not operation(product_id, quantity):
                raise ReservationInvariantError(
                    f"Cannot {verb} {quantity} unit(s) of product {product_id} for order {order.id}: "
                    "stock numbers do not match the reservation."
                )