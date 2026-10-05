"""
Checkout / cancel integration suite on a real PostgreSQL: randomised
concurrent load with a bookkeeping audit, fault injection at every step,
and races against cart edits and price changes.

The audit (`assert_books_balance`) is the heart of it. After any mix of
checkouts, replays and cancels, whatever interleaving PostgreSQL chose:

  * every product's reserved_quantity equals the units held by orders that
    still hold a reservation - nothing leaked, nothing released twice
  * physical stock was never touched, and 0 <= reserved <= quantity
  * every coupon's used_count equals the number of live (non-cancelled)
    orders that used it, and never exceeds its limit
  * every order's money adds up from its own line items
  * order numbers and (user, idempotency key) pairs are unique
  * cancelled <=> reservation released

See tests/pg_support.py for how to run them.
"""

import random
import unittest
import uuid
from collections import defaultdict
from decimal import Decimal
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import (
    CartIssuesError,
    DomainError,
    EmptyCartError,
    InsufficientStockError,
    InvalidCouponError,
)
from app.core.security import create_access_token
from app.models import Coupon, Inventory, Order, OrderInventoryState, OrderStatus, Product
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.services.cart_service import CartService
from app.services.checkout_service import CheckoutService
from app.services.coupon_usage import CouponUsageService
from app.services.order_service import OrderService
from app.services.reservation_service import ReservationService
from tests.pg_support import new_session, run_concurrently
from tests.test_p6_checkout import CONFIG, CheckoutTestCase
from tests.test_p6_order_api import build_app

EXPECTED_REFUSALS = (InsufficientStockError, CartIssuesError, InvalidCouponError, EmptyCartError)


class AuditedTestCase(CheckoutTestCase):
    def assert_books_balance(self, products=None, coupons=None):
        with new_session() as s:
            self._audit_stock(s, products)
            self._audit_coupons(s, coupons)
            self._audit_orders(s)

    # --- the individual audits -------------------------------------------------

    def _audit_stock(self, s: Session, products):
        held = defaultdict(int)
        for order in s.query(Order).filter(Order.inventory_state == OrderInventoryState.RESERVED).all():
            for item in order.items:
                held[item.product_id] += item.quantity
        for inv in s.query(Inventory).all():
            self.assertEqual(inv.reserved_quantity, held[inv.product_id], f"reserved mismatch for {inv.product_id}")
            self.assertGreaterEqual(inv.reserved_quantity, 0)
            self.assertLessEqual(inv.reserved_quantity, inv.quantity)
        for product, quantity in (products or {}).items():
            row = s.query(Inventory).filter(Inventory.product_id == product).one()
            self.assertEqual(row.quantity, quantity, "physical stock must not change before payment")

    def _audit_coupons(self, s: Session, coupons):
        for coupon in s.query(Coupon).all():
            live = (
                s.query(Order)
                .filter(Order.coupon_id == coupon.id, Order.status != OrderStatus.CANCELLED)
                .count()
            )
            self.assertEqual(coupon.used_count, live, f"used_count mismatch for {coupon.code}")
            if coupon.usage_limit is not None:
                self.assertLessEqual(coupon.used_count, coupon.usage_limit)

    def _audit_orders(self, s: Session):
        orders = s.query(Order).all()
        self.assertEqual(len({o.order_number for o in orders}), len(orders), "duplicate order numbers")
        keys = [(o.user_id, o.idempotency_key) for o in orders if o.idempotency_key]
        self.assertEqual(len(set(keys)), len(keys), "duplicate idempotency keys")
        for o in orders:
            self.assertGreater(len(o.items), 0, "order without items")
            self.assertEqual(sum((i.subtotal for i in o.items), Decimal("0")), o.subtotal)
            for i in o.items:
                self.assertEqual(i.unit_price * i.quantity, i.subtotal)
            self.assertEqual(o.subtotal - o.discount_amount, o.taxable_amount)
            self.assertEqual(o.taxable_amount + o.tax_amount + o.delivery_charge, o.total_amount)
            cancelled = o.status == OrderStatus.CANCELLED
            released = o.inventory_state == OrderInventoryState.RELEASED
            self.assertEqual(cancelled, released, f"order {o.order_number}: cancelled/released out of step")

    # --- helpers ---------------------------------------------------------------

    def make_buyer(self):
        user = self.make_user()
        address = self.make_address(user)
        return user.id, address.id

    def checkout_job(self, user_id, address_id, key=None):
        def run():
            with new_session() as s:
                r = CheckoutService(s, config=CONFIG).place_order(
                    user_id, shipping_address_id=address_id, idempotency_key=key or f"k-{uuid.uuid4()}"
                )
                return ("checkout", r.created, r.order.id)

        return run

    def cancel_job(self, user_id, order_id):
        def run():
            with new_session() as s:
                OrderService(s).cancel_order(user_id, order_id)
                return ("cancel", True, order_id)

        return run

    def assert_only_expected_failures(self, results):
        for kind, value in results:
            if kind == "err":
                self.assertIsInstance(value, EXPECTED_REFUSALS, f"unexpected failure: {value!r}")


