"""
Checkout: turn the user's cart into an order - atomically and idempotently.

Everything below happens in ONE database transaction. Either the order
exists with its items, its stock reserved and its coupon use counted and
the cart is empty - or none of that happened and the cart is untouched.

Steps (and the locks they take, always in this order so two checkouts -
or a checkout and a cancel - can never deadlock):

  0. Replay check   same Idempotency-Key already produced an order? return it.
  1. cart           SELECT ... FOR UPDATE   (serialises this user's checkouts)
  1b. replay check again - a concurrent request with the same key that held
      the cart lock before us has committed by now
  2. address        must belong to the user
  3. coupon         SELECT ... FOR UPDATE   (only if the cart has one)
  4. products       SELECT ... FOR SHARE, ascending id (prices can't change)
  5. price          server-side, via the Phase 5 pricing rules
  6. reserve stock  conditional UPDATE per product, ascending id
  7. count coupon   conditional UPDATE (active AND under its limit)
  8. insert order + items (snapshots), clear the cart, COMMIT

Idempotency: the order itself is the stored result. It carries the client's
`Idempotency-Key` and a fingerprint of the request body; a partial UNIQUE
index on (user_id, key) makes a second order for the same key impossible
even if every application-level check were bypassed. A failed attempt
stores nothing, so retrying after a failure simply runs again.

Nothing here talks to a payment provider: the order is created
status=pending / payment_status=pending with its stock RESERVED.
"""

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterator, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AddressNotFoundError,
    CartChangedError,
    CartIssuesError,
    DomainError,
    EmptyCartError,
    IdempotencyKeyReusedError,
    InvalidCouponError,
)
from app.core.money import to_decimal, to_money
from app.models import (
    Order,
    OrderInventoryState,
    OrderItem,
    OrderPaymentStatus,
    OrderStatus,
)
from app.repositories.address_repository import AddressRepository
from app.repositories.cart_repository import CartRepository
from app.repositories.coupon_repository import CouponRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.services.cart_rules import available_stock, line_issue
from app.services.coupon_usage import CouponUsageService
from app.services.pricing import PricingConfig, calculate_totals
from app.services.reservation_service import ReservationService

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
"""8-64 characters (a UUID is 36). 64 is the width of the database column."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    created: bool
    """False when this was a replay of an earlier request with the same
    Idempotency-Key: the existing order is returned and nothing changed."""


def request_fingerprint(shipping_address_id: uuid.UUID, expected_total: Optional[Decimal]) -> str:
    """Stable hash of everything the client sent in the request body, so
    the same key with a different body can be told apart from a retry."""
    canonical = json.dumps(
        {
            "shipping_address_id": str(shipping_address_id),
            "expected_total": None if expected_total is None else str(to_money(expected_total)),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CheckoutService:
    def __init__(
        self,
        db: Session,
        *,
        config: Optional[PricingConfig] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.db = db
        self.carts = CartRepository(db)
        self.addresses = AddressRepository(db)
        self.coupons = CouponRepository(db)
        self.inventory = InventoryRepository(db)
        self.orders = OrderRepository(db)
        self.reservations = ReservationService(db)
        self.coupon_usage = CouponUsageService(db)
        self.config = config or PricingConfig.from_settings(settings)
        self.clock = clock or _utcnow

    # ------------------------------------------------------------------

    def place_order(
        self,
        user_id: uuid.UUID,
        *,
        shipping_address_id: uuid.UUID,
        idempotency_key: str,
        expected_total: Optional[Decimal] = None,
    ) -> CheckoutResult:
        """Create the order for `user_id`'s cart, or replay an earlier one.

        `expected_total` is the total the customer saw on screen; if the
        server's own calculation differs, nothing is ordered
        (`CartChangedError`). It is a guard, never a price source.

        Raises (all rolled back, nothing changed):
            DomainError (400): malformed Idempotency-Key.
            EmptyCartError, AddressNotFoundError, CartIssuesError,
            InvalidCouponError, CartChangedError, InsufficientStockError,
            IdempotencyKeyReusedError.
        """
        if not IDEMPOTENCY_KEY_PATTERN.match(idempotency_key or ""):
            raise DomainError(
                "Idempotency-Key must be 8-64 characters: letters, digits, '.', '_', ':' or '-'."
            )
        expected = None if expected_total is None else to_money(expected_total)
        fingerprint = request_fingerprint(shipping_address_id, expected)

        try:
            return self._place_order(user_id, shipping_address_id, idempotency_key, expected, fingerprint)
        except IntegrityError:
            # The unique index on (user_id, idempotency_key) is the last
            # line of defence. If it fired, a request with this key won
            # while we were working - hand back its order. Any other
            # integrity error is a real failure and is re-raised.
            self.db.rollback()
            winner = self.orders.get_by_idempotency_key(user_id, idempotency_key)
            if winner is None:
                raise
            return CheckoutResult(order=self._replay(winner, fingerprint), created=False)

    # ------------------------------------------------------------------

    def _place_order(
        self,
        user_id: uuid.UUID,
        shipping_address_id: uuid.UUID,
        idempotency_key: str,
        expected: Optional[Decimal],
        fingerprint: str,
    ) -> CheckoutResult:
        now = self.clock()

        with self._transaction():
            # 0. Replay, before taking any lock.
            existing = self.orders.get_by_idempotency_key(user_id, idempotency_key)
            if existing is not None:
                return CheckoutResult(order=self._replay(existing, fingerprint), created=False)

            # 1. Cart, locked: this user's checkouts now run one at a time.
            cart = self.carts.get_by_user_id(user_id, for_update=True)
            if cart is None:
                raise EmptyCartError()

            # 1b. A same-key request that held the lock before us has
            # committed; READ COMMITTED lets this fresh query see it.
            existing = self.orders.get_by_idempotency_key(user_id, idempotency_key)
            if existing is not None:
                return CheckoutResult(order=self._replay(existing, fingerprint), created=False)

            cart_lines = self.carts.get_lines(cart.id)
            if not cart_lines:
                raise EmptyCartError()

            # 2. Address: must be this user's.
            address = self.addresses.get_for_user(shipping_address_id, user_id)
            if address is None:
                raise AddressNotFoundError()

            # 3. Coupon, locked, so used_count is current while we validate.
            coupon = (
                self.coupons.get_by_id(cart.coupon_id, for_update=True) if cart.coupon_id is not None else None
            )

            # 4. Products, share-locked; then re-read the lines so prices
            # and active flags are the locked, current values.
            self.inventory.lock_products([product.id for _, product, _ in cart_lines])
            cart_lines = self.carts.get_lines(cart.id)

            # 5. Price on the server.
            priced = []
            for item, product, inventory in cart_lines:
                issue = line_issue(product.is_active, item.quantity, available_stock(inventory))
                if issue is not None:
                    raise CartIssuesError(f"{product.name}: {issue}")
                priced.append((item, product, to_money(product.price)))

            result = calculate_totals([(price, item.quantity) for item, _, price in priced], coupon, now, self.config)
            if coupon is not None and result.coupon_problem is not None:
                raise InvalidCouponError(result.coupon_problem)
            totals = result.totals

            if expected is not None and expected != totals.total:
                raise CartChangedError()

            # 6. Reserve stock (all lines or raise InsufficientStockError).
            self.reservations.reserve([(product.id, item.quantity) for item, product, _ in priced])

            # 7. Count the coupon use (conditional UPDATE; last line of defence).
            if coupon is not None:
                self.coupon_usage.consume(coupon.id)

            # 8. The order, with snapshots of everything that must not change later.
            order = Order(
                user_id=user_id,
                order_number=self.orders.next_order_number(now),
                status=OrderStatus.PENDING,
                payment_status=OrderPaymentStatus.PENDING,
                inventory_state=OrderInventoryState.RESERVED,
                shipping_address_id=address.id,
                shipping_full_name=address.full_name,
                shipping_phone_number=address.phone_number,
                shipping_address_line_1=address.address_line_1,
                shipping_address_line_2=address.address_line_2,
                shipping_city=address.city,
                shipping_state=address.state,
                shipping_postal_code=address.postal_code,
                shipping_country=address.country,
                subtotal=totals.subtotal,
                discount_amount=totals.discount,
                taxable_amount=totals.taxable_amount,
                gst_rate=totals.gst_rate,
                tax_amount=totals.gst,
                delivery_charge=totals.delivery_charge,
                total_amount=totals.total,
                coupon_id=coupon.id if coupon is not None else None,
                coupon_code=coupon.code if coupon is not None else None,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
            for item, product, unit_price in priced:
                order.items.append(
                    OrderItem(
                        product_id=product.id,
                        product_name_snapshot=product.name,
                        sku_snapshot=product.sku,
                        unit_price=unit_price,
                        quantity=item.quantity,
                        subtotal=to_money(unit_price * item.quantity),
                    )
                )
            self.orders.add(order)
            order_id = order.id

            # Clear the cart only now - it is part of the same commit.
            self.carts.delete_all_items(cart.id)
            self.carts.set_coupon(cart, None)

        # Committed. Return a clean instance with its items loaded.
        created = self.orders.get_for_user(order_id, user_id)
        return CheckoutResult(order=created, created=True)

    # ------------------------------------------------------------------

    @staticmethod
    def _replay(existing: Order, fingerprint: str) -> Order:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyKeyReusedError()
        return existing

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise