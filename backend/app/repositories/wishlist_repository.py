"""
Wishlist repository - every query that touches wishlists / wishlist_items.

Every read and write is scoped by the owner's `user_id` in the same query, so a
product on someone else's wishlist is indistinguishable from one that is not
there. Like the other repositories it only stages changes; the service commits.
"""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.models import Product, User, Wishlist, WishlistItem


class WishlistRepository:
    def __init__(self, db: Session):
        self.db = db

    def lock_owner(self, user_id: uuid.UUID) -> None:
        """Serialise wishlist writes of ONE user (two tabs adding at once, the
        first-ever add creating the wishlist row). FOR NO KEY UPDATE conflicts
        with itself but not with the key-share locks that carts and orders take
        on the user row, so it never blocks shopping."""
        self.db.query(User.id).filter(User.id == user_id).with_for_update(key_share=True).first()

    def get_active_product(self, product_id: uuid.UUID) -> Optional[Product]:
        return self.db.query(Product).filter(Product.id == product_id, Product.is_active.is_(True)).first()

    def get_or_create(self, user_id: uuid.UUID) -> Wishlist:
        """The user's wishlist, created on first use. Call under `lock_owner`:
        `wishlists.user_id` is unique, so two creators would otherwise collide."""
        wishlist = self.db.query(Wishlist).filter(Wishlist.user_id == user_id).first()
        if wishlist is None:
            wishlist = Wishlist(user_id=user_id)
            self.db.add(wishlist)
            self.db.flush()
        return wishlist

    def count_items(self, wishlist_id: uuid.UUID) -> int:
        return self.db.query(func.count(WishlistItem.id)).filter(WishlistItem.wishlist_id == wishlist_id).scalar() or 0

    def has_item(self, wishlist_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        return (
            self.db.query(WishlistItem.id)
            .filter(WishlistItem.wishlist_id == wishlist_id, WishlistItem.product_id == product_id)
            .first()
            is not None
        )

    def add_item(self, wishlist_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        """INSERT ... ON CONFLICT DO NOTHING on (wishlist, product). True if a
        row was added, False if it was already there - never an error, so a
        double click or a race cannot create a duplicate or fail."""
        result = self.db.execute(
            pg_insert(WishlistItem)
            .values(id=uuid.uuid4(), wishlist_id=wishlist_id, product_id=product_id)
            .on_conflict_do_nothing(constraint="uq_wishlist_items_wishlist_id_product_id")
            .returning(WishlistItem.id)
        )
        return result.first() is not None

    def remove_item(self, user_id: uuid.UUID, product_id: uuid.UUID) -> int:
        """Remove one product from THIS user's wishlist; returns the row count
        (0 if it was not there). One statement, owner-scoped."""
        owned = select(Wishlist.id).where(Wishlist.user_id == user_id).scalar_subquery()
        result = self.db.execute(
            delete(WishlistItem)
            .where(WishlistItem.wishlist_id == owned, WishlistItem.product_id == product_id)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount

    def list_page(self, user_id: uuid.UUID, *, page: int, page_size: int) -> Tuple[List[WishlistItem], int]:
        """Most recently added first. Product and inventory come in the same
        query, not one query per row."""
        base = (
            self.db.query(WishlistItem)
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .filter(Wishlist.user_id == user_id)
        )
        total = base.with_entities(func.count(WishlistItem.id)).scalar() or 0
        items = (
            base.options(joinedload(WishlistItem.product).joinedload(Product.inventory))
            .populate_existing()  # always today's price, stock and active flag, never a cached copy
            .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_item(self, user_id: uuid.UUID, product_id: uuid.UUID) -> Optional[WishlistItem]:
        return (
            self.db.query(WishlistItem)
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .filter(Wishlist.user_id == user_id, WishlistItem.product_id == product_id)
            .options(joinedload(WishlistItem.product).joinedload(Product.inventory))
            .populate_existing()
            .first()
        )

    def product_ids(self, user_id: uuid.UUID) -> List[uuid.UUID]:
        rows = (
            self.db.query(WishlistItem.product_id)
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .filter(Wishlist.user_id == user_id)
            .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
            .all()
        )
        return [r[0] for r in rows]
