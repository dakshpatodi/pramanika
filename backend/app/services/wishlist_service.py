"""
Wishlist business logic (Phase 8).

The owner is always the authenticated user's id handed in by the router. The
wishlist is bounded (MAX_WISHLIST_ITEMS), adding is idempotent, and removing
is idempotent: repeating either is safe and never an error, which is what a
heart button that gets double-clicked needs.
"""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy.orm import Session

from app.core.exceptions import ProductUnavailableError, WishlistFullError
from app.models import WishlistItem
from app.repositories.wishlist_repository import WishlistRepository
from app.schemas.product import PaginationMeta
from app.schemas.wishlist import WishlistItemResponse, WishlistListResponse, WishlistProductIdsResponse
from app.services.product_service import _compute_stock_flags  # the catalogue's own stock rule

MAX_WISHLIST_ITEMS = 100


@dataclass
class AddResult:
    item: WishlistItemResponse
    created: bool


def to_item_response(item: WishlistItem) -> WishlistItemResponse:
    product = item.product
    if product.is_active:
        in_stock, low_stock = _compute_stock_flags(product)
    else:
        in_stock = low_stock = False  # it cannot be bought, whatever the shelf says
    return WishlistItemResponse(
        product_id=product.id,
        name=product.name,
        slug=product.slug,
        price=product.price,
        compare_at_price=product.compare_at_price,
        image_url=product.image_url,
        is_available=product.is_active,
        in_stock=in_stock,
        low_stock=low_stock,
        added_at=item.created_at,
    )


class WishlistService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = WishlistRepository(db)

    def list_items(self, user_id: uuid.UUID, *, page: int, page_size: int) -> WishlistListResponse:
        items, total = self.repository.list_page(user_id, page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return WishlistListResponse(
            items=[to_item_response(i) for i in items],
            pagination=PaginationMeta(
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    def product_ids(self, user_id: uuid.UUID) -> WishlistProductIdsResponse:
        return WishlistProductIdsResponse(product_ids=self.repository.product_ids(user_id))

    def add(self, user_id: uuid.UUID, product_id: uuid.UUID) -> AddResult:
        """Save a product. Already saved: nothing changes and `created` is False.
        A product that is out of stock CAN be saved (that is what a wishlist is
        for); one that does not exist or is deactivated cannot.

        Raises:
            ProductUnavailableError: no such product, or it has been deactivated.
            WishlistFullError: the wishlist already holds MAX_WISHLIST_ITEMS.
        """
        with self._transaction():
            self.repository.lock_owner(user_id)
            if self.repository.get_active_product(product_id) is None:
                raise ProductUnavailableError()
            wishlist = self.repository.get_or_create(user_id)

            created = False
            if not self.repository.has_item(wishlist.id, product_id):
                if self.repository.count_items(wishlist.id) >= MAX_WISHLIST_ITEMS:
                    raise WishlistFullError(MAX_WISHLIST_ITEMS)
                created = self.repository.add_item(wishlist.id, product_id)

        item = self.repository.get_item(user_id, product_id)
        return AddResult(item=to_item_response(item), created=created)

    def remove(self, user_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        """Take a product off the wishlist. True if it was there, False if it
        was not (not an error: removing twice is harmless). Works for a product
        that has since been deactivated, so such rows can always be cleared."""
        with self._transaction():
            removed = self.repository.remove_item(user_id, product_id) > 0
        return removed

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
