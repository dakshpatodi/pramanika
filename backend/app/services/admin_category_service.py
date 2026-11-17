"""
Admin category management (Phase 9 M3).

Rules:
  - name and slug are unique (name compared case-insensitively); slug is made
    from the name when not given; a taken slug is refused, never auto-suffixed.
  - NO hard delete. A category owns products (and orders' history points at
    them), so removal would orphan the catalogue. The safe alternative is
    deactivation, allowed only when the category has no ACTIVE products
    (deactivate or move them first); a deactivated category disappears from the
    public shop. Reactivation is always allowed.
  - Invariant kept for the public shop: an inactive category never holds an
    active product (the product service enforces the other half).
  - Every change is audited in the same transaction.
"""

import math
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import AdminConflictError, AdminValidationError, CategoryNotFoundError
from app.models import Category, User
from app.repositories.admin_category_repository import AdminCategoryRepository
from app.schemas.admin_catalog import (
    AdminCategoryItem,
    AdminCategoryListResponse,
    CategoryCreate,
    CategoryUpdate,
)
from app.schemas.product import PaginationMeta
from app.services.admin_common import admin_transaction, snapshot
from app.services.audit_service import AuditService
from app.services.catalog_rules import slugify

AUDITED_FIELDS = ("name", "slug", "description", "image_url", "is_active")
CONFLICT_LABELS = {"slug": "slug", "name": "name"}


class AdminCategoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminCategoryRepository(db)
        self.audit = AuditService(db)

    # ---- reads
    def list(self, *, search, is_active, sort, order, page, page_size) -> AdminCategoryListResponse:
        rows, total = self.repository.list(
            search=search, is_active=is_active, sort=sort, order=order, page=page, page_size=page_size
        )
        pages = math.ceil(total / page_size) if total else 0
        return AdminCategoryListResponse(
            categories=[self._item(c, n, a) for c, n, a in rows],
            pagination=PaginationMeta(
                total=total, page=page, page_size=page_size, total_pages=pages,
                has_next=page < pages, has_previous=page > 1,
            ),
        )

    def get(self, category_id: uuid.UUID) -> AdminCategoryItem:
        category = self._require(category_id)
        total, active = self.repository.counts_for(category.id)
        return self._item(category, total, active)

    # ---- writes
    def create(self, admin: User, payload: CategoryCreate) -> AdminCategoryItem:
        slug = payload.slug or slugify(payload.name)
        if not slug:
            raise AdminValidationError("slug: could not be made from the name; please provide one.")
        with admin_transaction(self.db, conflict_labels=CONFLICT_LABELS):
            self._ensure_unique(name=payload.name, slug=slug)
            category = Category(
                name=payload.name, slug=slug, description=payload.description,
                image_url=payload.image_url, is_active=payload.is_active,
            )
            self.db.add(category)
            self.db.flush()
            self.audit.record(
                admin=admin, action="category.create", entity_type="category", entity_id=category.id,
                after=snapshot(category, AUDITED_FIELDS),
            )
        return self.get(category.id)

    def update(self, admin: User, category_id: uuid.UUID, payload: CategoryUpdate) -> AdminCategoryItem:
        with admin_transaction(self.db, conflict_labels=CONFLICT_LABELS):
            category = self._require(category_id, lock="update")
            new_values = {f: getattr(payload, f) for f in payload.model_fields_set}
            changes = {f: v for f, v in new_values.items() if getattr(category, f) != v}
            if changes:
                self._ensure_unique(name=changes.get("name"), slug=changes.get("slug"), exclude=category.id)
                before = {f: getattr(category, f) for f in changes}
                for field, value in changes.items():
                    setattr(category, field, value)
                self.db.flush()
                self.audit.record(
                    admin=admin, action="category.update", entity_type="category", entity_id=category.id,
                    before=before, after=changes,
                )
        return self.get(category_id)

    def set_active(self, admin: User, category_id: uuid.UUID, active: bool) -> AdminCategoryItem:
        with admin_transaction(self.db):
            category = self._require(category_id, lock="update")
            if category.is_active != active:
                if not active:
                    _, active_products = self.repository.counts_for(category.id)
                    if active_products:
                        raise AdminConflictError(
                            f"{active_products} active product(s) still use this category. "
                            "Deactivate them or move them to another category first."
                        )
                category.is_active = active
                self.db.flush()
                self.audit.record(
                    admin=admin, action="category.activate" if active else "category.deactivate",
                    entity_type="category", entity_id=category.id,
                    before={"is_active": not active}, after={"is_active": active},
                )
        return self.get(category_id)

    # ---- helpers
    def _require(self, category_id: uuid.UUID, *, lock: Optional[str] = None) -> Category:
        category = self.repository.get(category_id, lock=lock)
        if category is None:
            raise CategoryNotFoundError(str(category_id))
        return category

    def _ensure_unique(self, *, name: Optional[str], slug: Optional[str], exclude: Optional[uuid.UUID] = None) -> None:
        if name is not None and self.repository.name_taken(name, exclude=exclude):
            raise AdminConflictError(f"name: a category named '{name}' already exists.")
        if slug is not None and self.repository.slug_taken(slug, exclude=exclude):
            raise AdminConflictError(f"slug: '{slug}' is already used by another category.")

    @staticmethod
    def _item(category: Category, total: int, active: int) -> AdminCategoryItem:
        return AdminCategoryItem(
            id=category.id, name=category.name, slug=category.slug, description=category.description,
            image_url=category.image_url, is_active=category.is_active, product_count=total,
            active_product_count=active, created_at=category.created_at, updated_at=category.updated_at,
        )
