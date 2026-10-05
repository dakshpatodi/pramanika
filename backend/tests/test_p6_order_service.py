"""
Order reads and cancellation (PostgreSQL integration tests).

See tests/pg_support.py for how to run them.
"""

import unittest
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from sqlalchemy import text

from app.core.exceptions import OrderNotCancellableError, OrderNotFoundError
from app.models import Order, OrderInventoryState, OrderPaymentStatus, OrderStatus
from app.services.order_service import OrderService
from app.services.reservation_service import ReservationService
from tests.pg_support import PostgresTestCase, new_session, run_concurrently
from tests.test_p6_checkout import CONFIG, CheckoutTestCase


class OrderCancelTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=10)
        self.coupon = self.make_coupon(usage_limit=3, used_count=0)

    def place(self, qty=2, coupon=None, user=None, address=None):
        user = user or self.user
        self.fill_cart(user, [(self.product, qty)], coupon)
        return self.checkout(user, address or self.address).order

    def order_row(self, order_id):
        with new_session() as s:
            o = s.get(Order, order_id)
            return o.status, o.payment_status, o.inventory_state, o.cancelled_at

    def test_cancel_releases_stock_restores_the_coupon_and_marks_the_order(self):
        order = self.place(qty=3, coupon=self.coupon)
        self.assertEqual(self.stock(self.product), (10, 3))
        self.assertEqual(self.used_count(self.coupon), 1)

        result = OrderService(self.db).cancel_order(self.user.id, order.id)

        self.assertEqual(result.status, OrderStatus.CANCELLED)
        self.assertFalse(result.can_cancel)
        self.assertIsNotNone(result.cancelled_at)
        self.assertEqual(self.stock(self.product), (10, 0))
        self.assertEqual(self.used_count(self.coupon), 0)
        status, payment, inventory, cancelled_at = self.order_row(order.id)
        self.assertEqual((status, payment, inventory), (OrderStatus.CANCELLED, OrderPaymentStatus.PENDING, OrderInventoryState.RELEASED))
        self.assertIsNotNone(cancelled_at)

    def test_cancelling_an_order_without_a_coupon_leaves_coupons_alone(self):
        bystander = self.make_coupon(used_count=2, usage_limit=5)
        order = self.place()
        OrderService(self.db).cancel_order(self.user.id, order.id)
        self.assertEqual(self.used_count(bystander), 2)

    def test_cancelling_twice_changes_nothing_the_second_time(self):
        order = self.place(qty=2, coupon=self.coupon)
        service = OrderService(self.db)
        first = service.cancel_order(self.user.id, order.id)
        again = service.cancel_order(self.user.id, order.id)

        self.assertEqual(again.status, OrderStatus.CANCELLED)
        self.assertEqual(again.cancelled_at, first.cancelled_at)
        self.assertEqual(self.stock(self.product), (10, 0), "released twice")
        self.assertEqual(self.used_count(self.coupon), 0, "coupon restored twice")

    def test_a_cancel_never_touches_other_orders_reservations_or_coupon_uses(self):
        other = self.make_user()
        other_address = self.make_address(other)
        keep = self.place(qty=4, coupon=self.coupon, user=other, address=other_address)
        mine = self.place(qty=2, coupon=self.coupon)
        self.assertEqual(self.stock(self.product), (10, 6))
        self.assertEqual(self.used_count(self.coupon), 2)

        OrderService(self.db).cancel_order(self.user.id, mine.id)

        self.assertEqual(self.stock(self.product), (10, 4))
        self.assertEqual(self.used_count(self.coupon), 1)
        self.assertEqual(self.order_row(keep.id)[0], OrderStatus.PENDING)

    def test_someone_elses_order_looks_like_it_does_not_exist_and_is_untouched(self):
        order = self.place(qty=2, coupon=self.coupon)
        stranger = self.make_user()
        with self.assertRaises(OrderNotFoundError):
            OrderService(self.db).cancel_order(stranger.id, order.id)
        with self.assertRaises(OrderNotFoundError):
            OrderService(self.db).cancel_order(self.user.id, uuid.uuid4())
        self.assertEqual(self.order_row(order.id)[0], OrderStatus.PENDING)
        self.assertEqual(self.stock(self.product), (10, 2))
        self.assertEqual(self.used_count(self.coupon), 1)

    def test_paid_and_progressed_orders_cannot_be_cancelled(self):
        cases = [
            (OrderStatus.PENDING, OrderPaymentStatus.PAID, "paid"),
            (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID, "confirmed"),
            (OrderStatus.SHIPPED, OrderPaymentStatus.PAID, "shipped"),
            (OrderStatus.DELIVERED, OrderPaymentStatus.PAID, "delivered"),
            (OrderStatus.REFUNDED, OrderPaymentStatus.REFUNDED, "refunded"),
        ]
        for status, payment, word in cases:
            with self.subTest(status=status.value, payment=payment.value):
                order = self.make_order(self.user, [(self.product, 1)], coupon=self.coupon, status=status, payment_status=payment)
                before = (self.stock(self.product), self.used_count(self.coupon))
                with self.assertRaises(OrderNotCancellableError) as ctx:
                    OrderService(self.db).cancel_order(self.user.id, order.id)
                self.assertIn(word, ctx.exception.message)
                self.assertEqual((self.stock(self.product), self.used_count(self.coupon)), before)
                self.assertEqual(self.order_row(order.id)[0], status)

    def test_an_order_whose_stock_was_already_sold_cannot_be_cancelled(self):
        order = self.place(qty=2)
        # Phase 7 will do this when payment is confirmed.
        ReservationService(self.db).consume_for_order(order)
        self.db.query(Order).filter(Order.id == order.id).update({Order.payment_status: OrderPaymentStatus.PAID})
        self.db.commit()
        before = self.stock(self.product)
        with self.assertRaises(OrderNotCancellableError):
            OrderService(self.db).cancel_order(self.user.id, order.id)
        self.assertEqual(self.stock(self.product), before)

    def test_a_failure_part_way_through_a_cancel_rolls_everything_back(self):
        order = self.place(qty=2, coupon=self.coupon)
        with mock.patch.object(ReservationService, "release_items", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                OrderService(self.db).cancel_order(self.user.id, order.id)
        status, _, inventory, cancelled_at = self.order_row(order.id)
        self.assertEqual((status, inventory, cancelled_at), (OrderStatus.PENDING, OrderInventoryState.RESERVED, None))
        self.assertEqual(self.stock(self.product), (10, 2))
        self.assertEqual(self.used_count(self.coupon), 1)

    def test_the_restored_coupon_use_and_stock_can_be_used_again(self):
        coupon = self.make_coupon(usage_limit=1)
        product = self.make_product(stock=1, price="300.00")
        first = self.make_user()
        first_address = self.make_address(first)
        second = self.make_user()
        second_address = self.make_address(second)

        self.fill_cart(first, [(product, 1)], coupon)
        order = self.checkout(first, first_address).order
        self.fill_cart(second, [(product, 1)], coupon)
        with self.assertRaises(Exception):
            self.checkout(second, second_address)  # last unit and last coupon use are taken

        OrderService(self.db).cancel_order(first.id, order.id)

        self.fill_cart(second, [(product, 1)], coupon)
        self.assertTrue(self.checkout(second, second_address).created)
        self.assertEqual(self.stock(product), (1, 1))
        self.assertEqual(self.used_count(coupon), 1)

    def test_losing_the_gate_to_a_payment_is_a_conflict_with_no_side_effects(self):
        """A payment lands between our read and our cancel statement."""
        from app.repositories.order_repository import OrderRepository

        order = self.place(qty=2, coupon=self.coupon)
        real = OrderRepository.cancel_pending

        def payment_lands_first(repo, order_id, now):
            with new_session() as other:
                other.query(Order).filter(Order.id == order_id).update({Order.payment_status: OrderPaymentStatus.PAID})
                other.commit()
            return real(repo, order_id, now)

        with mock.patch.object(OrderRepository, "cancel_pending", payment_lands_first):
            with self.assertRaises(OrderNotCancellableError):
                OrderService(self.db).cancel_order(self.user.id, order.id)

        self.assertEqual(self.order_row(order.id)[0], OrderStatus.PENDING)
        self.assertEqual(self.stock(self.product), (10, 2))
        self.assertEqual(self.used_count(self.coupon), 1)

    def test_losing_the_gate_to_another_cancel_is_a_quiet_success_with_no_side_effects(self):
        from app.repositories.order_repository import OrderRepository

        order = self.place(qty=2, coupon=self.coupon)
        real = OrderRepository.cancel_pending

        racing = {"done": False}

        def other_cancel_wins(repo, order_id, now):
            if not racing["done"]:
                racing["done"] = True  # the other request's own cancel must not recurse into this hook
                with new_session() as other:
                    OrderService(other).cancel_order(self.user.id, order_id)
            return real(repo, order_id, now)  # for us this now finds nothing to change -> False

        with mock.patch.object(OrderRepository, "cancel_pending", other_cancel_wins):
            result = OrderService(self.db).cancel_order(self.user.id, order.id)

        self.assertEqual(result.status, OrderStatus.CANCELLED)
        self.assertEqual(self.stock(self.product), (10, 0), "released twice")
        self.assertEqual(self.used_count(self.coupon), 0, "coupon restored twice")

    def test_many_simultaneous_cancels_have_exactly_one_effect(self):
        order = self.place(qty=3, coupon=self.coupon)
        user_id, order_id = self.user.id, order.id

        def job():
            with new_session() as s:
                return OrderService(s).cancel_order(user_id, order_id).status

        results = run_concurrently([job for _ in range(10)])

        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertTrue(all(r[1] == OrderStatus.CANCELLED for r in results))
        self.assertEqual(self.stock(self.product), (10, 0))
        self.assertEqual(self.used_count(self.coupon), 0)

    def test_checkouts_and_cancels_running_together_keep_the_books_balanced(self):
        coupon = self.make_coupon(usage_limit=None)
        a = self.make_product(stock=100)
        b = self.make_product(stock=100)
        a_id, b_id = a.id, b.id

        # 6 customers already hold an order each; 6 more are about to check out.
        existing = []
        for n in range(6):
            user = self.make_user()
            address = self.make_address(user)
            lines = [(a, 2), (b, 1)] if n % 2 else [(b, 1), (a, 2)]
            self.fill_cart(user, lines, coupon)
            existing.append((user.id, self.checkout(user, address).order.id))
        newcomers = []
        for n in range(6):
            user = self.make_user()
            address = self.make_address(user)
            self.fill_cart(user, [(a, 2), (b, 1)] if n % 2 else [(b, 1), (a, 2)], coupon)
            newcomers.append((user.id, address.id))

        from app.services.checkout_service import CheckoutService

        def cancel(user_id, order_id):
            def run():
                with new_session() as s:
                    return OrderService(s).cancel_order(user_id, order_id).status

            return run

        def checkout(user_id, address_id):
            def run():
                with new_session() as s:
                    return CheckoutService(s, config=CONFIG).place_order(
                        user_id, shipping_address_id=address_id, idempotency_key=f"k-{uuid.uuid4()}"
                    ).created

            return run

        jobs = [cancel(u, o) for u, o in existing] + [checkout(u, ad) for u, ad in newcomers]
        results = run_concurrently(jobs, timeout=60)

        self.assertEqual([r for r in results if r[0] == "err"], [])
        with new_session() as s:
            live = s.query(Order).filter(Order.status != OrderStatus.CANCELLED).all()
            self.assertEqual(len(live), 6)
            self.assertTrue(all(o.inventory_state == OrderInventoryState.RESERVED for o in live))
        self.assertEqual(self.stock(a), (100, 12))
        self.assertEqual(self.stock(b), (100, 6))
        self.assertEqual(self.used_count(coupon), 6)


class OrderReadTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=500, name="Oats")

    def place(self, user=None, address=None, qty=1):
        user = user or self.user
        self.fill_cart(user, [(self.product, qty)])
        return self.checkout(user, address or self.address).order

    def test_get_order_returns_the_full_snapshot(self):
        coupon = self.make_coupon(discount_value=Decimal("10"))
        self.fill_cart(self.user, [(self.product, 2)], coupon)
        order = self.checkout(self.user, self.address).order

        data = OrderService(self.db).get_order(self.user.id, order.id)

        self.assertEqual(data.id, order.id)
        self.assertEqual(data.status, OrderStatus.PENDING)
        self.assertEqual(data.payment_status, OrderPaymentStatus.PENDING)
        self.assertTrue(data.can_cancel)
        self.assertEqual(data.coupon_code, coupon.code)
        self.assertEqual(data.item_count, 2)
        self.assertEqual([(i.product_name, i.unit_price, i.quantity, i.line_total) for i in data.items], [("Oats", 100.0, 2, 200.0)])
        self.assertEqual(
            (data.totals.subtotal, data.totals.discount, data.totals.taxable_amount, data.totals.gst, data.totals.delivery_charge, data.totals.total),
            (200.0, 20.0, 180.0, 9.0, 49.0, 238.0),
        )
        self.assertEqual((data.shipping_address.city, data.shipping_address.postal_code), ("Pune", "411001"))

    def test_get_order_hides_other_peoples_orders(self):
        order = self.place()
        with self.assertRaises(OrderNotFoundError):
            OrderService(self.db).get_order(self.make_user().id, order.id)
        with self.assertRaises(OrderNotFoundError):
            OrderService(self.db).get_order(self.user.id, uuid.uuid4())

    def test_list_is_newest_first_paginated_and_only_mine(self):
        stranger = self.make_user()
        stranger_address = self.make_address(stranger)
        self.place(user=stranger, address=stranger_address)
        mine = [self.place(qty=n + 1) for n in range(5)]
        # make the ordering unambiguous regardless of clock resolution
        for offset, order in enumerate(mine):
            self.db.query(Order).filter(Order.id == order.id).update(
                {Order.created_at: Order.created_at + timedelta(minutes=offset)}, synchronize_session=False
            )
        self.db.commit()

        service = OrderService(self.db)
        page1 = service.list_orders(self.user.id, page=1, page_size=2)
        page3 = service.list_orders(self.user.id, page=3, page_size=2)
        beyond = service.list_orders(self.user.id, page=9, page_size=2)

        self.assertEqual([o.id for o in page1.orders], [mine[4].id, mine[3].id])
        self.assertEqual([o.id for o in page3.orders], [mine[0].id])
        self.assertEqual(
            (page1.pagination.total, page1.pagination.total_pages, page1.pagination.has_next, page1.pagination.has_previous),
            (5, 3, True, False),
        )
        self.assertEqual((page3.pagination.has_next, page3.pagination.has_previous), (False, True))
        self.assertEqual((beyond.orders, beyond.pagination.total), ([], 5))
        self.assertEqual(page1.orders[0].item_count, 5)
        self.assertEqual(page1.orders[0].item_names, ["Oats"])
        self.assertEqual(page1.orders[0].total, 5 * 100 + 25.0 + 0.0)  # 500 (>=500 so free delivery) + 5% GST

    def test_empty_history(self):
        data = OrderService(self.db).list_orders(self.user.id, page=1, page_size=10)
        self.assertEqual((data.orders, data.pagination.total, data.pagination.total_pages), ([], 0, 0))


if __name__ == "__main__":
    unittest.main()