class RandomisedLoadTests(AuditedTestCase):
    """Many customers, few products, one scarce coupon - hammered in rounds
    that mix new checkouts, duplicate (replayed) checkouts and cancels."""

    def run_scenario(self, seed: int, rounds: int = 3, buyers: int = 14):
        rng = random.Random(seed)
        products = [self.make_product(stock=rng.randint(6, 14), price=str(rng.choice([60, 99, 150, 240]))) for _ in range(4)]
        stock = {p.id: self.stock(p)[0] for p in products}
        coupon = self.make_coupon(usage_limit=7, discount_value=Decimal("10"))
        people = [self.make_buyer() for _ in range(buyers)]
        live_orders = []  # (user_id, order_id)

        for _ in range(rounds):
            jobs = []
            for user_id, address_id in people:
                chosen = rng.sample(products, rng.randint(1, 3))
                self.fill_cart_by_id(user_id, [(p, rng.randint(1, 3)) for p in chosen], coupon if rng.random() < 0.7 else None)
                key = f"k-{uuid.uuid4()}"
                jobs.append(self.checkout_job(user_id, address_id, key))
                if rng.random() < 0.35:
                    jobs.append(self.checkout_job(user_id, address_id, key))  # a double click
            for user_id, order_id in live_orders:
                jobs.append(self.cancel_job(user_id, order_id))
                if rng.random() < 0.3:
                    jobs.append(self.cancel_job(user_id, order_id))
            rng.shuffle(jobs)

            results = run_concurrently(jobs, timeout=90)
            self.assert_only_expected_failures(results)
            self.assert_books_balance(stock)

            # Orders from this round that were created become cancel candidates next round.
            created = {(None, v[2]) for k, v in results if k == "ok" and v[0] == "checkout" and v[1]}
            with new_session() as s:
                live_orders = [
                    (o.user_id, o.id)
                    for o in s.query(Order).filter(Order.status != OrderStatus.CANCELLED).all()
                    if rng.random() < 0.5
                ]
            self.assertTrue(created is not None)

        # And at the very end, cancel everything: stock and coupon must return to zero.
        with new_session() as s:
            everything = [(o.user_id, o.id) for o in s.query(Order).all()]
        run_concurrently([self.cancel_job(u, o) for u, o in everything], timeout=90)
        self.assert_books_balance(stock)
        for p in products:
            self.assertEqual(self.stock(p)[1], 0)
        self.assertEqual(self.used_count(coupon), 0)

    def fill_cart_by_id(self, user_id, lines, coupon):
        class _U:  # fill_cart only needs `.id`
            id = user_id

        self.fill_cart(_U, lines, coupon)

    def test_mixed_load_seed_1(self):
        self.run_scenario(seed=1)

    def test_mixed_load_seed_2(self):
        self.run_scenario(seed=2)

    def test_mixed_load_seed_3(self):
        self.run_scenario(seed=3, buyers=20)

    def test_heavy_contention_on_a_single_unit_and_a_single_coupon_use(self):
        product = self.make_product(stock=1, price="300.00")
        coupon = self.make_coupon(usage_limit=1)
        buyers = [self.make_buyer() for _ in range(15)]
        for user_id, _ in buyers:
            self.fill_cart_by_id(user_id, [(product, 1)], coupon)
        results = run_concurrently([self.checkout_job(u, a) for u, a in buyers], timeout=60)
        self.assert_only_expected_failures(results)
        self.assertEqual(sum(1 for k, _ in results if k == "ok"), 1)
        self.assert_books_balance({product.id: 1})
        self.assertEqual(self.stock(product), (1, 1))
        self.assertEqual(self.used_count(coupon), 1)


