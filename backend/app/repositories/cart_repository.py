"""
Cart repository - every query that touches carts / cart_items, plus the
product+inventory lookups the cart needs.

Like the other repositories it only stages changes (`add`, `delete`,
`flush`); the service owns commit / rollback.

Ownership: `get_item_for_user` resolves a cart item *through the cart's
user_id* in a single query, so an item id that belongs to someone else is
indistinguishable from one that does not exist. The service never has to
remember to compare owners.
"""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Cart, CartItem, Inventory, Product

CartLine = Tuple[CartItem, Product, Optional[Inventory]]


class CartRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- cart -------------------------------------------------------------

    def get_by_user_id(self, user_id: uuid.UUID, *, for_update: bool = False) -> Optional[Cart]:
        """`for_update=True` locks the cart row until the transaction ends,
        serialising concurrent mutations by the same user (e.g. a
        double-clicked Add to Cart) so they cannot race on the
        UNIQUE(cart_id, product_id) constraint."""
        query = self.db.query(Cart).filter(Cart.user_id == user_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def create(self, user_id: uuid.UUID) -> Cart:
        cart = Cart(user_id=user_id)
        self.db.add(cart)
        self.db.flush()  # assigns cart.id without committing
        return cart

    def set_coupon(self, cart: Cart, coupon_id: Optional[uuid.UUID]) -> Cart:
        cart.coupon_id = coupon_id
        self.db.add(cart)
        return cart

    # --- lines ------------------------------------------------------------

    def get_lines(self, cart_id: uuid.UUID) -> List[CartLine]:
        """Every line with its product and inventory in ONE query (no N+1).
        Product and inventory are joined explicitly by column so this does
        not depend on relationship loading strategy; a product with no
        inventory row comes back with `None` for the inventory."""
        return (
            self.db.query(CartItem, Product, Inventory)
            .join(Product, Product.id == CartItem.product_id)
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .filter(CartItem.cart_id == cart_id)
            .order_by(CartItem.created_at.asc(), CartItem.id.asc())
            .all()
        )

    def get_item_for_user(self, item_id: uuid.UUID, user_id: uuid.UUID) -> Optional[CartItem]:
        return (
            self.db.query(CartItem)
            .join(Cart, Cart.id == CartItem.cart_id)
            .filter(CartItem.id == item_id, Cart.user_id == user_id)
            .first()
        )

    def get_item_by_product(self, cart_id: uuid.UUID, product_id: uuid.UUID) -> Optional[CartItem]:
        return (
            self.db.query(CartItem)
            .filter(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
            .first()
        )

    def add_item(self, cart_id: uuid.UUID, product_id: uuid.UUID, quantity: int) -> CartItem:
        item = CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity)
        self.db.add(item)
        self.db.flush()
        return item

    def save_item(self, item: CartItem) -> CartItem:
        self.db.add(item)
        return item

    def delete_item(self, item: CartItem) -> None:
        self.db.delete(item)

    def delete_all_items(self, cart_id: uuid.UUID) -> int:
        return (
            self.db.query(CartItem)
            .filter(CartItem.cart_id == cart_id)
            .delete(synchronize_session=False)
        )

    # --- product + stock lookup ------------------------------------------

    def get_product_with_inventory(
        self, product_id: uuid.UUID
    ) -> Optional[Tuple[Product, Optional[Inventory]]]:
        row = (
            self.db.query(Product, Inventory)
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .filter(Product.id == product_id)
            .first()
        )
        return (row[0], row[1]) if row else None