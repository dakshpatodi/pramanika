"""
Product repository - the only place that writes SQLAlchemy queries
against Product/Category/Inventory for the customer-facing catalogue.
"""

from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session, joinedload

from app.models import Category, Product
from app.schemas.product import ProductSort


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self) -> Query:
        # joinedload for both category (many-to-one) and inventory
        # (one-to-one) - neither duplicates rows, so this is safe to
        # combine with pagination/counting without special-casing.
        # Avoids N+1: without this, rendering N products would fire N
        # additional queries just to read each one's category/stock.
        return (
            self.db.query(Product)
            .join(Category, Product.category_id == Category.id)
            .options(joinedload(Product.category), joinedload(Product.inventory))
            .filter(Product.is_active.is_(True))
        )

    def _apply_filters(
        self,
        query: Query,
        search: Optional[str],
        category_slug: Optional[str],
        min_price: Optional[float],
        max_price: Optional[float],
    ) -> Query:
        """Shared by both the paginated list query and its matching count
        query (see list_products below) - the two can never accidentally
        drift out of sync with each other's filters, since they both
        call this same method."""
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Product.name.ilike(pattern),
                    Product.short_description.ilike(pattern),
                    Product.description.ilike(pattern),
                    Product.sku.ilike(pattern),
                )
            )
        if category_slug:
            query = query.filter(Category.slug == category_slug)
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        return query

    def list_products(
        self,
        *,
        search: Optional[str] = None,
        category_slug: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        sort: ProductSort = ProductSort.NEWEST,
        offset: int = 0,
        limit: int = 12,
    ) -> Tuple[List[Product], int]:
        """Returns (page_of_products, total_matching_count).

        Pagination happens entirely at the database level via
        .offset()/.limit() - the full result set is never loaded into
        Python just to slice it.
        """
        filtered = self._apply_filters(
            self._base_query(), search, category_slug, min_price, max_price
        )

        total = filtered.count()

        if sort == ProductSort.PRICE_ASC:
            filtered = filtered.order_by(Product.price.asc())
        elif sort == ProductSort.PRICE_DESC:
            filtered = filtered.order_by(Product.price.desc())
        elif sort == ProductSort.NAME_ASC:
            filtered = filtered.order_by(Product.name.asc())
        elif sort == ProductSort.NAME_DESC:
            filtered = filtered.order_by(Product.name.desc())
        else:  # NEWEST
            filtered = filtered.order_by(Product.created_at.desc())

        products = filtered.offset(offset).limit(limit).all()
        return products, total

    def get_by_slug(self, slug: str) -> Optional[Product]:
        return (
            self.db.query(Product)
            .options(joinedload(Product.category), joinedload(Product.inventory))
            .filter(Product.slug == slug, Product.is_active.is_(True))
            .first()
        )

    def get_related(self, product: Product, limit: int = 4) -> List[Product]:
        """Same category, excludes the product itself, active only.
        Ordered by newest rather than random - a random ORDER BY is a
        genuinely expensive full-table-scan pattern in Postgres, and
        "keep related-products queries cheap" was explicit in the brief.
        """
        return (
            self.db.query(Product)
            .options(joinedload(Product.category), joinedload(Product.inventory))
            .filter(
                Product.category_id == product.category_id,
                Product.id != product.id,
                Product.is_active.is_(True),
            )
            .order_by(Product.created_at.desc())
            .limit(limit)
            .all()
        )