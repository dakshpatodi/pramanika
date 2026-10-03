"""
Unit tests for the pure cart logic (pricing + stock rules). No database,
no network, no extra dependencies - standard-library unittest only.

Run from the backend folder:

    python -m unittest tests.test_cart_pricing -v
"""

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from app.core.money import to_decimal, to_money
from app.services.cart_rules import available_stock, line_issue
from app.services.pricing import PricingConfig, calculate_discount, calculate_totals

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
D = Decimal


class DiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


@dataclass
class FakeCoupon:
    discount_type: object = DiscountType.PERCENTAGE
    discount_value: object = D("10")
    minimum_order_amount: Optional[object] = None
    maximum_discount_amount: Optional[object] = None
    usage_limit: Optional[int] = None
    used_count: int = 0
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True


@dataclass
class FakeInventory:
    quantity: int
    reserved_quantity: int = 0


CONFIG = PricingConfig(gst_rate=D("0.05"), free_delivery_threshold=D("500.00"), delivery_charge=D("49.00"))


def price(lines, coupon=None, config=CONFIG):
    return calculate_totals(lines, coupon, NOW, config)


class MoneyTests(unittest.TestCase):
    def test_float_is_converted_without_noise(self):
        self.assertEqual(to_decimal(0.05), D("0.05"))

    def test_half_rounds_up(self):
        self.assertEqual(to_money("0.125"), D("0.13"))
        self.assertEqual(to_money("2.675"), D("2.68"))


class TotalsTests(unittest.TestCase):
    def test_empty_cart_is_all_zero_with_no_delivery(self):
        result = price([])
        t = result.totals
        self.assertEqual((t.subtotal, t.discount, t.gst, t.delivery_charge, t.total),
                         (D("0.00"),) * 5)
        self.assertEqual(t.amount_for_free_delivery, D("0.00"))
        self.assertIsNone(result.coupon_problem)

    def test_no_coupon_full_breakdown(self):
        # 2 x 100 + 1 x 50 = 250 ; GST 5% = 12.50 ; below 500 -> delivery 49
        t = price([(D("100.00"), 2), (D("50.00"), 1)]).totals
        self.assertEqual(t.subtotal, D("250.00"))
        self.assertEqual(t.discount, D("0.00"))
        self.assertEqual(t.taxable_amount, D("250.00"))
        self.assertEqual(t.gst, D("12.50"))
        self.assertEqual(t.delivery_charge, D("49.00"))
        self.assertEqual(t.amount_for_free_delivery, D("250.00"))
        self.assertEqual(t.total, D("311.50"))

    def test_float_prices_are_handled(self):
        t = price([(199.99, 3)]).totals
        self.assertEqual(t.subtotal, D("599.97"))

    def test_gst_rounds_half_up(self):
        cfg = PricingConfig(D("0.05"), D("0.00"), D("0.00"))
        # 0.50 * 5% = 0.025 -> 0.03
        self.assertEqual(price([(D("0.50"), 1)], config=cfg).totals.gst, D("0.03"))

    def test_free_delivery_exactly_at_threshold(self):
        t = price([(D("250.00"), 2)]).totals
        self.assertEqual(t.subtotal, D("500.00"))
        self.assertEqual(t.delivery_charge, D("0.00"))
        self.assertEqual(t.amount_for_free_delivery, D("0.00"))

    def test_just_below_threshold_pays_delivery(self):
        t = price([(D("499.99"), 1)]).totals
        self.assertEqual(t.delivery_charge, D("49.00"))
        self.assertEqual(t.amount_for_free_delivery, D("0.01"))

    def test_free_delivery_is_judged_after_discount(self):
        # subtotal 520 qualifies on its own, but 10% off -> taxable 468 < 500
        coupon = FakeCoupon(discount_value=D("10"))
        t = price([(D("520.00"), 1)], coupon).totals
        self.assertEqual(t.discount, D("52.00"))
        self.assertEqual(t.taxable_amount, D("468.00"))
        self.assertEqual(t.delivery_charge, D("49.00"))

    def test_gst_is_on_post_discount_amount_and_delivery_untaxed(self):
        coupon = FakeCoupon(discount_type=DiscountType.FIXED_AMOUNT, discount_value=D("100"))
        t = price([(D("400.00"), 1)], coupon).totals
        # taxable 300 ; GST 15 ; delivery 49 (not taxed) ; total 364
        self.assertEqual(t.taxable_amount, D("300.00"))
        self.assertEqual(t.gst, D("15.00"))
        self.assertEqual(t.delivery_charge, D("49.00"))
        self.assertEqual(t.total, D("364.00"))

    def test_total_identity_holds(self):
        t = price([(D("123.45"), 3), (D("67.89"), 2)], FakeCoupon(discount_value=D("15"))).totals
        self.assertEqual(t.total, to_money(t.taxable_amount + t.gst + t.delivery_charge))
        self.assertEqual(t.taxable_amount, to_money(t.subtotal - t.discount))


