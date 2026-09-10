"""
Category repository - the only place that writes SQLAlchemy queries
against Category for the customer-facing catalogue.
"""

from typing import List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Category, Product


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active_with_product_counts(self) -> List[Tuple[Category, int]]:
        """Returns (category, active_product_count) pairs, ordered by name.

        One LEFT JOIN + GROUP BY, not N+1 per-category count queries -
        the product count is genuinely useful for a category browsing
        page ("Cereals (12)") and this is the only way to get it without
        looping over categories in Python.
        """
        rows = (
            self.db.query(Category, func.count(Product.id))
            .outerjoin(
                Product,
                and_(Product.category_id == Category.id, Product.is_active.is_(True)),
            )
            .filter(Category.is_active.is_(True))
            .group_by(Category.id)
            .order_by(Category.name.asc())
            .all()
        )
        return [(category, count) for category, count in rows]

    def get_by_slug(self, slug: str) -> Optional[Category]:
        return (
            self.db.query(Category)
            .filter(Category.slug == slug, Category.is_active.is_(True))
            .first()
        )