"""
Admin inventory management (Phase 9 M4).

What an administrator may do to stock, and what is guaranteed:

  - VIEW: lists and details never write, lock or modify anything.
  - SET quantity (stock-take): needs `expected_quantity`, the value the admin
    saw. If a sale consumed units meanwhile the request is refused (409) rather
    than overwriting it.
  - ADJUST by +/-n (goods received, write-off): applied atomically to the
    current value, so concurrent adjustments never lose an update.
  - Neither may take quantity BELOW reserved_quantity: those units are promised
    to open orders (checkout, payment, expiry all depend on it). The refusal
    says how many are reserved. The database CHECK constraints are the last
    line of defence and any violation that slips through becomes the same 409.
  - Quantity can't exceed 1,000,000 or go negative.
  - `reserved_quantity` is never writable here; only checkout/payment/expiry
    move it (through InventoryRepository).
  - low_stock_threshold may be changed freely (>= 0).
  - Every change takes the inventory row FOR UPDATE, runs as conditional
    UPDATEs, and writes ONE audit row (changed fields before/after, method,
    optional reason) in the same transaction. A no-op writes nothing.
"""

import math
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import AdminConflictError, ProductNotFoundError
from app.models import Inventory, Product, User
from app.repositories.admin_inventory_repository import AdminInventoryRepository
from app.repositories.admin_product_repository import AdminProductRepository
from app.schemas.admin_catalog import AdminCategoryRef
from app.schemas.admin_inventory import (
    MAX_QUANTITY,
    AdminInventoryDetail,
    AdminInventoryItem,
    AdminInventoryListResponse,
    InventoryUpdate,
)
from app.schemas.product import PaginationMeta
from app.services.admin_common import admin_transaction
from app.services.audit_service import AuditService
from app.services.catalog_rules import stock_status

TRACKED = ("quantity", "low_stock_threshold")
CHECK_MESSAGES = {
    "reserved_within_quantity": "Stock cannot go below the units reserved by open orders. Refresh and try again.",
    "quantity_non_negative": "Stock cannot be negative.",
}


class AdminInventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminInventoryRepository(db)
        self.products = AdminProductRepository(db)
        self.audit = AuditService(db)

    # ---- reads
    def list(self, *, search, category_id, is_active, stock, sort, order, page, page_size) -> AdminInventoryListResponse:
        products, total = self.repository.list(
            search=search, category_id=category_id, is_active=is_active, stock=stock,
            sort=sort, order=order, page=page, page_size=page_size,
        )
        pages = math.ceil(total / page_size) if total else 0
        return AdminInventoryListResponse(
            items=[self._item(p) for p in products],
            pagination=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=pages,
                has_next=page < pages, has_previous=page > 1,
            ),
        )

    def get(self, product_id: uuid.UUID) -> AdminInventoryDetail:
        product = self.products.get(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        orders, units = self.repository.open_reservations(product_id)
        item = self._item(product)
        return AdminInventoryDetail(
            **item.model_dump(), open_order_count=orders, open_order_units=units,
            reservations_match=units == item.reserved_quantity,
        )

    # ---- write
    def update(self, admin: User, product_id: uuid.UUID, payload: InventoryUpdate) -> AdminInventoryDetail:
        with admin_transaction(self.db, check_messages=CHECK_MESSAGES):
            inventory = self.repository.lock(product_id) or self.repository.create_missing(product_id)
            if inventory is None:
                raise ProductNotFoundError(str(product_id))
            before = {f: getattr(inventory, f) for f in TRACKED}
            sent = payload.model_fields_set
            method: Optional[str] = None

            if "quantity" in sent:
                method = "set"
                self._set(inventory, payload.quantity, payload.expected_quantity)
            elif "adjust_by" in sent:
                method = "adjust"
                self._adjust(inventory, payload.adjust_by)
            if "low_stock_threshold" in sent and payload.low_stock_threshold != inventory.low_stock_threshold:
                self.repository.set_threshold(product_id, payload.low_stock_threshold)

            inventory = self.repository.lock(product_id)  # re-read under the same lock
            changed = {f: getattr(inventory, f) for f in TRACKED if getattr(inventory, f) != before[f]}
            if changed:
                after = dict(changed)
                if method:
                    after["method"] = method
                if method == "adjust":
                    after["adjust_by"] = payload.adjust_by
                if payload.reason:
                    after["reason"] = payload.reason
                self.audit.record(
                    admin=admin, action="inventory.update", entity_type="inventory", entity_id=product_id,
                    before={f: before[f] for f in changed}, after=after,
                )
        return self.get(product_id)

    # ---- helpers
    def _set(self, inventory: Inventory, new: int, expected: int) -> None:
        if inventory.quantity != expected:
            raise AdminConflictError(
                f"Stock changed since you loaded it (now {inventory.quantity}, you expected {expected}). "
                "Refresh and try again."
            )
        if new == inventory.quantity:
            return
        if not self.repository.set_quantity(inventory.product_id, expected, new):
            raise AdminConflictError(
                f"Cannot set stock to {new}: {inventory.reserved_quantity} unit(s) are reserved by open orders, "
                "and stock cannot go below the reserved amount."
            )

    def _adjust(self, inventory: Inventory, delta: int) -> None:
        if not self.repository.add_quantity(inventory.product_id, delta):
            target = inventory.quantity + delta
            if target > MAX_QUANTITY:
                raise AdminConflictError(f"Stock cannot exceed {MAX_QUANTITY:,} units.")
            if target < 0:
                raise AdminConflictError(
                    f"Cannot remove {-delta} unit(s): only {inventory.quantity} in stock."
                )
            raise AdminConflictError(
                f"Cannot remove {-delta} unit(s): {inventory.reserved_quantity} of {inventory.quantity} are reserved "
                f"by open orders, so at most {inventory.quantity - inventory.reserved_quantity} can be removed."
            )

    @staticmethod
    def _item(product: Product) -> AdminInventoryItem:
        inv = product.inventory
        quantity = inv.quantity if inv else 0
        reserved = inv.reserved_quantity if inv else 0
        threshold = inv.low_stock_threshold if inv else None
        category = product.category
        return AdminInventoryItem(
            product_id=product.id, name=product.name, sku=product.sku, is_active=product.is_active,
            category=AdminCategoryRef(id=category.id, name=category.name, slug=category.slug, is_active=category.is_active),
            quantity=quantity, reserved_quantity=reserved, available_quantity=quantity - reserved,
            low_stock_threshold=threshold, stock_status=stock_status(inv.quantity if inv else None, reserved, threshold),
            updated_at=inv.updated_at if inv else product.updated_at,
        )