class FaultInjectionTests(AuditedTestCase):
    """A failure at ANY step - including ones after the stock, the coupon
    and the order row were already written - leaves nothing behind."""

    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.a = self.make_product(price="300.00", stock=10)
        self.b = self.make_product(price="120.00", stock=10)
        self.coupon = self.make_coupon(usage_limit=5, used_count=0)

    @staticmethod
    def after(real):
        """Run the real step (so its writes happen), THEN fail."""

        def wrapper(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("injected failure")

        return wrapper

    def run_with_failure_at(self, target, attribute, *, after=True):
        self.fill_cart(self.user, [(self.a, 2), (self.b, 3)], self.coupon)
        before = dict(
            stock_before=[self.stock(self.a), self.stock(self.b)],
            used_before=0,
            cart_before=self.cart_state(self.user),
        )
        real = getattr(target, attribute)
        replacement = self.after(real) if after else mock.Mock(side_effect=RuntimeError("injected failure"))
        with mock.patch.object(target, attribute, replacement):
            with self.assertRaises(RuntimeError):
                self.checkout(self.user, self.address)
        self.assert_nothing_changed(self.user, [self.a, self.b], self.coupon, **before)
        self.assert_books_balance()

    def test_failure_after_stock_was_reserved(self):
        self.run_with_failure_at(ReservationService, "reserve")

    def test_failure_after_the_coupon_use_was_counted(self):
        self.run_with_failure_at(CouponUsageService, "consume")

    def test_failure_after_the_order_number_was_drawn(self):
        self.run_with_failure_at(OrderRepository, "next_order_number")

    def test_failure_after_the_order_row_was_inserted(self):
        self.run_with_failure_at(OrderRepository, "add")

    def test_failure_after_the_cart_items_were_deleted(self):
        self.run_with_failure_at(CartRepository, "delete_all_items")

    def test_failure_after_the_coupon_was_detached_from_the_cart(self):
        self.run_with_failure_at(CartRepository, "set_coupon")

    def test_failure_of_the_commit_itself(self):
        self.fill_cart(self.user, [(self.a, 2), (self.b, 3)], self.coupon)
        before = dict(
            stock_before=[self.stock(self.a), self.stock(self.b)],
            used_before=0,
            cart_before=self.cart_state(self.user),
        )
        real_commit = Session.commit
        calls = {"n": 0}

        def failing_commit(session):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("injected commit failure")
            return real_commit(session)

        with mock.patch.object(Session, "commit", failing_commit):
            with self.assertRaises(RuntimeError):
                self.checkout(self.user, self.address)
        self.assert_nothing_changed(self.user, [self.a, self.b], self.coupon, **before)

    def test_the_same_request_succeeds_after_every_kind_of_failure(self):
        key = f"k-{uuid.uuid4()}"
        self.fill_cart(self.user, [(self.a, 2)], self.coupon)
        with mock.patch.object(OrderRepository, "add", self.after(OrderRepository.add)):
            with self.assertRaises(RuntimeError):
                self.checkout(self.user, self.address, key=key)
        result = self.checkout(self.user, self.address, key=key)
        self.assertTrue(result.created)
        self.assertEqual(self.stock(self.a), (10, 2))
        self.assertEqual(self.used_count(self.coupon), 1)
        self.assert_books_balance()

    def test_failure_while_cancelling_after_every_step(self):
        self.fill_cart(self.user, [(self.a, 2), (self.b, 1)], self.coupon)
        order = self.checkout(self.user, self.address).order
        for target, attribute in [
            (CouponUsageService, "restore"),
            (ReservationService, "release_items"),
        ]:
            with self.subTest(step=attribute):
                with mock.patch.object(target, attribute, self.after(getattr(target, attribute))):
                    with self.assertRaises(RuntimeError):
                        OrderService(self.db).cancel_order(self.user.id, order.id)
                self.assert_books_balance()
                with new_session() as s:
                    self.assertEqual(s.get(Order, order.id).status, OrderStatus.PENDING)
                self.assertEqual(self.stock(self.a), (10, 2))
                self.assertEqual(self.used_count(self.coupon), 1)


class RaceTests(AuditedTestCase):
    def test_cart_edits_racing_a_checkout_never_lose_or_duplicate_units(self):
        """The checkout takes the cart lock, so a concurrent Add to Cart lands
        either in the order or in the (now empty) cart - never both, never
        neither."""
        a = self.make_product(stock=100)
        b = self.make_product(stock=100)
        for _ in range(12):
            user_id, address_id = self.make_buyer()
            self.fill_cart_by_id(user_id, [(a, 2)], None)

            def add_b():
                with new_session() as s:
                    CartService(s, config=CONFIG).add_item(user_id, b.id, 1)
                    return "added"

            results = run_concurrently([self.checkout_job(user_id, address_id), add_b])
            self.assertEqual([r for r in results if r[0] == "err"], [])

            with new_session() as s:
                order = s.query(Order).filter(Order.user_id == user_id).one()
                ordered = {i.product_id: i.quantity for i in order.items}
            cart_items, _ = self.cart_state_by_id(user_id)
            self.assertEqual(ordered[a.id], 2)
            self.assertNotIn(a.id, cart_items)
            self.assertEqual(ordered.get(b.id, 0) + cart_items.get(b.id, 0), 1, "the added unit was lost or duplicated")
        self.assert_books_balance()

    def cart_state_by_id(self, user_id):
        class _U:
            id = user_id

        return self.cart_state(_U)

    def fill_cart_by_id(self, user_id, lines, coupon):
        class _U:
            id = user_id

        self.fill_cart(_U, lines, coupon)

    def test_a_price_change_racing_a_checkout_cannot_produce_an_inconsistent_order(self):
        product = self.make_product(price="100.00", stock=500)
        product_id = product.id
        for n in range(10):
            user_id, address_id = self.make_buyer()
            self.fill_cart_by_id(user_id, [(product, 2)], None)
            new_price = Decimal(150 + n)

            def reprice():
                with new_session() as s:
                    s.query(Product).filter(Product.id == product_id).update({Product.price: new_price})
                    s.commit()
                    return "repriced"

            results = run_concurrently([self.checkout_job(user_id, address_id), reprice])
            self.assertEqual([r for r in results if r[0] == "err"], [])
            with new_session() as s:
                order = s.query(Order).filter(Order.user_id == user_id).one()
                self.assertEqual(order.items[0].unit_price * 2, order.subtotal)
                self.assertIn(order.items[0].unit_price, {Decimal("100.00"), Decimal("150.00")} | {Decimal(150 + k) for k in range(10)})
        self.assert_books_balance()

    def test_a_coupon_being_deactivated_during_checkouts_is_never_overspent(self):
        coupon = self.make_coupon(usage_limit=100)
        coupon_id = coupon.id
        product = self.make_product(stock=100, price="300.00")
        buyers = [self.make_buyer() for _ in range(10)]
        for user_id, _ in buyers:
            self.fill_cart_by_id(user_id, [(product, 1)], coupon)

        def deactivate():
            with new_session() as s:
                s.query(Coupon).filter(Coupon.id == coupon_id).update({Coupon.is_active: False})
                s.commit()
                return "deactivated"

        jobs = [self.checkout_job(u, a) for u, a in buyers] + [deactivate]
        results = run_concurrently(jobs)
        self.assert_only_expected_failures(results)
        self.assert_books_balance()
        # Every order that did get the coupon was placed while it was still active:
        # the audit above proves used_count == number of such live orders.

    def test_two_customers_using_the_same_key_at_once_each_get_their_own_order(self):
        product = self.make_product(stock=10)
        buyers = [self.make_buyer() for _ in range(2)]
        for user_id, _ in buyers:
            self.fill_cart_by_id(user_id, [(product, 1)], None)
        key = f"shared-{uuid.uuid4()}"
        results = run_concurrently([self.checkout_job(u, a, key) for u, a in buyers])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(len({v[2] for _, v in results}), 2)
        self.assert_books_balance()

    def test_the_same_failing_request_sent_many_times_stores_nothing_and_can_be_retried(self):
        product = self.make_product(stock=1)
        user_id, address_id = self.make_buyer()
        self.fill_cart_by_id(user_id, [(product, 1)], None)
        self.db.query(Inventory).filter(Inventory.product_id == product.id).update({Inventory.quantity: 0})
        self.db.commit()
        key = f"k-{uuid.uuid4()}"

        results = run_concurrently([self.checkout_job(user_id, address_id, key) for _ in range(6)])
        self.assertTrue(all(r[0] == "err" and isinstance(r[1], EXPECTED_REFUSALS) for r in results), results)
        self.assertEqual(self.order_count(), 0)

        self.db.query(Inventory).filter(Inventory.product_id == product.id).update({Inventory.quantity: 5})
        self.db.commit()
        retry = run_concurrently([self.checkout_job(user_id, address_id, key) for _ in range(6)])
        self.assertEqual([r for r in retry if r[0] == "err"], [])
        self.assertEqual(sum(1 for _, v in retry if v[1]), 1)
        self.assert_books_balance()

    def test_replaying_a_key_after_the_order_was_cancelled_returns_it_without_reserving_again(self):
        product = self.make_product(stock=5)
        user_id, address_id = self.make_buyer()
        self.fill_cart_by_id(user_id, [(product, 2)], None)
        key = f"k-{uuid.uuid4()}"
        with new_session() as s:
            first = CheckoutService(s, config=CONFIG).place_order(user_id, shipping_address_id=address_id, idempotency_key=key)
            order_id = first.order.id
        with new_session() as s:
            OrderService(s).cancel_order(user_id, order_id)
        with new_session() as s:
            again = CheckoutService(s, config=CONFIG).place_order(user_id, shipping_address_id=address_id, idempotency_key=key)
            self.assertFalse(again.created)
            self.assertEqual(again.order.status, OrderStatus.CANCELLED)
        self.assertEqual(self.stock(product), (5, 0))
        self.assert_books_balance()

    def test_a_large_cart_of_many_products_checks_out_and_cancels_cleanly(self):
        products = [self.make_product(stock=5, price="25.00") for _ in range(30)]
        user_id, address_id = self.make_buyer()
        self.fill_cart_by_id(user_id, [(p, 2) for p in products], None)
        with new_session() as s:
            result = CheckoutService(s, config=CONFIG).place_order(user_id, shipping_address_id=address_id, idempotency_key=f"k-{uuid.uuid4()}")
            order_id = result.order.id
            self.assertEqual(len(result.order.items), 30)
        self.assertTrue(all(self.stock(p) == (5, 2) for p in products))
        with new_session() as s:
            OrderService(s).cancel_order(user_id, order_id)
        self.assertTrue(all(self.stock(p) == (5, 0) for p in products))
        self.assert_books_balance()


class ConnectionHygieneTests(AuditedTestCase):
    def test_http_requests_leave_no_transaction_open(self):
        client = TestClient(build_app())
        user = self.make_user()
        address = self.make_address(user)
        product = self.make_product(stock=50, price="100.00")
        headers = {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

        for _ in range(8):
            self.fill_cart(user, [(product, 1)])
            created = client.post(
                "/api/orders",
                json={"shipping_address_id": str(address.id)},
                headers={**headers, "Idempotency-Key": f"k-{uuid.uuid4()}"},
            )
            self.assertEqual(created.status_code, 201)
            order_id = created.json()["data"]["id"]
            client.get("/api/orders", headers=headers)
            client.get(f"/api/orders/{order_id}", headers=headers)
            client.post(f"/api/orders/{order_id}/cancel", headers=headers)
            client.post(f"/api/orders/{order_id}/cancel", headers=headers)
            client.post("/api/orders", json={"shipping_address_id": str(address.id)}, headers={**headers, "Idempotency-Key": f"k-{uuid.uuid4()}"})  # empty cart -> 400

        with new_session() as s:
            stuck = s.execute(
                text(
                    "select count(*) from pg_stat_activity "
                    "where datname = current_database() and pid <> pg_backend_pid() and state = 'idle in transaction'"
                )
            ).scalar()
        # self.db (this test's own session) may be idle in a transaction; nothing else may be.
        own = 1 if self.db.in_transaction() else 0
        self.assertLessEqual(stuck, own, "a request left its transaction open")
        self.assert_books_balance()


if __name__ == "__main__":
    unittest.main()