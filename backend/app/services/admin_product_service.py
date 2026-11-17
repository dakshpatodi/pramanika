"""
Admin product management (Phase 9 M3).

Rules:
  - SKU is stored upper-case and compared case-insensitively; SKU and slug are
    unique. A taken slug is refused, never auto-suffixed. Slug may be edited
    (the public URL changes with it).
  - The category must exist and be ACTIVE (on create, on move, and on
    activation) - together with the category service this keeps "an inactive
    category never holds an active product", which the public shop relies on.
  - Creating a product also creates its inventory row (1:1) in the same
    transaction. Editing never touches stock: quantities change only through
    the inventory endpoints. Activation/deactivation are separate, idempotent
    actions with their own audit entries.
  - Every edit takes the product row FOR UPDATE (checkout takes a share lock on
    the same row) and changes only the fields that differ; a no-op edit writes
    nothing and audits nothing.
  - Deactivating hides the product from the shop and blocks new carts/checkouts
    for it (existing cart lines are flagged unavailable by the cart rules);
    orders and reservations already made are unaffected.
"""

import math
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import AdminConflictError, AdminValidationError, ProductNotFoundError
from app.models import Category, Inventory, Product, User
from app.repositories.admin_category_repository import AdminCategoryRepository
from app.repositories.admin_product_repository import AdminProductRepository
from app.schemas.admin_catalog import (
    AdminCategoryRef,
    AdminProductDetail,
    AdminProductListResponse,
    ProductCreate,
    ProductUpdate,
)
from app.schemas.product import PaginationMeta
from app.services.admin_common import admin_transaction, audit_value, snapshot
from app.services.audit_service import AuditService
from app.services.catalog_rules import slugify, stock_status

EDITABLE_FIELDS = (
    "category_id", "name", "slug", "sku", "price", "compare_at_price", "short_description", "description",
    "weight", "weight_unit", "ingredients", "nutritional_information", "image_url",
)
AUDITED_ON_CREATE = EDITABLE_FIELDS + ("is_active",)
CONFLICT_LABELS = {"sku": "sku", "slug": "slug"}


def _plain(value: Any) -> Any:
    """Audit/compare-friendly: enums as their value, Decimals as text."""
    if hasattr(value, "value") and not isinstance(value, (str, int, float)):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return audit_value(value)


class AdminProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminProductRepository(db)
        self.categories = AdminCategoryRepository(db)
        self.audit = AuditService(db)

    # ---- reads
    def list(self, *, search, category_id, is_active, stock, sort, order, page, page_size) -> AdminProductListResponse:
        products, total = self.repository.list(
            search=search, category_id=category_id, is_active=is_active, stock=stock,
            sort=sort, order=order, page=page, page_size=page_size,
        )
        pages = math.ceil(total / page_size) if total else 0
        return AdminProductListResponse(
            products=[self._detail(p) for p in products],
            pagination=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=pages,
                has_next=page < pages, has_previous=page > 1,
            ),
        )

    def get(self, product_id: uuid.UUID) -> AdminProductDetail:
        product = self.repository.get(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        return self._detail(product)

    # ---- writes
    def create(self, admin: User, payload: ProductCreate) -> AdminProductDetail:
        slug = payload.slug or slugify(payload.name)
        if not slug:
            raise AdminValidationError("slug: could not be made from the name; please provide one.")
        with admin_transaction(self.db, conflict_labels=CONFLICT_LABELS):
            category = self._usable_category(payload.category_id)
            self._ensure_unique(sku=payload.sku, slug=slug)
            product = Product(
                category_id=category.id, name=payload.name, slug=slug, sku=payload.sku, price=payload.price,
                compare_at_price=payload.compare_at_price, short_description=payload.short_description,
                description=payload.description, weight=payload.weight, weight_unit=payload.weight_unit,
                ingredients=payload.ingredients, nutritional_information=payload.nutritional_information,
                image_url=payload.image_url, is_active=payload.is_active,
            )
            self.db.add(product)
            self.db.flush()
            self.db.add(
                Inventory(
                    product_id=product.id, quantity=payload.initial_quantity, reserved_quantity=0,
                    low_stock_threshold=payload.low_stock_threshold,
                )
            )
            self.db.flush()
            after = {f: _plain(v) for f, v in snapshot(product, AUDITED_ON_CREATE).items()}
            after.update(initial_quantity=payload.initial_quantity, low_stock_threshold=payload.low_stock_threshold)
            self.audit.record(
                admin=admin, action="product.create", entity_type="product", entity_id=product.id, after=after
            )
            product_id = product.id
        return self.get(product_id)

    def update(self, admin: User, product_id: uuid.UUID, payload: ProductUpdate) -> AdminProductDetail:
        with admin_transaction(self.db, conflict_labels=CONFLICT_LABELS):
            product = self._require_locked(product_id)
            sent = {f: getattr(payload, f) for f in payload.model_fields_set}
            changes = {f: v for f, v in sent.items() if getattr(product, f) != v}
            if changes:
                merged = {f: changes.get(f, getattr(product, f)) for f in EDITABLE_FIELDS}
                self._check_merged(merged)
                if "category_id" in changes and product.is_active:
                    self._usable_category(changes["category_id"])
                elif "category_id" in changes:
                    self._existing_category(changes["category_id"])
                self._ensure_unique(sku=changes.get("sku"), slug=changes.get("slug"), exclude=product.id)
                before = {f: _plain(getattr(product, f)) for f in changes}
                for field, value in changes.items():
                    setattr(product, field, value)
                self.db.flush()
                self.audit.record(
                    admin=admin, action="product.update", entity_type="product", entity_id=product.id,
                    before=before, after={f: _plain(v) for f, v in changes.items()},
                )
        return self.get(product_id)

    def set_active(self, admin: User, product_id: uuid.UUID, active: bool) -> AdminProductDetail:
        with admin_transaction(self.db):
            product = self._require_locked(product_id)
            if product.is_active != active:
                if active:
                    self._usable_category(product.category_id, activating=True)
                product.is_active = active
                self.db.flush()
                self.audit.record(
                    admin=admin, action="product.activate" if active else "product.deactivate",
                    entity_type="product", entity_id=product.id,
                    before={"is_active": not active}, after={"is_active": active},
                )
        return self.get(product_id)

    # ---- helpers
    def _require_locked(self, product_id: uuid.UUID) -> Product:
        product = self.repository.get(product_id, lock=True)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        return product

    def _existing_category(self, category_id: uuid.UUID, *, lock: Optional[str] = None) -> Category:
        category = self.categories.get(category_id, lock=lock)
        if category is None:
            raise AdminValidationError("category_id: that category does not exist.")
        return category

    def _usable_category(self, category_id: uuid.UUID, *, activating: bool = False) -> Category:
        """An ACTIVE category, share-locked so it cannot be deactivated before we commit."""
        category = self._existing_category(category_id, lock="share")
        if not category.is_active:
            if activating:
                raise AdminConflictError("Activate the product's category first; it is inactive.")
            raise AdminValidationError("category_id: that category is inactive. Activate it or pick another.")
        return category

    def _ensure_unique(self, *, sku: Optional[str], slug: Optional[str], exclude: Optional[uuid.UUID] = None) -> None:
        if sku is not None and self.repository.sku_taken(sku, exclude=exclude):
            raise AdminConflictError(f"sku: '{sku}' is already used by another product.")
        if slug is not None and self.repository.slug_taken(slug, exclude=exclude):
            raise AdminConflictError(f"slug: '{slug}' is already used by another product.")

    @staticmethod
    def _check_merged(values: Dict[str, Any]) -> None:
        price, compare = values["price"], values["compare_at_price"]
        if compare is not None and compare <= price:
            raise AdminValidationError("compare_at_price: must be greater than price.")
        if (values["weight"] is None) != (values["weight_unit"] is None):
            raise AdminValidationError("weight: weight and weight_unit must be given together.")

    @staticmethod
    def _detail(product: Product) -> AdminProductDetail:
        inventory = product.inventory
        quantity = inventory.quantity if inventory else 0
        reserved = inventory.reserved_quantity if inventory else 0
        threshold = inventory.low_stock_threshold if inventory else None
        category = product.category
        return AdminProductDetail(
            id=product.id, name=product.name, slug=product.slug, sku=product.sku,
            price=float(product.price),
            compare_at_price=float(product.compare_at_price) if product.compare_at_price is not None else None,
            image_url=product.image_url, is_active=product.is_active,
            category=AdminCategoryRef(id=category.id, name=category.name, slug=category.slug, is_active=category.is_active),
            quantity=quantity, reserved_quantity=reserved, available_quantity=quantity - reserved,
            low_stock_threshold=threshold,
            stock_status=stock_status(inventory.quantity if inventory else None, reserved, threshold),
            created_at=product.created_at, updated_at=product.updated_at,
            short_description=product.short_description, description=product.description,
            weight=float(product.weight) if product.weight is not None else None,
            weight_unit=product.weight_unit.value if product.weight_unit is not None else None,
            ingredients=product.ingredients, nutritional_information=product.nutritional_information,
        )
