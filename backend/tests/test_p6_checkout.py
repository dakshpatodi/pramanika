"""
Checkout service (PostgreSQL integration tests): atomic, idempotent order
creation with stock reservation and coupon usage.

Groups:
  CheckoutSuccessTests      what a good order looks like
  CheckoutRejectionTests    every refusal changes nothing
  CheckoutRollbackTests     a failure at the LAST step undoes the earlier steps
  CheckoutIdempotencyTests  Idempotency-Key retries, reuse and the unique-index backstop
  CheckoutConcurrencyTests  real threads, real row locks

See tests/pg_support.py for how to run them.
"""

import re
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

from app.core.exceptions import (
    AddressNotFoundError,
    CartChangedError,
    CartIssuesError,
    DomainError,
    EmptyCartError,
    IdempotencyKeyReusedError,
    InsufficientStockError,
    InvalidCouponError,
)
from app.models import (
    Cart,
    CartItem,
    Inventory,
    Order,
    OrderInventoryState,
    OrderItem,
    OrderPaymentStatus,
    OrderStatus,
    Product,
)
from app.repositories.order_repository import OrderRepository
from app.services.cart_service import CartService
from app.services.checkout_service import CheckoutService
from app.services.pricing import PricingConfig
from tests.pg_support import PostgresTestCase, new_session, run_concurrently

CONFIG = PricingConfig(
    gst_rate=Decimal("0.05"),
    free_delivery_threshold=Decimal("500"),
    delivery_charge=Decimal("49"),
)


def new_key() -> str:
    return f"key-{uuid.uuid4()}"


class CheckoutTestCase(PostgresTestCase):
    # --- builders -----------------------------------------------------------

    def fill_cart(self, user, lines, coupon=None):
        cart = self.db.query(Cart).filter(Cart.user_id == user.id).first()
        if cart is None:
            cart = Cart(user_id=user.id)
            self.db.add(cart)
            self.db.flush()
        self.db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
        for product, quantity in lines:
            self.db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity))
        cart.coupon_id = coupon.id if coupon else None
        self.db.commit()
        return cart

    def checkout(self, user, address, *, key=None, expected_total=None, session=None, **service_kwargs):
        service = CheckoutService(session or self.db, config=CONFIG, **service_kwargs)
        return service.place_order(
            user.id,
            shipping_address_id=address.id,
            idempotency_key=key or new_key(),
            expected_total=expected_total,
        )

    # --- fresh readers --------------------------------------------------------

    def order_count(self) -> int:
        with new_session() as s:
            return s.query(Order).count()

    def cart_state(self, user):
        """(item quantities by product id, coupon_id) as committed."""
        with new_session() as s:
            cart = s.query(Cart).filter(Cart.user_id == user.id).first()
            if cart is None:
                return {}, None
            items = s.query(CartItem).filter(CartItem.cart_id == cart.id).all()
            return {i.product_id: i.quantity for i in items}, cart.coupon_id

    def assert_nothing_changed(self, user, products, coupon=None, *, stock_before, used_before=None, cart_before):
        self.assertEqual(self.order_count(), 0, "an order was left behind")
        self.assertEqual([self.stock(p) for p in products], stock_before, "stock changed")
        if coupon is not None:
            self.assertEqual(self.used_count(coupon), used_before, "coupon used_count changed")
        self.assertEqual(self.cart_state(user), cart_before, "the cart was modified")


