"""Phase 7 / Milestone 3: which orders may start a payment (pure rule)."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models import OrderCancellationReason as Reason
from app.models import OrderInventoryState as Inv
from app.models import OrderPaymentStatus as Pay
from app.models import OrderStatus as Status
from app.services.payment_rules import PaymentBlock as B
from app.services.payment_rules import CaptureDisposition, capture_disposition, payment_block

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def order(**overrides):
    values = dict(
        status=Status.PENDING, payment_status=Pay.PENDING, inventory_state=Inv.RESERVED,
        cancellation_reason=None, expires_at=NOW + timedelta(minutes=10), total_amount=Decimal("406.21"),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class PaymentBlockTests(unittest.TestCase):
    def test_a_fresh_pending_order_can_be_paid(self):
        self.assertIsNone(payment_block(order(), NOW))

    def test_an_order_with_no_deadline_can_be_paid(self):
        self.assertIsNone(payment_block(order(expires_at=None), NOW))

    def test_a_paid_order(self):
        for status in (Status.PENDING, Status.CONFIRMED, Status.SHIPPED):
            with self.subTest(status=status):
                self.assertIs(payment_block(order(status=status, payment_status=Pay.PAID), NOW), B.ALREADY_PAID)

    def test_a_customer_cancelled_order(self):
        o = order(status=Status.CANCELLED, inventory_state=Inv.RELEASED, cancellation_reason=Reason.CUSTOMER)
        self.assertIs(payment_block(o, NOW), B.CANCELLED)

    def test_an_expired_order_is_reported_as_expired_not_cancelled(self):
        o = order(status=Status.CANCELLED, inventory_state=Inv.RELEASED, cancellation_reason=Reason.EXPIRED)
        self.assertIs(payment_block(o, NOW), B.EXPIRED)

    def test_a_cancelled_order_says_cancelled_even_though_its_stock_is_gone(self):
        o = order(status=Status.CANCELLED, inventory_state=Inv.RELEASED, cancellation_reason=Reason.CUSTOMER)
        self.assertIsNot(payment_block(o, NOW), B.STOCK_NOT_HELD)

    def test_an_order_past_its_deadline_is_expired_before_the_job_has_run(self):
        self.assertIs(payment_block(order(expires_at=NOW - timedelta(seconds=1)), NOW), B.EXPIRED)

    def test_the_deadline_itself_is_already_expired(self):
        self.assertIs(payment_block(order(expires_at=NOW), NOW), B.EXPIRED)

    def test_one_second_before_the_deadline_is_still_payable(self):
        self.assertIsNone(payment_block(order(expires_at=NOW + timedelta(seconds=1)), NOW))

    def test_other_order_states_are_not_payable(self):
        for status in (Status.CONFIRMED, Status.PROCESSING, Status.SHIPPED, Status.DELIVERED, Status.REFUNDED):
            with self.subTest(status=status):
                self.assertIs(payment_block(order(status=status), NOW), B.NOT_PAYABLE)

    def test_a_failed_or_refunded_order_payment_status_is_not_payable(self):
        for pay in (Pay.FAILED, Pay.REFUNDED):
            with self.subTest(payment_status=pay):
                self.assertIs(payment_block(order(payment_status=pay), NOW), B.NOT_PAYABLE)

    def test_stock_that_is_no_longer_held(self):
        for inv in (Inv.RELEASED, Inv.CONSUMED):
            with self.subTest(inventory_state=inv):
                self.assertIs(payment_block(order(inventory_state=inv), NOW), B.STOCK_NOT_HELD)

    def test_nothing_to_pay(self):
        for total in (Decimal("0.00"), Decimal("-1.00"), None):
            with self.subTest(total=total):
                self.assertIs(payment_block(order(total_amount=total), NOW), B.NOTHING_TO_PAY)


class CaptureDispositionTests(unittest.TestCase):
    def test_a_live_pending_order_is_paid(self):
        self.assertIs(capture_disposition(order()), CaptureDisposition.PAYS_ORDER)

    def test_an_order_past_its_deadline_but_not_yet_expired_by_the_job_is_still_paid(self):
        self.assertIs(capture_disposition(order(expires_at=NOW - timedelta(hours=1))), CaptureDisposition.PAYS_ORDER)

    def test_everything_else_is_flagged_for_refund(self):
        closed = {
            "cancelled by the customer": dict(status=Status.CANCELLED, inventory_state=Inv.RELEASED, cancellation_reason=Reason.CUSTOMER),
            "expired": dict(status=Status.CANCELLED, inventory_state=Inv.RELEASED, cancellation_reason=Reason.EXPIRED),
            "stock released but still pending": dict(inventory_state=Inv.RELEASED),
            "stock already consumed": dict(inventory_state=Inv.CONSUMED),
            "already paid": dict(status=Status.CONFIRMED, payment_status=Pay.PAID, inventory_state=Inv.CONSUMED),
            "payment status failed": dict(payment_status=Pay.FAILED),
            "payment refunded": dict(payment_status=Pay.REFUNDED),
            "already confirmed": dict(status=Status.CONFIRMED),
            "shipped": dict(status=Status.SHIPPED),
        }
        for name, overrides in closed.items():
            with self.subTest(case=name):
                self.assertIs(capture_disposition(order(**overrides)), CaptureDisposition.REFUND_REQUIRED)


if __name__ == "__main__":
    unittest.main()
