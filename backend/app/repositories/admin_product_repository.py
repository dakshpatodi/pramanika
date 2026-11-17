"""Admin product queries (Phase 9 M3): one filtered/sorted/paged query with the
category and stock joined in (no per-row queries), plus the lock helpers."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, contains_eager

from app.models import Category, Inventory, Product
from app.repositories.admin_category_repository import like_pattern
from app.schemas.admin_catalog import AdminProductSort, SortOrder, StockFilter

_AVAILABLE = func.coalesce(Inventory.quantity - Inventory.reserved_quantity, 0)
_THRESHOLD = func.coalesce(Inventory.low_stock_threshold, 0)


class AdminProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def _joined(self, stmt):
        return stmt.join(Category, Category.id == Product.category_id).outerjoin(
            Inventory, Inventory.product_id == Product.id
        )

    def conditions(self, search, category_id, is_active, stock: Optional[StockFilter]) -> list:
        """The shared filter set (also used by the inventory list)."""
        return self._conditions(search, category_id, is_active, stock)

    def _conditions(self, search, category_id, is_active, stock: Optional[StockFilter]) -> list:
        conditions = []
        if search:
            pattern = like_pattern(search)
            conditions.append(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.sku.ilike(pattern, escape="\\"),
                    Product.slug.ilike(pattern, escape="\\"),
                )
            )
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        if is_active is not None:
            conditions.append(Product.is_active.is_(is_active))
        if stock == StockFilter.OUT:
            conditions.append(_AVAILABLE <= 0)
        elif stock == StockFilter.LOW:
            conditions.append(and_(_AVAILABLE > 0, _AVAILABLE <= _THRESHOLD))
        elif stock == StockFilter.OK:
            conditions.append(_AVAILABLE > _THRESHOLD)
        return conditions

    def list(
        self, *, search, category_id, is_active, stock, sort: AdminProductSort, order: SortOrder, page: int, page_size: int
    ) -> Tuple[List[Product], int]:
        conditions = self._conditions(search, category_id, is_active, stock)
        total = self.db.execute(self._joined(select(func.count(Product.id))).where(*conditions)).scalar_one()

        column = {
            AdminProductSort.CREATED_AT: Product.created_at,
            AdminProductSort.UPDATED_AT: Product.updated_at,
            AdminProductSort.NAME: func.lower(Product.name),
            AdminProductSort.SKU: Product.sku,
            AdminProductSort.PRICE: Product.price,
            AdminProductSort.AVAILABLE: _AVAILABLE,
        }[sort]
        direction = column.desc() if order == SortOrder.DESC else column.asc()
        stmt = (
            self._joined(select(Product))
            .options(contains_eager(Product.category), contains_eager(Product.inventory))
            .where(*conditions)
            .order_by(direction, Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.execute(stmt).unique().scalars().all()), total

    def get(self, product_id: uuid.UUID, *, lock: bool = False) -> Optional[Product]:
        """With `lock=True` the PRODUCT row is taken FOR UPDATE (checkout takes a
        share lock on the same row, so the two cannot interleave)."""
        if lock:
            return self.db.execute(
                select(Product)
                .where(Product.id == product_id)
                .with_for_update()
                .execution_options(populate_existing=True)  # fresh values after waiting for the lock
            ).scalar_one_or_none()
        stmt = (
            self._joined(select(Product))
            .options(contains_eager(Product.category), contains_eager(Product.inventory))
            .where(Product.id == product_id)
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def sku_taken(self, sku: str, *, exclude: Optional[uuid.UUID] = None) -> bool:
        return self._exists(func.lower(Product.sku) == sku.lower(), exclude)

    def slug_taken(self, slug: str, *, exclude: Optional[uuid.UUID] = None) -> bool:
        return self._exists(Product.slug == slug, exclude)

    def _exists(self, condition, exclude: Optional[uuid.UUID]) -> bool:
        query = select(Product.id).where(condition)
        if exclude is not None:
            query = query.where(Product.id != exclude)
        return self.db.execute(query.limit(1)).first() is not None
