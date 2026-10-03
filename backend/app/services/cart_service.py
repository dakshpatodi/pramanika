"""
Cart business logic.

Every public method takes the authenticated user's id (taken from the JWT
by the router) - there is no way to address another user's cart from here.
Mutating methods run inside `_transaction()`: one commit per operation,
rollback if anything in it raises (same ownership model as AuthService -
repositories stage changes, the service commits).

Every method returns a fully priced `CartResponse`, so the frontend never
has to compute or merge anything itself.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    CartItemNotFoundError,
    InsufficientStockError,
    InvalidCouponError,
    ProductUnavailableError,
)
from app.core.money import money_to_float, to_money
from app.models import Cart
from app.repositories.cart_repository import CartRepository
from app.repositories.coupon_repository import CouponRepository
from app.schemas.cart import (
    CartCouponResponse,
    CartItemResponse,
    CartProductSummary,
    CartResponse,
    CartTotalsResponse,
)
from app.services.cart_rules import available_stock, line_issue
from app.services.pricing import PricingConfig, PricingResult, calculate_totals, coupon_problem


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CartService:
    def __init__(
        self,
        db: Session,
        *,
        config: Optional[PricingConfig] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.db = db
        self.repository = CartRepository(db)
        self.coupon_repository = CouponRepository(db)
        self.config = config or PricingConfig.from_settings(settings)
        self.clock = clock or _utcnow

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_cart(self, user_id: uuid.UUID) -> CartResponse:
        """Read-only: a user who has never added anything simply has no
        cart row yet, and gets an empty response rather than a cart being
        created just because they looked."""
        cart = self.repository.get_by_user_id(user_id)
        return self._build_response(cart)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def add_item(self, user_id: uuid.UUID, product_id: uuid.UUID, quantity: int) -> CartResponse:
        """Add `quantity` units. If the product is already in the cart the
        quantity is INCREASED (decision A); the combined quantity is what
        gets checked against stock.

        Raises:
            ProductUnavailableError: no such product, or it is inactive.
            InsufficientStockError: the combined quantity exceeds what is
                available (quantity - reserved_quantity).
        """
        with self._transaction():
            # Product first, so a bad product id never leaves an empty
            # cart row behind.
            found = self.repository.get_product_with_inventory(product_id)
            if found is None or not found[0].is_active:
                raise ProductUnavailableError()
            product, inventory = found

            cart = self._get_or_create_cart(user_id)

            existing = self.repository.get_item_by_product(cart.id, product.id)
            in_cart = existing.quantity if existing else 0
            available = available_stock(inventory)
            if in_cart + quantity > available:
                raise InsufficientStockError(available, in_cart)

            if existing:
                existing.quantity = in_cart + quantity
                self.repository.save_item(existing)
            else:
                self.repository.add_item(cart.id, product.id, quantity)

        return self._build_response(cart)

    def update_item(self, user_id: uuid.UUID, item_id: uuid.UUID, quantity: int) -> CartResponse:
        """Set a line's quantity to exactly `quantity` (decision A).

        Raises:
            CartItemNotFoundError: no such item in THIS user's cart.
            ProductUnavailableError: the product has been deactivated.
            InsufficientStockError: `quantity` exceeds available stock.
        """
        with self._transaction():
            cart = self._require_cart(user_id)
            item = self.repository.get_item_for_user(item_id, user_id)
            if item is None:
                raise CartItemNotFoundError()

            found = self.repository.get_product_with_inventory(item.product_id)
            if found is None or not found[0].is_active:
                raise ProductUnavailableError()
            _, inventory = found

            available = available_stock(inventory)
            if quantity > available:
                raise InsufficientStockError(available)

            item.quantity = quantity
            self.repository.save_item(item)

        return self._build_response(cart)

    def remove_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> CartResponse:
        """Raises CartItemNotFoundError if the item is not in this user's cart."""
        with self._transaction():
            cart = self._require_cart(user_id)
            item = self.repository.get_item_for_user(item_id, user_id)
            if item is None:
                raise CartItemNotFoundError()
            self.repository.delete_item(item)

        return self._build_response(cart)

    def clear_cart(self, user_id: uuid.UUID) -> CartResponse:
        """Remove every item AND detach any coupon (decision B: the coupon
        lives until it is removed or the cart is cleared). Clearing a
        cart that does not exist is a harmless no-op."""
        with self._transaction():
            cart = self.repository.get_by_user_id(user_id, for_update=True)
            if cart is not None:
                self.repository.delete_all_items(cart.id)
                self.repository.set_coupon(cart, None)

        return self._build_response(cart)

    # ------------------------------------------------------------------
    # Coupon
    # ------------------------------------------------------------------

    def apply_coupon(self, user_id: uuid.UUID, code: str) -> CartResponse:
        """Attach a coupon (replacing any existing one) after validating
        it against the cart as it stands right now.

        Raises:
            InvalidCouponError: unknown code, empty cart, or the coupon
                is inactive / not started / expired / used up / below its
                minimum order. Nothing is attached in that case.
        """
        with self._transaction():
            cart = self.repository.get_by_user_id(user_id, for_update=True)
            coupon = self.coupon_repository.get_by_code(code)
            if coupon is None:
                raise InvalidCouponError()

            purchasable = self._purchasable_lines(cart) if cart is not None else []
            if cart is None or not purchasable:
                raise InvalidCouponError("Add items to your cart before applying a coupon.")

            subtotal = to_money(sum((price * qty for price, qty in purchasable), to_money(0)))
            problem = coupon_problem(coupon, subtotal, self.clock())
            if problem is not None:
                raise InvalidCouponError(problem)

            self.repository.set_coupon(cart, coupon.id)

        return self._build_response(cart)

    def remove_coupon(self, user_id: uuid.UUID) -> CartResponse:
        """Idempotent: removing a coupon that is not there is not an error."""
        with self._transaction():
            cart = self.repository.get_by_user_id(user_id, for_update=True)
            if cart is not None and cart.coupon_id is not None:
                self.repository.set_coupon(cart, None)

        return self._build_response(cart)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _require_cart(self, user_id: uuid.UUID) -> Cart:
        """Locked cart for a mutation of existing items. A user with no
        cart cannot own any item, so this is reported exactly like an
        unknown item id."""
        cart = self.repository.get_by_user_id(user_id, for_update=True)
        if cart is None:
            raise CartItemNotFoundError()
        return cart

    def _get_or_create_cart(self, user_id: uuid.UUID) -> Cart:
        """Locked cart, created on first use.

        Two first-ever adds from the same user can race: both see "no
        cart", both insert, and the UNIQUE(user_id) constraint rejects the
        loser. The insert runs in a savepoint so the loser can back out of
        just that insert and pick up the winner's cart instead of failing
        the whole request.
        """
        cart = self.repository.get_by_user_id(user_id, for_update=True)
        if cart is not None:
            return cart

        try:
            with self.db.begin_nested():
                return self.repository.create(user_id)
        except IntegrityError:
            cart = self.repository.get_by_user_id(user_id, for_update=True)
            if cart is None:
                raise
            return cart

    def _purchasable_lines(self, cart: Cart):
        """[(unit_price, quantity)] for lines with no stock/availability issue."""
        lines = []
        for item, product, inventory in self.repository.get_lines(cart.id):
            if line_issue(product.is_active, item.quantity, available_stock(inventory)) is None:
                lines.append((to_money(product.price), item.quantity))
        return lines

    def _build_response(self, cart: Optional[Cart]) -> CartResponse:
        if cart is None:
            result = calculate_totals([], None, self.clock(), self.config)
            return CartResponse(totals=self._totals_response(result))

        coupon = (
            self.coupon_repository.get_by_id(cart.coupon_id) if cart.coupon_id is not None else None
        )

        items = []
        priced_lines = []
        item_count = 0
        has_issues = False
        for item, product, inventory in self.repository.get_lines(cart.id):
            available = available_stock(inventory)
            issue = line_issue(product.is_active, item.quantity, available)
            unit_price = to_money(product.price)

            items.append(
                CartItemResponse(
                    id=item.id,
                    product=CartProductSummary(
                        id=product.id,
                        name=product.name,
                        slug=product.slug,
                        sku=product.sku,
                        image_url=product.image_url,
                    ),
                    quantity=item.quantity,
                    unit_price=money_to_float(unit_price),
                    line_subtotal=money_to_float(unit_price * item.quantity),
                    available_quantity=available,
                    issue=issue,
                )
            )
            item_count += item.quantity
            if issue is None:
                priced_lines.append((unit_price, item.quantity))
            else:
                has_issues = True

        result = calculate_totals(priced_lines, coupon, self.clock(), self.config)

        coupon_response = None
        if coupon is not None:
            coupon_response = CartCouponResponse(
                code=coupon.code,
                description=coupon.description,
                applied=result.coupon_problem is None,
                message=result.coupon_problem,
            )

        return CartResponse(
            id=cart.id,
            items=items,
            item_count=item_count,
            has_issues=has_issues,
            coupon=coupon_response,
            totals=self._totals_response(result),
        )

    @staticmethod
    def _totals_response(result: PricingResult) -> CartTotalsResponse:
        t = result.totals
        return CartTotalsResponse(
            subtotal=money_to_float(t.subtotal),
            discount=money_to_float(t.discount),
            taxable_amount=money_to_float(t.taxable_amount),
            gst_rate=float(t.gst_rate),
            gst=money_to_float(t.gst),
            delivery_charge=money_to_float(t.delivery_charge),
            amount_for_free_delivery=money_to_float(t.amount_for_free_delivery),
            total=money_to_float(t.total),
        )