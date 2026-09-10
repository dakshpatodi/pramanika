"""
Product business logic: listing (search/filter/sort/paginate), detail +
related products. Route handlers (api/products.py) stay thin and just
call into this.
"""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import ProductNotFoundError
from app.models import Product
from app.repositories.product_repository import ProductRepository
from app.schemas.product import PaginationMeta, ProductDetail, ProductListItem, ProductSort


def _compute_stock_flags(product: Product) -> Tuple[bool, bool]:
    """A product with no Inventory row (shouldn't normally happen given
    the 1:1 relationship established in Phase 3 - but never trust that
    blindly) is treated as out of stock rather than raising. "Can't
    confirm it's in stock" and "confirmed out of stock" should look the
    same to a customer either way."""
    inventory = product.inventory
    if inventory is None:
        return False, False

    available = inventory.quantity - inventory.reserved_quantity
    in_stock = available > 0
    threshold = inventory.low_stock_threshold or 0
    low_stock = in_stock and available <= threshold
    return in_stock, low_stock


def _to_list_item(product: Product) -> ProductListItem:
    in_stock, low_stock = _compute_stock_flags(product)
    return ProductListItem(
        id=product.id,
        name=product.name,
        slug=product.slug,
        sku=product.sku,
        price=product.price,
        compare_at_price=product.compare_at_price,
        image_url=product.image_url,
        category=product.category,
        in_stock=in_stock,
        low_stock=low_stock,
    )


class ProductService:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def list_products(
        self,
        *,
        search: Optional[str],
        category_slug: Optional[str],
        min_price: Optional[float],
        max_price: Optional[float],
        sort: ProductSort,
        page: int,
        page_size: int,
    ) -> Tuple[List[ProductListItem], PaginationMeta]:
        offset = (page - 1) * page_size
        products, total = self.repository.list_products(
            search=search,
            category_slug=category_slug,
            min_price=min_price,
            max_price=max_price,
            sort=sort,
            offset=offset,
            limit=page_size,
        )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        pagination = PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )
        return [_to_list_item(p) for p in products], pagination

    def get_product_detail(self, slug: str, related_limit: int = 4) -> ProductDetail:
        product = self.repository.get_by_slug(slug)
        if product is None:
            raise ProductNotFoundError(slug)

        in_stock, low_stock = _compute_stock_flags(product)
        related = self.repository.get_related(product, limit=related_limit)

        return ProductDetail(
            id=product.id,
            name=product.name,
            slug=product.slug,
            sku=product.sku,
            short_description=product.short_description,
            description=product.description,
            price=product.price,
            compare_at_price=product.compare_at_price,
            weight=product.weight,
            weight_unit=product.weight_unit,
            ingredients=product.ingredients,
            nutritional_information=product.nutritional_information,
            image_url=product.image_url,
            category=product.category,
            in_stock=in_stock,
            low_stock=low_stock,
            created_at=product.created_at,
            related_products=[_to_list_item(p) for p in related],
        )