class CheckoutSuccessTests(CheckoutTestCase):
    def test_creates_a_pending_unpaid_order_with_reserved_stock(self):
        user = self.make_user()
        address = self.make_address(user)
        rice = self.make_product(price="100.00", stock=10, name="Rice")
        oats = self.make_product(price="150.00", stock=5, name="Oats")
        self.fill_cart(user, [(rice, 2), (oats, 1)])

        result = self.checkout(user, address)

        order = result.order
        self.assertTrue(result.created)
        self.assertRegex(order.order_number, r"^PRM-\d{4}-\d{6}$")
        self.assertEqual(order.user_id, user.id)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(order.inventory_state, OrderInventoryState.RESERVED)
        # 350 subtotal, no coupon, 5% GST = 17.50, delivery 49 (under 500)
        self.assertEqual(
            (order.subtotal, order.discount_amount, order.taxable_amount, order.tax_amount, order.delivery_charge, order.total_amount),
            (Decimal("350.00"), Decimal("0.00"), Decimal("350.00"), Decimal("17.50"), Decimal("49.00"), Decimal("416.50")),
        )
        self.assertEqual(order.gst_rate, Decimal("0.0500"))
        self.assertIsNone(order.coupon_id)
        self.assertEqual(
            sorted((i.product_name_snapshot, i.sku_snapshot, i.unit_price, i.quantity, i.subtotal) for i in order.items),
            sorted(
                [
                    ("Rice", rice.sku, Decimal("100.00"), 2, Decimal("200.00")),
                    ("Oats", oats.sku, Decimal("150.00"), 1, Decimal("150.00")),
                ]
            ),
        )
        # Stock is RESERVED, not sold.
        self.assertEqual(self.stock(rice), (10, 2))
        self.assertEqual(self.stock(oats), (5, 1))
        # The cart is empty afterwards.
        self.assertEqual(self.cart_state(user), ({}, None))

    def test_order_total_equals_what_the_cart_page_showed(self):
        user = self.make_user()
        address = self.make_address(user)
        coupon = self.make_coupon(discount_value=Decimal("15"))
        a = self.make_product(price="199.99", stock=9)
        b = self.make_product(price="33.33", stock=9)
        self.fill_cart(user, [(a, 2), (b, 3)], coupon)

        shown = CartService(self.db, config=CONFIG).get_cart(user.id).totals
        order = self.checkout(user, address, expected_total=Decimal(str(shown.total))).order

        self.assertEqual(
            (order.subtotal, order.discount_amount, order.taxable_amount, order.tax_amount, order.delivery_charge, order.total_amount),
            tuple(Decimal(str(v)).quantize(Decimal("0.01")) for v in (shown.subtotal, shown.discount, shown.taxable_amount, shown.gst, shown.delivery_charge, shown.total)),
        )

    def test_coupon_is_applied_counted_and_detached_from_the_cart(self):
        user = self.make_user()
        address = self.make_address(user)
        coupon = self.make_coupon(discount_value=Decimal("10"), usage_limit=5, used_count=2)
        product = self.make_product(price="300.00", stock=10)
        self.fill_cart(user, [(product, 2)], coupon)  # 600 -> 10% off = 60

        order = self.checkout(user, address).order

        self.assertEqual(order.discount_amount, Decimal("60.00"))
        self.assertEqual(order.taxable_amount, Decimal("540.00"))
        self.assertEqual(order.tax_amount, Decimal("27.00"))
        self.assertEqual(order.delivery_charge, Decimal("0.00"))  # free over 500
        self.assertEqual(order.total_amount, Decimal("567.00"))
        self.assertEqual((order.coupon_id, order.coupon_code), (coupon.id, coupon.code))
        self.assertEqual(self.used_count(coupon), 3)
        self.assertEqual(self.cart_state(user), ({}, None))

    def test_no_coupon_leaves_every_counter_alone(self):
        user = self.make_user()
        address = self.make_address(user)
        bystander = self.make_coupon(used_count=4, usage_limit=10)
        product = self.make_product(stock=5)
        self.fill_cart(user, [(product, 1)])

        self.checkout(user, address)

        self.assertEqual(self.used_count(bystander), 4)

    def test_address_is_copied_into_the_order(self):
        user = self.make_user()
        address = self.make_address(user)
        product = self.make_product(stock=5)
        self.fill_cart(user, [(product, 1)])

        order_id = self.checkout(user, address).order.id

        address.city = "Mumbai"  # customer edits the address later
        self.db.commit()
        with new_session() as s:
            order = s.get(Order, order_id)
            self.assertEqual(order.shipping_address_id, address.id)
            self.assertEqual(
                (order.shipping_full_name, order.shipping_phone_number, order.shipping_address_line_1, order.shipping_city, order.shipping_state, order.shipping_postal_code, order.shipping_country),
                ("Test User", "9000000000", "1 Test Street", "Pune", "Maharashtra", "411001", "India"),
            )

    def test_prices_are_snapshots_later_price_changes_do_not_touch_the_order(self):
        user = self.make_user()
        address = self.make_address(user)
        product = self.make_product(price="100.00", stock=5)
        self.fill_cart(user, [(product, 2)])

        order_id = self.checkout(user, address).order.id

        self.db.query(Product).filter(Product.id == product.id).update({Product.price: Decimal("999.00")})
        self.db.commit()
        with new_session() as s:
            item = s.query(OrderItem).filter(OrderItem.order_id == order_id).one()
            self.assertEqual((item.unit_price, item.subtotal), (Decimal("100.00"), Decimal("200.00")))

    def test_the_same_product_can_be_ordered_by_two_users(self):
        a, b = self.make_user(), self.make_user()
        addr_a, addr_b = self.make_address(a), self.make_address(b)
        product = self.make_product(stock=5)
        self.fill_cart(a, [(product, 2)])
        self.fill_cart(b, [(product, 3)])

        self.checkout(a, addr_a)
        self.checkout(b, addr_b)

        self.assertEqual(self.stock(product), (5, 5))

    def test_order_numbers_are_unique_across_orders(self):
        user = self.make_user()
        address = self.make_address(user)
        product = self.make_product(stock=50)
        numbers = []
        for _ in range(3):
            self.fill_cart(user, [(product, 1)])
            numbers.append(self.checkout(user, address).order.order_number)
        self.assertEqual(len(set(numbers)), 3)


class CheckoutRejectionTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=5)

    def expect_rejection(self, error, *, lines=None, coupon=None, address=None, expected_total=None, key=None):
        """Run checkout and assert it fails with `error` and changes nothing."""
        if lines is not None:
            self.fill_cart(self.user, lines, coupon)
        products = [self.product] + [p for p, _ in (lines or []) if p.id != self.product.id]
        before = dict(
            stock_before=[self.stock(p) for p in products],
            used_before=self.used_count(coupon) if coupon else None,
            cart_before=self.cart_state(self.user),
        )
        with self.assertRaises(error) as ctx:
            self.checkout(self.user, address or self.address, expected_total=expected_total, key=key)
        self.assert_nothing_changed(self.user, products, coupon, **before)
        return ctx.exception

    def test_no_cart_at_all(self):
        self.expect_rejection(EmptyCartError)

    def test_empty_cart(self):
        self.expect_rejection(EmptyCartError, lines=[])

    def test_unknown_address(self):
        ghost = mock.Mock(id=uuid.uuid4())
        self.expect_rejection(AddressNotFoundError, lines=[(self.product, 1)], address=ghost)

    def test_someone_elses_address(self):
        stranger_address = self.make_address(self.make_user())
        self.expect_rejection(AddressNotFoundError, lines=[(self.product, 1)], address=stranger_address)

    def test_inactive_product(self):
        self.fill_cart(self.user, [(self.product, 1)])
        self.db.query(Product).filter(Product.id == self.product.id).update({Product.is_active: False})
        self.db.commit()
        error = self.expect_rejection(CartIssuesError)
        self.assertIn("no longer available", error.message)

    def test_quantity_above_available_stock(self):
        error = self.expect_rejection(CartIssuesError, lines=[(self.product, 6)])
        self.assertIn("Only 5", error.message)

    def test_out_of_stock_product_is_refused_even_when_other_lines_are_fine(self):
        gone = self.make_product(stock=3, reserved=3)
        self.expect_rejection(CartIssuesError, lines=[(self.product, 1), (gone, 1)])

    def test_stock_held_by_other_orders_is_not_available(self):
        self.db.query(Inventory).filter(Inventory.product_id == self.product.id).update({Inventory.reserved_quantity: 4})
        self.db.commit()
        self.expect_rejection(CartIssuesError, lines=[(self.product, 2)])

    def test_total_the_customer_saw_is_stale(self):
        self.fill_cart(self.user, [(self.product, 2)])  # really 200 + 10 + 49 = 259
        self.expect_rejection(CartChangedError, expected_total=Decimal("100.00"))

    def test_matching_expected_total_is_accepted(self):
        self.fill_cart(self.user, [(self.product, 2)])
        self.assertTrue(self.checkout(self.user, self.address, expected_total=Decimal("259.00")).created)

    def test_price_changed_after_the_customer_looked(self):
        self.fill_cart(self.user, [(self.product, 2)])
        self.db.query(Product).filter(Product.id == self.product.id).update({Product.price: Decimal("120.00")})
        self.db.commit()
        self.expect_rejection(CartChangedError, expected_total=Decimal("259.00"))

    def test_coupon_that_expired(self):
        coupon = self.make_coupon(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        error = self.expect_rejection(InvalidCouponError, lines=[(self.product, 1)], coupon=coupon)
        self.assertIn("expired", error.message)

    def test_coupon_that_was_deactivated(self):
        coupon = self.make_coupon(is_active=False)
        self.expect_rejection(InvalidCouponError, lines=[(self.product, 1)], coupon=coupon)

    def test_coupon_that_is_not_valid_yet(self):
        coupon = self.make_coupon(starts_at=datetime.now(timezone.utc) + timedelta(days=1))
        self.expect_rejection(InvalidCouponError, lines=[(self.product, 1)], coupon=coupon)

    def test_coupon_whose_limit_was_reached(self):
        coupon = self.make_coupon(usage_limit=3, used_count=3)
        error = self.expect_rejection(InvalidCouponError, lines=[(self.product, 1)], coupon=coupon)
        self.assertIn("usage limit", error.message)

    def test_cart_below_the_coupons_minimum_order(self):
        coupon = self.make_coupon(minimum_order_amount=Decimal("500"))
        self.expect_rejection(InvalidCouponError, lines=[(self.product, 1)], coupon=coupon)

    def test_malformed_idempotency_keys(self):
        self.fill_cart(self.user, [(self.product, 1)])
        for bad in ["", "short", "x" * 65, "has spaces in it", "semi;colon-key", None]:
            with self.subTest(key=bad):
                with self.assertRaises(DomainError):
                    CheckoutService(self.db, config=CONFIG).place_order(
                        self.user.id, shipping_address_id=self.address.id, idempotency_key=bad
                    )
        self.assertEqual(self.order_count(), 0)
        self.assertEqual(self.stock(self.product), (5, 0))

    def test_a_refusal_does_not_poison_the_next_attempt(self):
        # Fails on stock, then succeeds once the cart is fixed - same session, same key.
        key = new_key()
        self.fill_cart(self.user, [(self.product, 9)])
        with self.assertRaises(CartIssuesError):
            self.checkout(self.user, self.address, key=key)
        self.fill_cart(self.user, [(self.product, 2)])
        self.assertTrue(self.checkout(self.user, self.address, key=key).created)
        self.assertEqual(self.stock(self.product), (5, 2))


class CheckoutRollbackTests(CheckoutTestCase):
    """Failures AFTER stock was reserved and the coupon was counted must
    undo both - the transaction is all-or-nothing."""

    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)

    def test_failure_while_saving_the_order_undoes_reservation_coupon_and_cart_clearing(self):
        coupon = self.make_coupon(usage_limit=5, used_count=1)
        a = self.make_product(price="300.00", stock=10)
        b = self.make_product(price="300.00", stock=10)
        self.fill_cart(self.user, [(a, 2), (b, 3)], coupon)
        before = dict(stock_before=[self.stock(a), self.stock(b)], used_before=1, cart_before=self.cart_state(self.user))

        with mock.patch.object(OrderRepository, "add", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.checkout(self.user, self.address)

        self.assert_nothing_changed(self.user, [a, b], coupon, **before)

    def test_stock_running_out_on_a_later_line_releases_the_earlier_lines(self):
        a = self.make_product(stock=10)
        b = self.make_product(stock=1)
        self.fill_cart(self.user, [(a, 4), (b, 2)])
        before = dict(stock_before=[self.stock(a), self.stock(b)], cart_before=self.cart_state(self.user))

        # Skip the cart-level check so the failure comes from the reservation itself.
        with mock.patch("app.services.checkout_service.line_issue", return_value=None):
            with self.assertRaises(InsufficientStockError):
                self.checkout(self.user, self.address)

        self.assert_nothing_changed(self.user, [a, b], **before)

    def test_coupon_row_is_locked_while_checkout_runs(self):
        """Validation and the increment see the same used_count: nobody
        else can change the coupon between them."""
        coupon = self.make_coupon(usage_limit=1, used_count=0)
        product = self.make_product(stock=10, price="300.00")
        self.fill_cart(self.user, [(product, 2)], coupon)

        from app.services.coupon_usage import CouponUsageService

        real_consume = CouponUsageService.consume

        def probe_then_consume(service, coupon_id):
            self._assert_coupon_locked(coupon_id)
            return real_consume(service, coupon_id)

        with mock.patch.object(CouponUsageService, "consume", probe_then_consume):
            result = self.checkout(self.user, self.address)
        self.assertTrue(result.created)
        self.assertEqual(self.used_count(coupon), 1)

    def _assert_coupon_locked(self, coupon_id):
        """From a second connection the coupon row must be locked."""
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError

        with new_session() as other:
            other.execute(text("set local lock_timeout = '300ms'"))
            with self.assertRaises(OperationalError):
                other.execute(text("update coupons set description = 'x' where id = :i"), {"i": coupon_id})
            other.rollback()

    def test_products_are_share_locked_during_checkout(self):
        product = self.make_product(stock=10)
        self.fill_cart(self.user, [(product, 1)])
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError
        from app.services.reservation_service import ReservationService

        real_reserve = ReservationService.reserve
        outcome = {}

        def reserve_and_probe(service, lines):
            with new_session() as other:
                other.execute(text("set local lock_timeout = '300ms'"))
                try:
                    other.execute(text("update products set price = 1 where id = :i"), {"i": product.id})
                    outcome["blocked"] = False
                except OperationalError:
                    outcome["blocked"] = True
                other.rollback()
            return real_reserve(service, lines)

        with mock.patch.object(ReservationService, "reserve", reserve_and_probe):
            self.checkout(self.user, self.address)
        self.assertTrue(outcome["blocked"], "a price change was able to slip in while checkout held the product")


class CheckoutIdempotencyTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=10)
        self.coupon = self.make_coupon(usage_limit=10)

    def test_retry_with_the_same_key_returns_the_same_order_and_changes_nothing_more(self):
        self.fill_cart(self.user, [(self.product, 2)], self.coupon)
        key = new_key()

        first = self.checkout(self.user, self.address, key=key)
        second = self.checkout(self.user, self.address, key=key)

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.order.id, second.order.id)
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock(self.product), (10, 2), "stock reserved twice")
        self.assertEqual(self.used_count(self.coupon), 1, "coupon counted twice")

    def test_replay_ignores_whatever_is_in_the_cart_now(self):
        self.fill_cart(self.user, [(self.product, 2)])
        key = new_key()
        first = self.checkout(self.user, self.address, key=key)

        self.fill_cart(self.user, [(self.product, 5)])  # shopping again
        replay = self.checkout(self.user, self.address, key=key)

        self.assertEqual(replay.order.id, first.order.id)
        self.assertEqual(self.cart_state(self.user)[0], {self.product.id: 5}, "the new cart was consumed by a replay")
        self.assertEqual(self.stock(self.product), (10, 2))

    def test_same_key_with_a_different_address_is_rejected(self):
        self.fill_cart(self.user, [(self.product, 1)])
        key = new_key()
        self.checkout(self.user, self.address, key=key)
        other = self.make_address(self.user)

        with self.assertRaises(IdempotencyKeyReusedError):
            self.checkout(self.user, other, key=key)
        self.assertEqual(self.order_count(), 1)

    def test_same_key_with_a_different_expected_total_is_rejected(self):
        self.fill_cart(self.user, [(self.product, 1)])  # 100 + 5 + 49 = 154
        key = new_key()
        self.checkout(self.user, self.address, key=key, expected_total=Decimal("154.00"))

        with self.assertRaises(IdempotencyKeyReusedError):
            self.checkout(self.user, self.address, key=key, expected_total=Decimal("1.00"))
        with self.assertRaises(IdempotencyKeyReusedError):
            self.checkout(self.user, self.address, key=key)  # body without expected_total is a different body
        self.assertEqual(self.order_count(), 1)

    def test_equivalent_money_formats_count_as_the_same_body(self):
        self.fill_cart(self.user, [(self.product, 1)])
        key = new_key()
        first = self.checkout(self.user, self.address, key=key, expected_total=Decimal("154"))
        again = self.checkout(self.user, self.address, key=key, expected_total=Decimal("154.00"))
        self.assertEqual(first.order.id, again.order.id)

    def test_different_users_can_use_the_same_key(self):
        other = self.make_user()
        other_address = self.make_address(other)
        self.fill_cart(self.user, [(self.product, 1)])
        self.fill_cart(other, [(self.product, 1)])
        key = new_key()

        a = self.checkout(self.user, self.address, key=key)
        b = self.checkout(other, other_address, key=key)

        self.assertNotEqual(a.order.id, b.order.id)
        self.assertTrue(a.created and b.created)

    def test_another_users_key_is_never_replayed(self):
        other = self.make_user()
        other_address = self.make_address(other)
        self.fill_cart(self.user, [(self.product, 1)])
        key = new_key()
        mine = self.checkout(self.user, self.address, key=key)

        self.fill_cart(other, [(self.product, 1)])
        theirs = self.checkout(other, other_address, key=key)

        self.assertNotEqual(mine.order.id, theirs.order.id)
        self.assertEqual(theirs.order.user_id, other.id)

    def test_unique_index_is_the_backstop_when_the_application_checks_miss(self):
        self.fill_cart(self.user, [(self.product, 2)])
        key = new_key()
        first = self.checkout(self.user, self.address, key=key)
        self.fill_cart(self.user, [(self.product, 3)])
        stock_after_first = self.stock(self.product)
        cart_before = self.cart_state(self.user)

        real = OrderRepository.get_by_idempotency_key
        calls = {"n": 0}

        def blind_twice(repo, user_id, k):
            calls["n"] += 1
            return None if calls["n"] <= 2 else real(repo, user_id, k)

        with mock.patch.object(OrderRepository, "get_by_idempotency_key", blind_twice):
            second = self.checkout(self.user, self.address, key=key)

        self.assertFalse(second.created)
        self.assertEqual(second.order.id, first.order.id)
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock(self.product), stock_after_first, "the losing attempt's reservation was not undone")
        self.assertEqual(self.cart_state(self.user), cart_before)

    def test_unique_index_with_a_different_body_is_still_a_conflict(self):
        self.fill_cart(self.user, [(self.product, 1)])
        key = new_key()
        self.checkout(self.user, self.address, key=key)
        self.fill_cart(self.user, [(self.product, 1)])
        other = self.make_address(self.user)

        real = OrderRepository.get_by_idempotency_key
        calls = {"n": 0}

        def blind_twice(repo, user_id, k):
            calls["n"] += 1
            return None if calls["n"] <= 2 else real(repo, user_id, k)

        with mock.patch.object(OrderRepository, "get_by_idempotency_key", blind_twice):
            with self.assertRaises(IdempotencyKeyReusedError):
                self.checkout(self.user, other, key=key)
        self.assertEqual(self.order_count(), 1)


