"""
Stock reservation, release and consumption (PostgreSQL integration tests).

See tests/pg_support.py for how to run them.
"""

import unittest

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import InsufficientStockError
from app.models import Inventory, OrderInventoryState, Product
from app.services.reservation_service import ReservationInvariantError, ReservationService
from tests.pg_support import PostgresTestCase, new_session, run_concurrently


def reserve_one(product_id):
    """A checkout-sized unit of work in its own session/transaction."""

    def job():
        with new_session() as s:
            try:
                ReservationService(s).reserve([(product_id, 1)])
                s.commit()
                return True
            except InsufficientStockError:
                s.rollback()
                return False

    return job


class ReserveTests(PostgresTestCase):
    def reserve(self, lines):
        service = ReservationService(self.db)
        service.reserve(lines)
        self.db.commit()

    def test_reserves_available_units(self):
        p = self.make_product(stock=10)
        self.reserve([(p.id, 3)])
        self.assertEqual(self.stock(p), (10, 3))

    def test_the_exact_remaining_stock_can_be_reserved(self):
        p = self.make_product(stock=10, reserved=4)
        self.reserve([(p.id, 6)])
        self.assertEqual(self.stock(p), (10, 10))

    def test_one_over_the_available_stock_is_refused_and_nothing_changes(self):
        p = self.make_product(stock=10, reserved=4)
        with self.assertRaises(InsufficientStockError) as ctx:
            ReservationService(self.db).reserve([(p.id, 7)])
        self.db.rollback()
        self.assertEqual(ctx.exception.available, 6)
        self.assertEqual(self.stock(p), (10, 4))

    def test_existing_reservations_count_against_availability(self):
        p = self.make_product(stock=10, reserved=8)
        with self.assertRaises(InsufficientStockError):
            ReservationService(self.db).reserve([(p.id, 3)])
        self.db.rollback()
        self.reserve([(p.id, 2)])
        self.assertEqual(self.stock(p), (10, 10))

    def test_out_of_stock_product_is_refused(self):
        p = self.make_product(stock=0)
        with self.assertRaises(InsufficientStockError) as ctx:
            ReservationService(self.db).reserve([(p.id, 1)])
        self.db.rollback()
        self.assertEqual(ctx.exception.available, 0)

    def test_product_without_an_inventory_row_is_refused(self):
        p = self.make_product(stock=5)
        self.db.query(Inventory).filter(Inventory.product_id == p.id).delete()
        self.db.commit()
        with self.assertRaises(InsufficientStockError) as ctx:
            ReservationService(self.db).reserve([(p.id, 1)])
        self.db.rollback()
        self.assertEqual(ctx.exception.available, 0)

    def test_all_or_nothing_when_a_later_line_fails(self):
        a = self.make_product(stock=10)
        b = self.make_product(stock=1)
        with self.assertRaises(InsufficientStockError):
            ReservationService(self.db).reserve([(a.id, 4), (b.id, 2)])
        self.db.rollback()  # what checkout's transaction does
        self.assertEqual(self.stock(a), (10, 0))
        self.assertEqual(self.stock(b), (1, 0))

    def test_lines_for_the_same_product_are_combined(self):
        p = self.make_product(stock=5)
        with self.assertRaises(InsufficientStockError):
            ReservationService(self.db).reserve([(p.id, 3), (p.id, 3)])  # 6 > 5
        self.db.rollback()
        self.reserve([(p.id, 3), (p.id, 2)])
        self.assertEqual(self.stock(p), (5, 5))

    def test_non_positive_quantities_are_rejected(self):
        p = self.make_product(stock=5)
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                ReservationService(self.db).reserve([(p.id, bad)])
        self.assertEqual(self.stock(p), (5, 0))

    def test_the_database_itself_refuses_reserved_over_quantity(self):
        p = self.make_product(stock=5)
        with self.assertRaises(IntegrityError):
            self.db.query(Inventory).filter(Inventory.product_id == p.id).update({Inventory.reserved_quantity: 6})
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.stock(p), (5, 0))


class ConcurrentReserveTests(PostgresTestCase):
    def test_exactly_as_many_buyers_succeed_as_there_are_units(self):
        p = self.make_product(stock=5)
        results = run_concurrently([reserve_one(p.id) for _ in range(16)])
        errors = [r[1] for r in results if r[0] == "err"]
        self.assertEqual(errors, [])
        won = sum(1 for _, ok in results if ok)
        self.assertEqual(won, 5)
        self.assertEqual(self.stock(p), (5, 5))

    def test_only_one_of_two_orders_for_the_last_units_succeeds(self):
        p = self.make_product(stock=5)
        product_id = p.id  # read ids on the test thread: ORM objects belong to self.db

        def big():
            with new_session() as s:
                try:
                    ReservationService(s).reserve([(product_id, 3)])
                    s.commit()
                    return True
                except InsufficientStockError:
                    s.rollback()
                    return False

        results = run_concurrently([big, big])
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertEqual(sorted(r[1] for r in results), [False, True])
        self.assertEqual(self.stock(p), (5, 3))

    def test_orders_listing_products_in_opposite_order_do_not_deadlock(self):
        a = self.make_product(stock=100)
        b = self.make_product(stock=100)
        a_id, b_id = a.id, b.id  # read ids on the test thread: ORM objects belong to self.db

        def worker(first, second):
            def job():
                with new_session() as s:
                    ReservationService(s).reserve([(first, 1), (second, 1)])
                    s.commit()
                    return True

            return job

        jobs = [worker(a_id, b_id) if i % 2 == 0 else worker(b_id, a_id) for i in range(24)]
        results = run_concurrently(jobs, timeout=60)
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(self.stock(a), (100, 24))
        self.assertEqual(self.stock(b), (100, 24))


class ReleaseAndConsumeTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.a = self.make_product(stock=10)
        self.b = self.make_product(stock=10)
        self.order = self.make_order(self.user, [(self.a, 3), (self.b, 2)])  # reserves 3 and 2

    def state(self):
        self.db.expire_all()
        return self.db.get(type(self.order), self.order.id).inventory_state

    def test_setup_reserved_the_stock(self):
        self.assertEqual(self.stock(self.a), (10, 3))
        self.assertEqual(self.stock(self.b), (10, 2))

    def test_release_returns_the_units_and_marks_the_order_released(self):
        self.assertTrue(ReservationService(self.db).release_for_order(self.order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (10, 0))
        self.assertEqual(self.stock(self.b), (10, 0))
        self.assertEqual(self.state(), OrderInventoryState.RELEASED)

    def test_a_second_release_does_nothing(self):
        service = ReservationService(self.db)
        self.assertTrue(service.release_for_order(self.order))
        self.db.commit()
        self.assertFalse(service.release_for_order(self.order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (10, 0))
        self.assertEqual(self.stock(self.b), (10, 0))

    def test_consume_sells_the_units_without_changing_availability(self):
        self.assertTrue(ReservationService(self.db).consume_for_order(self.order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (7, 0))  # available 7 before and after
        self.assertEqual(self.stock(self.b), (8, 0))
        self.assertEqual(self.state(), OrderInventoryState.CONSUMED)

    def test_a_second_consume_does_nothing(self):
        service = ReservationService(self.db)
        self.assertTrue(service.consume_for_order(self.order))
        self.db.commit()
        self.assertFalse(service.consume_for_order(self.order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (7, 0))

    def test_release_after_consume_is_a_no_op(self):
        service = ReservationService(self.db)
        service.consume_for_order(self.order)
        self.db.commit()
        self.assertFalse(service.release_for_order(self.order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (7, 0))
        self.assertEqual(self.state(), OrderInventoryState.CONSUMED)

    def test_consume_after_release_is_a_no_op(self):
        service = ReservationService(self.db)
        service.release_for_order(self.order)
        self.db.commit()
        self.assertFalse(service.consume_for_order(self.order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (10, 0))
        self.assertEqual(self.state(), OrderInventoryState.RELEASED)

    def test_concurrent_releases_of_one_order_release_exactly_once(self):
        order_id = self.order.id

        def job():
            with new_session() as s:
                order = s.get(type(self.order), order_id)
                done = ReservationService(s).release_for_order(order)
                s.commit()
                return done

        results = run_concurrently([job for _ in range(8)])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(sum(1 for _, done in results if done), 1)
        self.assertEqual(self.stock(self.a), (10, 0))
        self.assertEqual(self.stock(self.b), (10, 0))

    def test_a_release_racing_a_consume_has_exactly_one_winner(self):
        order_id = self.order.id

        def make(method):
            def job():
                with new_session() as s:
                    order = s.get(type(self.order), order_id)
                    done = getattr(ReservationService(s), method)(order)
                    s.commit()
                    return (method, done)

            return job

        results = run_concurrently([make("release_for_order"), make("consume_for_order")])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        winners = [value[0] for _, value in results if value[1]]
        self.assertEqual(len(winners), 1)
        expected = (10, 0) if winners[0] == "release_for_order" else (7, 0)
        self.assertEqual(self.stock(self.a), expected)

    def test_items_whose_product_was_deleted_are_skipped(self):
        self.db.query(Product).filter(Product.id == self.b.id).delete()  # cascades inventory, nulls order_items.product_id
        self.db.commit()
        self.db.expire_all()
        order = self.db.get(type(self.order), self.order.id)
        self.assertTrue(ReservationService(self.db).release_for_order(order))
        self.db.commit()
        self.assertEqual(self.stock(self.a), (10, 0))

    def test_unbalanced_books_abort_and_leave_the_order_reserved(self):
        with new_session() as s:  # someone corrupted the numbers
            s.query(Inventory).filter(Inventory.product_id == self.b.id).update({Inventory.reserved_quantity: 0})
            s.commit()
        order = self.db.get(type(self.order), self.order.id)
        with self.assertRaises(ReservationInvariantError):
            ReservationService(self.db).release_for_order(order)
        self.db.rollback()  # what the calling transaction does on any exception
        self.assertEqual(self.state(), OrderInventoryState.RESERVED)
        self.assertEqual(self.stock(self.a), (10, 3))  # the successful half was undone too


if __name__ == "__main__":
    unittest.main()