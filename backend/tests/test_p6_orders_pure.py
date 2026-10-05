"""Pure (no database) tests for Phase 6 order rules."""

import unittest

from app.models import OrderPaymentStatus as P
from app.models import OrderStatus as S
from app.services.order_rules import can_cancel, format_order_number


class OrderNumberTests(unittest.TestCase):
    def test_pads_to_six_digits(self):
        self.assertEqual(format_order_number(2026, 123), "PRM-2026-000123")
        self.assertEqual(format_order_number(2026, 1), "PRM-2026-000001")

    def test_grows_instead_of_truncating(self):
        self.assertEqual(format_order_number(2027, 1234567), "PRM-2027-1234567")


class CancellationRuleTests(unittest.TestCase):
    def test_only_unpaid_pending_orders_can_be_cancelled(self):
        self.assertTrue(can_cancel(S.PENDING, P.PENDING))

    def test_nothing_else_can(self):
        for status in S:
            for payment in P:
                if (status, payment) == (S.PENDING, P.PENDING):
                    continue
                self.assertFalse(can_cancel(status, payment), (status, payment))


if __name__ == "__main__":
    unittest.main()