class CheckoutConcurrencyTests(CheckoutTestCase):
    """Real threads against real row locks. `run_concurrently` fails the
    test if any job hangs, which is how a deadlock would show up."""

    def place(self, user_id, address_id, key=None, expected_total=None):
        def run():
            with new_session() as s:
                result = CheckoutService(s, config=CONFIG).place_order(
                    user_id,
                    shipping_address_id=address_id,
                    idempotency_key=key or new_key(),
                    expected_total=expected_total,
                )
                return result.created, result.order.id

        return run

    def buyers(self, count, lines_for, coupon=None):
        """`count` users, each with an address and a filled cart."""
        buyers = []
        for n in range(count):
            user = self.make_user()
            address = self.make_address(user)
            self.fill_cart(user, lines_for(n), coupon)
            buyers.append((user.id, address.id))
        return buyers

    def test_same_key_sent_many_times_at_once_creates_one_order(self):
        user = self.make_user()
        address = self.make_address(user)
        product = self.make_product(stock=10, price="100.00")
        coupon = self.make_coupon(usage_limit=10)
        self.fill_cart(user, [(product, 2)], coupon)
        user_id, address_id, key = user.id, address.id, new_key()

        results = run_concurrently([self.place(user_id, address_id, key) for _ in range(10)])

        self.assertEqual([r for r in results if r[0] == "err"], [])
        outcomes = [r[1] for r in results]
        self.assertEqual(sum(1 for created, _ in outcomes if created), 1)
        self.assertEqual(len({order_id for _, order_id in outcomes}), 1)
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock(product), (10, 2))
        self.assertEqual(self.used_count(coupon), 1)

    def test_same_user_checking_out_with_different_keys_at_once_orders_the_cart_once(self):
        user = self.make_user()
        address = self.make_address(user)
        product = self.make_product(stock=10)
        self.fill_cart(user, [(product, 2)])
        user_id, address_id = user.id, address.id

        results = run_concurrently([self.place(user_id, address_id) for _ in range(6)])

        wins = [r for r in results if r[0] == "ok"]
        losses = [r[1] for r in results if r[0] == "err"]
        self.assertEqual(len(wins), 1)
        self.assertTrue(all(isinstance(e, EmptyCartError) for e in losses), losses)
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock(product), (10, 2))

    def test_the_last_units_go_to_exactly_as_many_buyers_as_there_are_units(self):
        product = self.make_product(stock=3, price="100.00")
        buyers = self.buyers(10, lambda n: [(product, 1)])

        results = run_concurrently([self.place(u, a) for u, a in buyers])

        wins = [r for r in results if r[0] == "ok"]
        losses = [r[1] for r in results if r[0] == "err"]
        self.assertEqual(len(wins), 3)
        self.assertTrue(all(isinstance(e, (InsufficientStockError, CartIssuesError)) for e in losses), losses)
        self.assertEqual(self.order_count(), 3)
        self.assertEqual(self.stock(product), (3, 3), "overselling or lost reservation")

    def test_two_big_orders_for_the_last_units_one_wins_and_the_loser_leaves_no_trace(self):
        a = self.make_product(stock=5)
        b = self.make_product(stock=5)
        buyers = self.buyers(2, lambda n: [(a, 4), (b, 4)])

        results = run_concurrently([self.place(u, ad) for u, ad in buyers])

        self.assertEqual(sorted(r[0] for r in results), ["err", "ok"])
        self.assertEqual(self.stock(a), (5, 4))
        self.assertEqual(self.stock(b), (5, 4))

    def test_the_last_coupon_use_goes_to_exactly_one_checkout(self):
        coupon = self.make_coupon(usage_limit=1)
        product = self.make_product(stock=20, price="100.00")
        buyers = self.buyers(8, lambda n: [(product, 1)], coupon)

        results = run_concurrently([self.place(u, a) for u, a in buyers])

        wins = [r for r in results if r[0] == "ok"]
        losses = [r[1] for r in results if r[0] == "err"]
        self.assertEqual(len(wins), 1)
        self.assertTrue(all(isinstance(e, InvalidCouponError) for e in losses), losses)
        self.assertEqual(self.used_count(coupon), 1)
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock(product), (20, 1), "a losing checkout kept its reservation")

    def test_a_coupon_with_room_is_counted_once_per_order(self):
        coupon = self.make_coupon(usage_limit=None)
        product = self.make_product(stock=50)
        buyers = self.buyers(12, lambda n: [(product, 1)], coupon)

        results = run_concurrently([self.place(u, a) for u, a in buyers])

        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(self.used_count(coupon), 12)
        self.assertEqual(self.stock(product), (50, 12))

    def test_carts_listing_the_same_products_in_opposite_order_do_not_deadlock(self):
        a = self.make_product(stock=100)
        b = self.make_product(stock=100)
        coupon = self.make_coupon()
        buyers = self.buyers(12, lambda n: [(a, 1), (b, 1)] if n % 2 else [(b, 1), (a, 1)], coupon)

        results = run_concurrently([self.place(u, ad) for u, ad in buyers])

        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(self.stock(a), (100, 12))
        self.assertEqual(self.stock(b), (100, 12))

    def test_checkouts_do_not_touch_each_others_carts(self):
        product = self.make_product(stock=50)
        buyers = self.buyers(2, lambda n: [(product, n + 1)])
        bystander = self.make_user()
        self.fill_cart(bystander, [(product, 4)])

        run_concurrently([self.place(u, a) for u, a in buyers])

        self.assertEqual(self.cart_state(bystander)[0], {product.id: 4})


if __name__ == "__main__":
    unittest.main()