class DiscountTests(unittest.TestCase):
    def test_percentage(self):
        self.assertEqual(calculate_discount(D("200.00"), FakeCoupon(discount_value=D("10"))), D("20.00"))

    def test_percentage_capped_by_maximum(self):
        c = FakeCoupon(discount_value=D("50"), maximum_discount_amount=D("75"))
        self.assertEqual(calculate_discount(D("1000.00"), c), D("75.00"))

    def test_fixed_amount(self):
        c = FakeCoupon(discount_type=DiscountType.FIXED_AMOUNT, discount_value=D("60"))
        self.assertEqual(calculate_discount(D("400.00"), c), D("60.00"))

    def test_fixed_amount_never_exceeds_subtotal(self):
        c = FakeCoupon(discount_type=DiscountType.FIXED_AMOUNT, discount_value=D("500"))
        t = price([(D("120.00"), 1)], c).totals
        self.assertEqual(t.discount, D("120.00"))
        self.assertEqual(t.taxable_amount, D("0.00"))
        self.assertEqual(t.gst, D("0.00"))
        self.assertGreaterEqual(t.total, D("0.00"))

    def test_plain_string_discount_type_works(self):
        c = FakeCoupon(discount_type="percentage", discount_value=D("10"))
        self.assertEqual(calculate_discount(D("100.00"), c), D("10.00"))

    def test_unknown_type_gives_zero(self):
        c = FakeCoupon(discount_type="mystery")
        self.assertEqual(calculate_discount(D("100.00"), c), D("0.00"))


class CouponValidityTests(unittest.TestCase):
    LINES = [(D("300.00"), 1)]

    def assertRejected(self, coupon, fragment):
        result = price(self.LINES, coupon)
        self.assertEqual(result.totals.discount, D("0.00"))
        self.assertIsNotNone(result.coupon_problem)
        self.assertIn(fragment, result.coupon_problem)

    def test_valid_coupon_has_no_problem(self):
        result = price(self.LINES, FakeCoupon())
        self.assertIsNone(result.coupon_problem)
        self.assertEqual(result.totals.discount, D("30.00"))

    def test_inactive(self):
        self.assertRejected(FakeCoupon(is_active=False), "not active")

    def test_not_started(self):
        self.assertRejected(FakeCoupon(starts_at=NOW + timedelta(days=1)), "not valid yet")

    def test_expired(self):
        self.assertRejected(FakeCoupon(expires_at=NOW - timedelta(seconds=1)), "expired")

    def test_expires_at_exact_instant_is_expired(self):
        self.assertRejected(FakeCoupon(expires_at=NOW), "expired")

    def test_usage_limit_reached(self):
        self.assertRejected(FakeCoupon(usage_limit=5, used_count=5), "usage limit")

    def test_usage_limit_not_reached(self):
        self.assertIsNone(price(self.LINES, FakeCoupon(usage_limit=5, used_count=4)).coupon_problem)

    def test_minimum_order_not_met(self):
        self.assertRejected(FakeCoupon(minimum_order_amount=D("500")), "minimum order of Rs.500.00")

    def test_minimum_order_uses_pre_discount_subtotal(self):
        # subtotal 300 meets a 300 minimum even though the 10% discount
        # takes the taxable amount to 270.
        result = price(self.LINES, FakeCoupon(minimum_order_amount=D("300")))
        self.assertIsNone(result.coupon_problem)
        self.assertEqual(result.totals.taxable_amount, D("270.00"))

    def test_naive_datetimes_are_treated_as_utc(self):
        naive_past = (NOW - timedelta(days=1)).replace(tzinfo=None)
        self.assertRejected(FakeCoupon(expires_at=naive_past), "expired")

    def test_rejected_coupon_still_prices_the_cart(self):
        result = price(self.LINES, FakeCoupon(is_active=False))
        self.assertEqual(result.totals.subtotal, D("300.00"))
        self.assertEqual(result.totals.total, D("364.00"))  # 300 + 15 GST + 49 delivery


class ConfigTests(unittest.TestCase):
    def test_rejects_gst_rate_over_one(self):
        with self.assertRaises(ValueError):
            PricingConfig(D("5"), D("500"), D("49"))

    def test_rejects_negative_values(self):
        with self.assertRaises(ValueError):
            PricingConfig(D("-0.1"), D("500"), D("49"))
        with self.assertRaises(ValueError):
            PricingConfig(D("0.05"), D("-1"), D("49"))
        with self.assertRaises(ValueError):
            PricingConfig(D("0.05"), D("500"), D("-1"))

    def test_from_settings_converts_floats_exactly(self):
        class S:
            GST_RATE = 0.05
            FREE_DELIVERY_THRESHOLD = 500.0
            DELIVERY_CHARGE = 49.0

        cfg = PricingConfig.from_settings(S)
        self.assertEqual(cfg.gst_rate, D("0.05"))
        self.assertEqual(cfg.free_delivery_threshold, D("500.00"))
        self.assertEqual(cfg.delivery_charge, D("49.00"))

    def test_zero_gst_is_allowed(self):
        cfg = PricingConfig(D("0"), D("500"), D("49"))
        self.assertEqual(price([(D("100.00"), 1)], config=cfg).totals.gst, D("0.00"))


class StockRuleTests(unittest.TestCase):
    def test_available_is_quantity_minus_reserved(self):
        self.assertEqual(available_stock(FakeInventory(quantity=10, reserved_quantity=3)), 7)

    def test_missing_inventory_is_zero(self):
        self.assertEqual(available_stock(None), 0)

    def test_never_negative(self):
        self.assertEqual(available_stock(FakeInventory(quantity=2, reserved_quantity=5)), 0)

    def test_line_ok(self):
        self.assertIsNone(line_issue(True, 3, 8))
        self.assertIsNone(line_issue(True, 8, 8))

    def test_line_exceeds_stock(self):
        self.assertEqual(line_issue(True, 9, 8), "Only 8 units available - please reduce the quantity.")
        self.assertEqual(line_issue(True, 2, 1), "Only 1 unit available - please reduce the quantity.")

    def test_line_out_of_stock(self):
        self.assertEqual(line_issue(True, 1, 0), "This product is currently out of stock.")

    def test_line_inactive_takes_precedence(self):
        self.assertEqual(line_issue(False, 1, 0), "This product is no longer available.")


if __name__ == "__main__":
    unittest.main()