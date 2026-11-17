"""Admin category queries (Phase 9 M3). Reads are single aggregate queries;
the lock helpers are what make category deactivation safe against a product
being created or moved into the category at the same moment."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Category, Product
from app.schemas.admin_catalog import AdminCategorySort, SortOrder


def like_pattern(text: str) -> str:
    """`%text%` with the user's own % _ \\ escaped, so searching for '50%' means '50%'."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class AdminCategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def _filters(self, search: Optional[str], is_active: Optional[bool]) -> list:
        conditions = []
        if search:
            pattern = like_pattern(search)
            conditions.append(or_(Category.name.ilike(pattern, escape="\\"), Category.slug.ilike(pattern, escape="\\")))
        if is_active is not None:
            conditions.append(Category.is_active.is_(is_active))
        return conditions

    def list(
        self, *, search, is_active, sort: AdminCategorySort, order: SortOrder, page: int, page_size: int
    ) -> Tuple[List[Tuple[Category, int, int]], int]:
        conditions = self._filters(search, is_active)
        total = self.db.execute(select(func.count()).select_from(Category).where(*conditions)).scalar_one()

        product_count = func.count(Product.id)
        active_count = func.count(Product.id).filter(Product.is_active.is_(True))
        sort_column = {
            AdminCategorySort.NAME: func.lower(Category.name),
            AdminCategorySort.CREATED_AT: Category.created_at,
            AdminCategorySort.PRODUCT_COUNT: product_count,
        }[sort]
        direction = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
        rows = self.db.execute(
            select(Category, product_count, active_count)
            .outerjoin(Product, Product.category_id == Category.id)
            .where(*conditions)
            .group_by(Category.id)
            .order_by(direction, Category.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(c, n, a) for c, n, a in rows], total

    def counts_for(self, category_id: uuid.UUID) -> Tuple[int, int]:
        return self.db.execute(
            select(func.count(Product.id), func.count(Product.id).filter(Product.is_active.is_(True))).where(
                Product.category_id == category_id
            )
        ).one()

    def get(self, category_id: uuid.UUID, *, lock: Optional[str] = None) -> Optional[Category]:
        """`lock='update'` (FOR UPDATE) or `'share'` (FOR SHARE) or none."""
        query = select(Category).where(Category.id == category_id)
        if lock == "update":
            query = query.with_for_update()
        elif lock == "share":
            query = query.with_for_update(read=True)
        return self.db.execute(query).scalar_one_or_none()

    def name_taken(self, name: str, *, exclude: Optional[uuid.UUID] = None) -> bool:
        return self._exists(func.lower(Category.name) == name.lower(), exclude)

    def slug_taken(self, slug: str, *, exclude: Optional[uuid.UUID] = None) -> bool:
        return self._exists(Category.slug == slug, exclude)

    def _exists(self, condition, exclude: Optional[uuid.UUID]) -> bool:
        query = select(Category.id).where(condition)
        if exclude is not None:
            query = query.where(Category.id != exclude)
        return self.db.execute(query.limit(1)).first() is not None
