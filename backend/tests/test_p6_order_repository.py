"""
Order repository: order numbers, ownership scoping, the cancel gate and the
idempotency-key index (PostgreSQL integration tests).

See tests/pg_support.py for how to run them.
"""

import re
import unittest
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.models import Order, OrderInventoryState, OrderPaymentStatus, OrderStatus
from app.repositories.order_repository import OrderRepository
from tests.pg_support import PostgresTestCase, new_session, run_concurrently

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


class OrderNumberTests(PostgresTestCase):
    def test_numbers_use_the_year_and_increase(self):
        repo = OrderRepository(self.db)
        first, second = repo.next_order_number(NOW), repo.next_order_number(NOW)
        pattern = re.compile(r"^PRM-2026-\d{6,}$")
        self.assertRegex(first, pattern)
        self.assertRegex(second, pattern)
        self.assertLess(int(first.rsplit("-", 1)[1]), int(second.rsplit("-", 1)[1]))

    def test_concurrent_checkouts_never_share_a_number(self):
        def job():
            with new_session() as s:
                repo = OrderRepository(s)
                numbers = [repo.next_order_number(NOW) for _ in range(10)]
                s.commit()
                return numbers

        results = run_concurrently([job for _ in range(10)])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        everything = [n for _, numbers in results for n in numbers]
        self.assertEqual(len(everything), 100)
        self.assertEqual(len(set(everything)), 100)


class OwnershipTests(PostgresTestCase):
    def test_a_customer_only_sees_their_own_orders(self):
        alice, bob = self.make_user(), self.make_user()
        p = self.make_product(stock=10)
        order = self.make_order(alice, [(p, 1)])
        repo = OrderRepository(self.db)
        self.assertIsNotNone(repo.get_for_user(order.id, alice.id))
        self.assertIsNone(repo.get_for_user(order.id, bob.id))

    def test_order_lookup_loads_the_items(self):
        user = self.make_user()
        p = self.make_product(stock=10)
        order = self.make_order(user, [(p, 2)])
        self.db.expire_all()
        found = OrderRepository(self.db).get_for_user(order.id, user.id)
        self.assertEqual([(i.sku_snapshot, i.quantity) for i in found.items], [(p.sku, 2)])

    def test_listing_is_scoped_newest_first_and_paged(self):
        alice, bob = self.make_user(), self.make_user()
        p = self.make_product(stock=100)
        mine = [self.make_order(alice, [(p, 1)]) for _ in range(5)]
        self.make_order(bob, [(p, 1)])
        repo = OrderRepository(self.db)
        page1, total = repo.list_for_user(alice.id, page=1, page_size=2)
        page3, _ = repo.list_for_user(alice.id, page=3, page_size=2)
        self.assertEqual(total, 5)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page3), 1)
        self.assertTrue(all(o.user_id == alice.id for o in page1 + page3))
        newest_first = [o.id for o in reversed(mine)]
        self.assertEqual([o.id for o in page1], newest_first[:2])


class CancelGateTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.p = self.make_product(stock=10)

    def fresh(self, order):
        self.db.expire_all()
        return self.db.get(Order, order.id)

    def test_cancels_a_pending_unpaid_reserved_order(self):
        order = self.make_order(self.user, [(self.p, 1)])
        self.assertTrue(OrderRepository(self.db).cancel_pending(order.id, NOW))
        self.db.commit()
        row = self.fresh(order)
        self.assertEqual(row.status, OrderStatus.CANCELLED)
        self.assertEqual(row.inventory_state, OrderInventoryState.RELEASED)
        self.assertEqual(row.cancelled_at, NOW)

    def test_a_second_cancel_changes_nothing(self):
        order = self.make_order(self.user, [(self.p, 1)])
        repo = OrderRepository(self.db)
        self.assertTrue(repo.cancel_pending(order.id, NOW))
        self.db.commit()
        self.assertFalse(repo.cancel_pending(order.id, NOW))

    def test_paid_or_progressed_orders_cannot_be_cancelled(self):
        cases = [
            dict(payment_status=OrderPaymentStatus.PAID),
            dict(status=OrderStatus.CONFIRMED),
            dict(status=OrderStatus.SHIPPED),
            dict(inventory_state=OrderInventoryState.CONSUMED),
            dict(inventory_state=OrderInventoryState.RELEASED),
        ]
        for overrides in cases:
            with self.subTest(overrides):
                order = self.make_order(self.user, [(self.p, 1)], reserve_stock=False, **overrides)
                self.assertFalse(OrderRepository(self.db).cancel_pending(order.id, NOW))
                self.db.rollback()

    def test_concurrent_cancels_have_exactly_one_winner(self):
        order = self.make_order(self.user, [(self.p, 1)])
        order_id = order.id

        def job():
            with new_session() as s:
                won = OrderRepository(s).cancel_pending(order_id, NOW)
                s.commit()
                return won

        results = run_concurrently([job for _ in range(8)])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(sum(1 for _, won in results if won), 1)


class IdempotencyIndexTests(PostgresTestCase):
    def new_order(self, user, key, number):
        return Order(
            user_id=user.id,
            order_number=number,
            subtotal=10,
            total_amount=10,
            idempotency_key=key,
            request_fingerprint="f" * 64,
        )

    def test_the_same_user_cannot_reuse_a_key(self):
        user = self.make_user()
        repo = OrderRepository(self.db)
        repo.add(self.new_order(user, "key-1", "N-1"))
        self.db.commit()
        with self.assertRaises(IntegrityError):
            repo.add(self.new_order(user, "key-1", "N-2"))
        self.db.rollback()
        self.assertEqual(self.db.query(Order).count(), 1)

    def test_different_users_may_use_the_same_key(self):
        alice, bob = self.make_user(), self.make_user()
        repo = OrderRepository(self.db)
        repo.add(self.new_order(alice, "same", "N-1"))
        repo.add(self.new_order(bob, "same", "N-2"))
        self.db.commit()
        self.assertEqual(self.db.query(Order).count(), 2)

    def test_orders_without_a_key_are_unrestricted(self):
        user = self.make_user()
        repo = OrderRepository(self.db)
        repo.add(self.new_order(user, None, "N-1"))
        repo.add(self.new_order(user, None, "N-2"))
        self.db.commit()
        self.assertEqual(self.db.query(Order).count(), 2)

    def test_lookup_by_key_is_scoped_to_the_user(self):
        alice, bob = self.make_user(), self.make_user()
        repo = OrderRepository(self.db)
        repo.add(self.new_order(alice, "k", "N-1"))
        self.db.commit()
        self.assertIsNotNone(repo.get_by_idempotency_key(alice.id, "k"))
        self.assertIsNone(repo.get_by_idempotency_key(bob.id, "k"))

    def test_concurrent_inserts_with_one_key_create_one_order(self):
        user = self.make_user()
        user_id = user.id

        def job(n):
            def run():
                with new_session() as s:
                    try:
                        OrderRepository(s).add(self.new_order_by_id(user_id, "dup", f"N-{n}"))
                        s.commit()
                        return True
                    except IntegrityError:
                        s.rollback()
                        return False

            return run

        results = run_concurrently([job(i) for i in range(8)])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(sum(1 for _, ok in results if ok), 1)
        self.assertEqual(self.db.query(Order).count(), 1)

    @staticmethod
    def new_order_by_id(user_id, key, number):
        return Order(
            user_id=user_id,
            order_number=number,
            subtotal=10,
            total_amount=10,
            idempotency_key=key,
            request_fingerprint="f" * 64,
        )


if __name__ == "__main__":
    unittest.main()