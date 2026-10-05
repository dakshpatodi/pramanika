"""
Coupon `used_count` (PostgreSQL integration tests).

See tests/pg_support.py for how to run them.
"""

import unittest

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import InvalidCouponError
from app.models import Coupon
from app.services.coupon_usage import CouponUsageService
from tests.pg_support import PostgresTestCase, new_session, run_concurrently


class ConsumeTests(PostgresTestCase):
    def consume(self, coupon):
        CouponUsageService(self.db).consume(coupon.id)
        self.db.commit()

    def test_a_use_increments_used_count_by_one(self):
        c = self.make_coupon(usage_limit=5)
        self.consume(c)
        self.assertEqual(self.used_count(c), 1)

    def test_unlimited_coupons_keep_counting(self):
        c = self.make_coupon(usage_limit=None, used_count=1000)
        self.consume(c)
        self.assertEqual(self.used_count(c), 1001)

    def test_the_last_use_is_allowed_and_the_next_is_refused(self):
        c = self.make_coupon(usage_limit=2, used_count=1)
        self.consume(c)
        self.assertEqual(self.used_count(c), 2)
        with self.assertRaises(InvalidCouponError):
            CouponUsageService(self.db).consume(c.id)
        self.db.rollback()
        self.assertEqual(self.used_count(c), 2)

    def test_an_inactive_coupon_is_refused_and_not_counted(self):
        c = self.make_coupon(usage_limit=5, is_active=False)
        with self.assertRaises(InvalidCouponError):
            CouponUsageService(self.db).consume(c.id)
        self.db.rollback()
        self.assertEqual(self.used_count(c), 0)

    def test_an_unknown_coupon_is_refused(self):
        import uuid

        with self.assertRaises(InvalidCouponError):
            CouponUsageService(self.db).consume(uuid.uuid4())
        self.db.rollback()

    def test_a_rolled_back_transaction_does_not_consume_a_use(self):
        c = self.make_coupon(usage_limit=1)
        CouponUsageService(self.db).consume(c.id)
        self.db.rollback()  # e.g. a later checkout step failed
        self.assertEqual(self.used_count(c), 0)
        self.consume(c)  # the use is still available
        self.assertEqual(self.used_count(c), 1)

    def test_the_database_refuses_used_count_over_the_limit(self):
        c = self.make_coupon(usage_limit=1, used_count=1)
        with self.assertRaises(IntegrityError):
            self.db.query(Coupon).filter(Coupon.id == c.id).update({Coupon.used_count: 2})
            self.db.commit()
        self.db.rollback()


class RestoreTests(PostgresTestCase):
    def test_restore_gives_one_use_back(self):
        c = self.make_coupon(usage_limit=5, used_count=3)
        self.assertTrue(CouponUsageService(self.db).restore(c.id))
        self.db.commit()
        self.assertEqual(self.used_count(c), 2)

    def test_restore_never_goes_below_zero(self):
        c = self.make_coupon(usage_limit=5, used_count=0)
        self.assertFalse(CouponUsageService(self.db).restore(c.id))
        self.db.commit()
        self.assertEqual(self.used_count(c), 0)


class ConcurrentConsumeTests(PostgresTestCase):
    def test_simultaneous_checkouts_cannot_exceed_the_usage_limit(self):
        c = self.make_coupon(usage_limit=3)
        coupon_id = c.id  # read on the test thread

        def job():
            with new_session() as s:
                try:
                    CouponUsageService(s).consume(coupon_id)
                    s.commit()
                    return True
                except InvalidCouponError:
                    s.rollback()
                    return False

        results = run_concurrently([job for _ in range(12)])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(sum(1 for _, ok in results if ok), 3)
        self.assertEqual(self.used_count(c), 3)

    def test_two_checkouts_racing_for_the_final_use_have_one_winner(self):
        c = self.make_coupon(usage_limit=1)
        coupon_id = c.id

        def job():
            with new_session() as s:
                try:
                    CouponUsageService(s).consume(coupon_id)
                    s.commit()
                    return True
                except InvalidCouponError:
                    s.rollback()
                    return False

        results = run_concurrently([job, job])
        self.assertEqual(sorted(r[1] for r in results), [False, True])
        self.assertEqual(self.used_count(c), 1)


if __name__ == "__main__":
    unittest.main()