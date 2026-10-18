"""
Phase 7 / Milestone 7: PaymentWebhookService on real PostgreSQL (no network).

Groups:
  AuthenticationTests     only a correctly signed, readable delivery changes anything
  ScenarioATests          the browser never comes back; the webhook pays the order
  ScenarioBTests          browser and webhook both report the same payment
  ScenarioCTests          money after the order closed: recorded, flagged, order untouched
  ScenarioDTests          the same event delivered again (and at the same time)
  ScenarioETests          failures arrive late, early or out of order
  OtherEventTests         authorized, unknown, mismatching and unhandled events
  AtomicityTests          a failure half-way undoes the claim too, so Razorpay's retry works
  ConcurrencyTests        real threads, real row locks
  PrivacyTests            nothing secret or personal reaches the log or the table
"""

import itertools
import json
import logging
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app.core.exceptions import (
    LatePaymentError,
    OrderNotCancellableError,
    PaymentsNotConfiguredError,
    WebhookPayloadError,
    WebhookSignatureError,
    WebhookTooLargeError,
)
from app.models import (
    Order,
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus as S,
    PaymentWebhookEvent,
)
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.payment_webhook_service import MAX_BODY_BYTES, PaymentWebhookService, WebhookOutcome as O, event_key
from app.services.razorpay_signature import webhook_signature
from tests.payment_fakes import FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session, run_concurrently

SECRET = "whsec-test-DO-NOT-LEAK-222"
RZ = "order_WHK001"
PAY = "pay_WHK001"
EMAIL = "private.customer@example.com"
_ids = itertools.count(1)


def make_body(event="payment.captured", *, pid=PAY, rz=RZ, amount=40621, currency="INR", **extra) -> bytes:
    entity = {"id": pid, "order_id": rz, "amount": amount, "currency": currency, "email": EMAIL, "contact": "+919999999999"}
    entity.update(extra)
    return json.dumps({"entity": "event", "event": event, "payload": {"payment": {"entity": entity}}}).encode()


class WebhookCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.coupon = self.make_coupon(usage_limit=10, used_count=1)
        self.order = self.make_order(self.user, [(self.product, 1)], coupon=self.coupon)  # stock (5, 1)
        self.payment = self.make_payment(self.order, gateway_order_id=RZ)
        self.user_id, self.order_id = self.user.id, self.order.id
        self.rz, self.pay_id = RZ, PAY

    def fresh_round(self, n):
        """A new order + payment in the same database, stock back to (5, 1) after the new order reserves its unit, and the
        coupon back to 1 use - for loops that repeat a race. (Not setUp again: that
        truncates the tables, which waits forever on this test's own open session.)"""
        from app.models import Coupon, Inventory

        self.db.query(Inventory).filter(Inventory.product_id == self.product.id).update(
            {Inventory.quantity: 5, Inventory.reserved_quantity: 0})  # make_order below reserves 1 again
        self.db.query(Coupon).filter(Coupon.id == self.coupon.id).update({Coupon.used_count: 1})
        self.db.commit()
        self.order = self.make_order(self.user, [(self.product, 1)], coupon=self.coupon)
        self.rz, self.pay_id = f"order_WHKR{n}", f"pay_WHKR{n}"
        self.payment = self.make_payment(self.order, gateway_order_id=self.rz)
        self.order_id = self.order.id

    # --- act ---

    def deliver(self, event="payment.captured", *, event_id=None, raw=None, signature=None, secret=SECRET, **fields):
        if raw is None:
            fields.setdefault("rz", self.rz)
            fields.setdefault("pid", self.pay_id)
            raw = make_body(event, **fields)
        signature = webhook_signature(SECRET, raw) if signature is None else signature
        event_id = f"evt_{next(_ids)}" if event_id is None else event_id
        with new_session() as session:
            return PaymentWebhookService(session, secret).handle(raw, signature, event_id)

    # --- read ---

    def order_row(self, order=None) -> Order:
        with new_session() as s:
            row = s.get(Order, (order or self.order).id)
            s.expunge(row)
            return row

    def payment_row(self, payment=None) -> Payment:
        with new_session() as s:
            row = s.get(Payment, (payment or self.payment).id)
            s.expunge(row)
            return row

    def events(self):
        with new_session() as s:
            return [(e.event_id, e.event_type, e.gateway_order_id, e.gateway_payment_id, e.outcome)
                    for e in s.query(PaymentWebhookEvent).order_by(PaymentWebhookEvent.received_at, PaymentWebhookEvent.event_id).all()]

    def snapshot(self):
        o, p = self.order_row(), self.payment_row()
        return (
            (o.status, o.payment_status, o.inventory_state, o.cancellation_reason),
            (p.status, p.gateway_payment_id, p.gateway_signature, p.paid_at, p.refund_required, p.failure_reason),
            self.stock(self.product), self.used_count(self.coupon),
        )

    def assert_paid(self):
        o, p = self.order_row(), self.payment_row()
        self.assertEqual((o.status, o.payment_status, o.inventory_state),
                         (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID, OrderInventoryState.CONSUMED))
        self.assertEqual((p.status, p.gateway_payment_id, p.refund_required), (S.CAPTURED, self.pay_id, False))
        self.assertIsNotNone(p.paid_at)
        self.assertEqual(self.stock(self.product), (4, 0))      # sold, nothing left reserved
        self.assertEqual(self.used_count(self.coupon), 1)       # a paid order keeps its coupon use

    def close_order(self, reason=OrderCancellationReason.CUSTOMER, close_payment=True):
        """What cancel (or the expiry job) leaves behind."""
        with new_session() as s:
            if reason == OrderCancellationReason.CUSTOMER:
                OrderService(s).cancel_order(self.user_id, self.order_id)
            else:
                from app.models import Inventory

                s.query(Order).filter(Order.id == self.order_id).update(
                    {Order.status: OrderStatus.CANCELLED, Order.inventory_state: OrderInventoryState.RELEASED,
                     Order.cancellation_reason: reason, Order.cancelled_at: datetime.now(timezone.utc)})
                s.query(Inventory).filter(Inventory.product_id == self.product.id).update(
                    {Inventory.reserved_quantity: Inventory.reserved_quantity - 1})
                if close_payment:
                    s.query(Payment).filter(Payment.id == self.payment.id).update(
                        {Payment.status: S.EXPIRED, Payment.failure_reason: "expired"})
                s.commit()


class AuthenticationTests(WebhookCase):
    def assert_nothing_happened(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events(), [])

    def test_a_wrong_signature_changes_nothing(self):
        before = self.snapshot()
        with self.assertRaises(WebhookSignatureError):
            self.deliver(signature="0" * 64)
        self.assert_nothing_happened(before)

    def test_a_signature_made_with_another_secret_changes_nothing(self):
        raw = make_body()
        before = self.snapshot()
        with self.assertRaises(WebhookSignatureError):
            self.deliver(raw=raw, signature=webhook_signature("another-secret", raw))
        self.assert_nothing_happened(before)

    def test_a_missing_signature_changes_nothing(self):
        before = self.snapshot()
        for missing in (None, ""):
            with new_session() as s, self.assertRaises(WebhookSignatureError):
                PaymentWebhookService(s, SECRET).handle(make_body(), missing, "evt_x")
        self.assert_nothing_happened(before)

    def test_a_body_edited_after_signing_changes_nothing(self):
        raw = make_body()
        signature = webhook_signature(SECRET, raw)
        before = self.snapshot()
        with self.assertRaises(WebhookSignatureError):
            self.deliver(raw=raw.replace(b"40621", b"100"), signature=signature)
        self.assert_nothing_happened(before)

    def test_the_server_without_a_webhook_secret_refuses_everything(self):
        raw = make_body()
        before = self.snapshot()
        for secret in ("", None):
            with new_session() as s, self.assertRaises(PaymentsNotConfiguredError):
                PaymentWebhookService(s, secret).handle(raw, webhook_signature(SECRET, raw), "evt")
        self.assert_nothing_happened(before)

    def test_an_empty_secret_cannot_be_used_to_forge_a_signature(self):
        # an HMAC with an empty key is computable by anyone: it must never be accepted
        import hashlib
        import hmac

        raw = make_body()
        forged = hmac.new(b"", raw, hashlib.sha256).hexdigest()
        with new_session() as s, self.assertRaises(PaymentsNotConfiguredError):
            PaymentWebhookService(s, "").handle(raw, forged, "evt")

    def test_a_huge_body_is_refused_before_anything_else(self):
        with new_session() as s, self.assertRaises(WebhookTooLargeError):
            PaymentWebhookService(s, SECRET).handle(b"x" * (MAX_BODY_BYTES + 1), "sig", "evt")

    def test_a_signed_but_unreadable_body_changes_nothing(self):
        before = self.snapshot()
        for raw in (b"not json", b"[]", b'{"event": 3}'):
            with self.subTest(raw=raw), self.assertRaises(WebhookPayloadError):
                self.deliver(raw=raw)
        self.assert_nothing_happened(before)

    def test_the_signature_is_checked_before_the_body_is_read(self):
        with mock.patch("app.services.payment_webhook_service.parse_webhook") as parse:
            with self.assertRaises(WebhookSignatureError):
                self.deliver(raw=b"garbage", signature="bad")
        parse.assert_not_called()


class ScenarioATests(WebhookCase):
    """The customer paid, then closed the tab. Only the webhook knows."""

    def test_payment_captured_pays_the_order(self):
        self.assertEqual(self.deliver("payment.captured"), O.PAID)
        self.assert_paid()
        self.assertIsNone(self.payment_row().gateway_signature)  # the checkout signature was never seen

    def test_order_paid_pays_the_order_too(self):
        raw = json.dumps({"event": "order.paid", "payload": {
            "order": {"entity": {"id": RZ, "amount_paid": 40621}},
            "payment": {"entity": {"id": PAY, "order_id": RZ, "amount": 40621, "currency": "INR"}}}}).encode()
        self.assertEqual(self.deliver(raw=raw), O.PAID)
        self.assert_paid()

    def test_the_event_is_recorded_with_what_was_done(self):
        self.deliver("payment.captured", event_id="evt_A1")
        self.assertEqual(self.events(), [("evt_A1", "payment.captured", RZ, PAY, "paid")])

    def test_every_line_of_the_order_is_consumed(self):
        other = self.make_product(price="100.00", stock=10)
        order = self.make_order(self.user, [(self.product, 2), (other, 3)])
        self.make_payment(order, gateway_order_id="order_MULTI", amount=order.total_amount)
        amount = int(order.total_amount * 100)
        before_first, before_other = self.stock(self.product), self.stock(other)
        self.deliver(rz="order_MULTI", pid="pay_MULTI", amount=amount)
        self.assertEqual(self.stock(self.product), (before_first[0] - 2, before_first[1] - 2))
        self.assertEqual(self.stock(other), (before_other[0] - 3, before_other[1] - 3))

    def test_an_order_past_its_deadline_that_expiry_has_not_reached_yet_is_still_paid(self):
        """The customer paid inside the window and the stock is still held."""
        self.db.query(Order).filter(Order.id == self.order_id).update({Order.expires_at: datetime.now(timezone.utc) - timedelta(minutes=5)})
        self.db.commit()
        self.assertEqual(self.deliver(), O.PAID)
        self.assert_paid()

    def test_an_authorized_payment_that_is_then_captured_pays(self):
        self.assertEqual(self.deliver("payment.authorized"), O.AUTHORIZED)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(self.deliver("payment.captured"), O.PAID)
        self.assert_paid()


class ScenarioBTests(WebhookCase):
    """The browser and Razorpay both report the same payment: it is paid once."""

    def verify_in_browser(self):
        gateway = FakeGateway()
        gateway.register_payment(PAY, order_id=RZ, amount_paise=40621)
        with new_session() as s:
            result = PaymentService(s, gateway).verify_payment(
                self.user_id, self.order_id, razorpay_order_id=RZ, razorpay_payment_id=PAY, razorpay_signature=sign(RZ, PAY))
        return result, gateway

    def test_browser_first_then_webhook_changes_nothing_the_second_time(self):
        self.verify_in_browser()
        after_browser = self.snapshot()
        self.assertEqual(self.deliver("payment.captured"), O.ALREADY_RECORDED)
        self.assertEqual(self.snapshot(), after_browser)
        self.assertEqual(self.stock(self.product), (4, 0))  # consumed once, not twice
        self.assertEqual(self.payment_row().gateway_signature, sign(RZ, PAY))  # the browser's signature is kept

    def test_webhook_first_then_browser_is_answered_from_the_database(self):
        self.deliver("payment.captured")
        after_webhook = self.snapshot()
        result, gateway = self.verify_in_browser()
        self.assertEqual(result.outcome.value, "already_paid")
        self.assertEqual(gateway.fetches, [])  # Razorpay was not even asked
        self.assertEqual(self.snapshot(), after_webhook)

    def test_captured_and_order_paid_for_the_same_payment_pay_once(self):
        self.assertEqual(self.deliver("payment.captured"), O.PAID)
        order_paid = json.dumps({"event": "order.paid", "payload": {"payment": {"entity": {
            "id": PAY, "order_id": RZ, "amount": 40621, "currency": "INR"}}}}).encode()
        self.assertEqual(self.deliver(raw=order_paid), O.ALREADY_RECORDED)
        self.assert_paid()

    def test_a_second_payment_id_on_an_already_paid_razorpay_order_goes_to_manual_review(self):
        self.deliver("payment.captured")
        before = self.snapshot()
        self.assertEqual(self.deliver("payment.captured", pid="pay_SECOND", event_id="evt_second"), O.MANUAL_REVIEW)
        self.assertEqual(self.snapshot(), before)
        self.assertIn(("evt_second", "payment.captured", RZ, "pay_SECOND", "manual_review"), self.events())  # id kept for the refund


class ScenarioCTests(WebhookCase):
    """The order closed before the money arrived."""

    def assert_flagged_and_order_untouched(self, before_order, expected_stock):
        p = self.payment_row()
        self.assertEqual((p.status, p.refund_required, p.gateway_payment_id), (S.CAPTURED, True, PAY))
        self.assertIsNotNone(p.paid_at)
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status, o.inventory_state, o.cancellation_reason), before_order)
        self.assertEqual(self.stock(self.product), expected_stock)  # not sold, not re-reserved

    def test_after_the_customer_cancelled(self):
        self.close_order(OrderCancellationReason.CUSTOMER)
        before_order = (OrderStatus.CANCELLED, OrderPaymentStatus.PENDING, OrderInventoryState.RELEASED, OrderCancellationReason.CUSTOMER)
        used = self.used_count(self.coupon)
        self.assertEqual(self.deliver("payment.captured"), O.LATE_PAYMENT)
        self.assert_flagged_and_order_untouched(before_order, (5, 0))
        self.assertEqual(self.used_count(self.coupon), used)  # the coupon is not taken again

    def test_after_the_order_expired(self):
        self.close_order(OrderCancellationReason.EXPIRED)
        before_order = (OrderStatus.CANCELLED, OrderPaymentStatus.PENDING, OrderInventoryState.RELEASED, OrderCancellationReason.EXPIRED)
        self.assertEqual(self.deliver("payment.captured"), O.LATE_PAYMENT)
        self.assert_flagged_and_order_untouched(before_order, (5, 0))

    def test_when_the_payment_row_was_never_closed(self):
        self.close_order(OrderCancellationReason.EXPIRED, close_payment=False)
        self.assertEqual(self.deliver("payment.captured"), O.LATE_PAYMENT)
        self.assertEqual(self.payment_row().refund_required, True)

    def test_when_the_stock_was_already_given_back_but_the_order_looks_pending(self):
        self.db.query(Order).filter(Order.id == self.order_id).update({Order.inventory_state: OrderInventoryState.RELEASED})
        self.db.commit()
        self.assertEqual(self.deliver("payment.captured"), O.LATE_PAYMENT)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_the_late_payment_is_recorded_once_even_if_delivered_twice_or_verified_later(self):
        self.close_order(OrderCancellationReason.CUSTOMER)
        self.deliver("payment.captured", event_id="evt_late")
        self.assertEqual(self.deliver("payment.captured", event_id="evt_late"), O.DUPLICATE)
        self.assertEqual(self.deliver("payment.captured", event_id="evt_late_2"), O.ALREADY_RECORDED)
        gateway = FakeGateway()
        with new_session() as s, self.assertRaises(LatePaymentError):
            PaymentService(s, gateway).verify_payment(
                self.user_id, self.order_id, razorpay_order_id=RZ, razorpay_payment_id=PAY, razorpay_signature=sign(RZ, PAY))
        self.assertEqual(self.stock(self.product), (5, 0))

    def test_a_paid_order_cannot_be_cancelled_after_the_webhook_paid_it(self):
        self.deliver("payment.captured")
        with new_session() as s, self.assertRaises(OrderNotCancellableError):
            OrderService(s).cancel_order(self.user_id, self.order_id)
        self.assert_paid()


class ScenarioDTests(WebhookCase):
    def test_the_same_event_delivered_again_does_nothing(self):
        self.assertEqual(self.deliver("payment.captured", event_id="evt_same"), O.PAID)
        after = self.snapshot()
        for _ in range(3):
            self.assertEqual(self.deliver("payment.captured", event_id="evt_same"), O.DUPLICATE)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0][4], "paid")  # the first outcome is not overwritten

    def test_a_duplicate_is_not_processed_even_if_its_content_would_now_do_something(self):
        self.deliver("payment.failed", event_id="evt_x", status="failed")
        self.assertEqual(self.payment_row().status, S.FAILED)
        # the same id, now claiming a capture: the id was used, so it is ignored
        self.assertEqual(self.deliver("payment.captured", event_id="evt_x"), O.DUPLICATE)
        self.assertEqual(self.payment_row().status, S.FAILED)

    def test_an_event_without_an_id_header_still_deduplicates_on_the_body(self):
        raw = make_body()
        sig = webhook_signature(SECRET, raw)
        outcomes = []
        for _ in range(2):
            with new_session() as s:
                outcomes.append(PaymentWebhookService(s, SECRET).handle(raw, sig, None))
        self.assertEqual(outcomes, [O.PAID, O.DUPLICATE])
        self.assertTrue(self.events()[0][0].startswith("sha256:"))

    def test_an_unusable_id_header_falls_back_to_the_body_hash(self):
        raw = make_body()
        for header in (None, "", "   ", "x" * 101, "bad\nid"):
            self.assertTrue(event_key(header, raw).startswith("sha256:"), header)
        self.assertEqual(event_key("evt_ok", raw), "evt_ok")
        self.assertEqual(event_key("  evt_ok ", raw), "evt_ok")
        self.assertEqual(event_key("x" * 100, raw), "x" * 100)

    def test_two_different_events_for_one_payment_apply_in_order_and_pay_once(self):
        outcomes = [self.deliver("payment.authorized"), self.deliver("payment.captured"), self.deliver("payment.captured")]
        self.assertEqual(outcomes, [O.AUTHORIZED, O.PAID, O.ALREADY_RECORDED])
        self.assert_paid()


class ScenarioETests(WebhookCase):
    def test_a_failed_attempt_marks_the_payment_failed_and_leaves_the_order_alone(self):
        before_order = self.order_row()
        self.assertEqual(self.deliver("payment.failed", error_description="Card declined", status="failed"), O.FAILED)
        p = self.payment_row()
        self.assertEqual((p.status, p.failure_reason, p.gateway_payment_id, p.paid_at), (S.FAILED, "Card declined", PAY, None))
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status, o.inventory_state), (before_order.status, OrderPaymentStatus.PENDING, OrderInventoryState.RESERVED))
        self.assertEqual(self.stock(self.product), (5, 1))  # the stock is still held for a retry
        self.assertEqual(self.used_count(self.coupon), 1)

    def test_a_failure_without_a_reason_still_says_something(self):
        self.deliver("payment.failed")
        self.assertEqual(self.payment_row().failure_reason, "The payment failed.")

    def test_a_late_failure_never_unpays_a_captured_payment(self):
        self.deliver("payment.captured")
        after = self.snapshot()
        self.assertEqual(self.deliver("payment.failed", error_description="bank timeout"), O.IGNORED_STALE)
        self.assertEqual(self.snapshot(), after)
        self.assert_paid()

    def test_a_late_failure_never_unpays_a_payment_the_browser_confirmed(self):
        gateway = FakeGateway()
        gateway.register_payment(PAY, order_id=RZ, amount_paise=40621)
        with new_session() as s:
            PaymentService(s, gateway).verify_payment(self.user_id, self.order_id, razorpay_order_id=RZ,
                                                      razorpay_payment_id=PAY, razorpay_signature=sign(RZ, PAY))
        self.assertEqual(self.deliver("payment.failed"), O.IGNORED_STALE)
        self.assert_paid()

    def test_a_failure_does_not_undo_a_late_payment_either(self):
        self.close_order(OrderCancellationReason.CUSTOMER)
        self.deliver("payment.captured")
        self.assertEqual(self.deliver("payment.failed"), O.IGNORED_STALE)
        p = self.payment_row()
        self.assertEqual((p.status, p.refund_required), (S.CAPTURED, True))

    def test_a_payment_that_failed_and_is_then_retried_at_razorpay_can_still_pay_the_order(self):
        self.deliver("payment.failed", pid="pay_TRY1", status="failed")
        self.assertEqual(self.payment_row().status, S.FAILED)
        self.assertEqual(self.deliver("payment.captured", pid="pay_TRY2"), O.PAID)
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status), (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID))
        p = self.payment_row()
        self.assertEqual((p.status, p.gateway_payment_id, p.failure_reason), (S.CAPTURED, "pay_TRY2", None))

    def test_a_failure_of_another_attempt_does_not_fail_the_authorized_one(self):
        self.deliver("payment.authorized", pid="pay_GOOD")
        self.assertEqual(self.deliver("payment.failed", pid="pay_BAD"), O.IGNORED_STALE)
        p = self.payment_row()
        self.assertEqual((p.status, p.gateway_payment_id), (S.AUTHORIZED, "pay_GOOD"))

    def test_a_failure_for_the_attempt_we_track_does_fail_it(self):
        self.deliver("payment.authorized", pid="pay_GOOD")
        self.assertEqual(self.deliver("payment.failed", pid="pay_GOOD"), O.FAILED)
        self.assertEqual(self.payment_row().status, S.FAILED)

    def test_a_failure_after_the_order_was_cancelled_is_ignored(self):
        self.close_order(OrderCancellationReason.CUSTOMER)
        before = self.snapshot()
        self.assertEqual(self.deliver("payment.failed"), O.IGNORED_STALE)
        self.assertEqual(self.snapshot(), before)

    def test_the_same_failure_again_under_a_new_event_id_is_already_recorded(self):
        self.deliver("payment.failed", error_description="first")
        self.assertEqual(self.deliver("payment.failed", error_description="second"), O.ALREADY_RECORDED)
        self.assertEqual(self.payment_row().failure_reason, "first")

    def test_a_failure_arriving_after_a_retry_started_does_not_touch_the_new_attempt(self):
        """First Razorpay order failed; the customer retried (a second Payment row); the first one's failure is redelivered."""
        self.deliver("payment.failed", pid="pay_OLD", status="failed")
        gateway = FakeGateway()
        with new_session() as s:
            second = PaymentService(s, gateway).create_razorpay_order(self.user_id, self.order_id)
        new_rz = second.intent.razorpay_order_id
        self.deliver("payment.failed", event_id="evt_redelivered", pid="pay_OLD", status="failed")
        with new_session() as s:
            rows = {p.gateway_order_id: p.status for p in s.query(Payment).filter(Payment.order_id == self.order_id).all()}
        self.assertEqual(rows, {RZ: S.FAILED, new_rz: S.INITIATED})


class OtherEventTests(WebhookCase):
    def test_authorized_records_it_and_the_order_stays_unpaid(self):
        before_order = self.order_row()
        self.assertEqual(self.deliver("payment.authorized"), O.AUTHORIZED)
        p = self.payment_row()
        self.assertEqual((p.status, p.gateway_payment_id, p.paid_at), (S.AUTHORIZED, PAY, None))
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status), (before_order.status, OrderPaymentStatus.PENDING))
        self.assertEqual(self.stock(self.product), (5, 1))

    def test_a_late_authorized_event_after_capture_changes_nothing(self):
        self.deliver("payment.captured")
        before = self.snapshot()
        self.assertEqual(self.deliver("payment.authorized"), O.IGNORED_STALE)
        self.assertEqual(self.snapshot(), before)

    def test_the_same_authorization_again_is_already_recorded(self):
        self.deliver("payment.authorized")
        self.assertEqual(self.deliver("payment.authorized"), O.ALREADY_RECORDED)

    def test_an_authorization_for_a_different_attempt_is_not_a_repeat(self):
        self.deliver("payment.authorized", pid="pay_FIRST")
        self.assertEqual(self.deliver("payment.authorized", pid="pay_OTHER"), O.IGNORED_STALE)
        self.assertEqual(self.payment_row().gateway_payment_id, "pay_FIRST")

    def test_authorized_after_failed_or_expired_is_ignored(self):
        self.deliver("payment.failed")
        self.assertEqual(self.deliver("payment.authorized"), O.IGNORED_STALE)
        self.assertEqual(self.payment_row().status, S.FAILED)

    def test_a_payment_that_is_not_ours_is_acknowledged_and_changes_nothing(self):
        before = self.snapshot()
        self.assertEqual(self.deliver(rz="order_SOMEONEELSE", event_id="evt_foreign"), O.IGNORED_UNKNOWN)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events(), [("evt_foreign", "payment.captured", "order_SOMEONEELSE", PAY, "ignored_unknown")])

    def test_events_without_usable_ids_are_ignored(self):
        before = self.snapshot()
        for raw in (
            json.dumps({"event": "payment.captured", "payload": {}}).encode(),
            make_body(pid="bad id"),
            make_body(rz="bad id"),
        ):
            self.assertEqual(self.deliver(raw=raw), O.IGNORED_UNKNOWN)
        self.assertEqual(self.snapshot(), before)

    def test_a_different_amount_is_rejected_and_changes_nothing(self):
        before = self.snapshot()
        for amount in (1, 40620, 40622, 4062100, None):
            with self.subTest(amount=amount):
                self.assertEqual(self.deliver(amount=amount), O.REJECTED_MISMATCH)
        self.assertEqual(self.snapshot(), before)

    def test_a_different_currency_is_rejected(self):
        before = self.snapshot()
        self.assertEqual(self.deliver(currency="USD"), O.REJECTED_MISMATCH)
        self.assertEqual(self.snapshot(), before)

    def test_a_mismatch_also_blocks_failed_and_authorized_events(self):
        before = self.snapshot()
        self.assertEqual(self.deliver("payment.failed", amount=1), O.REJECTED_MISMATCH)
        self.assertEqual(self.deliver("payment.authorized", amount=1), O.REJECTED_MISMATCH)
        self.assertEqual(self.snapshot(), before)

    def test_events_we_do_not_act_on_are_acknowledged_and_recorded(self):
        before = self.snapshot()
        for kind in ("refund.processed", "payment.dispute.created", "settlement.processed", "order.notification.delivered"):
            self.assertEqual(self.deliver(kind), O.IGNORED_EVENT)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.events()), 4)

    def test_the_event_table_records_each_outcome_as_text(self):
        self.deliver("payment.authorized", event_id="e1")
        self.deliver("payment.captured", event_id="e2")
        self.deliver("refund.created", event_id="e3")
        self.assertEqual({e[0]: e[4] for e in self.events()}, {"e1": "authorized", "e2": "paid", "e3": "ignored_event"})


class AtomicityTests(WebhookCase):
    def test_a_failure_while_paying_undoes_everything_including_the_claim(self):
        before = self.snapshot()
        with mock.patch("app.services.reservation_service.ReservationService.consume_for_order", return_value=False):
            with self.assertRaises(Exception):
                self.deliver(event_id="evt_boom")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events(), [])  # so Razorpay's retry is processed, not mistaken for a duplicate
        self.assertEqual(self.deliver(event_id="evt_boom"), O.PAID)
        self.assert_paid()

    def test_a_failure_after_the_claim_but_before_the_state_change_undoes_the_claim(self):
        with mock.patch("app.services.payment_webhook_service.PaymentWebhookService._apply", side_effect=RuntimeError("db went away")):
            with self.assertRaises(RuntimeError):
                self.deliver(event_id="evt_retry")
        self.assertEqual(self.events(), [])
        self.assertEqual(self.deliver(event_id="evt_retry"), O.PAID)

    def test_a_failure_to_record_the_outcome_undoes_the_payment_too(self):
        before = self.snapshot()
        with mock.patch("app.repositories.payment_webhook_repository.PaymentWebhookRepository.set_outcome", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                self.deliver(event_id="evt_y")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events(), [])


class ConcurrencyTests(WebhookCase):
    def _deliver_job(self, event, event_id, **fields):
        def job():
            return self.deliver(event, event_id=event_id, **fields)
        return job

    def test_the_same_event_delivered_at_the_same_moment_is_processed_once(self):
        for round_ in range(4):
            with self.subTest(round=round_):
                self.fresh_round(round_)
                results = run_concurrently([self._deliver_job("payment.captured", f"evt_twin{round_}")] * 4)
                self.assertEqual([k for k, _ in results], ["ok"] * 4, results)
                outcomes = sorted(v.value for _, v in results)
                self.assertEqual(outcomes, ["duplicate", "duplicate", "duplicate", "paid"])
                self.assert_paid()
                self.assertEqual(len([e for e in self.events() if e[0] == f"evt_twin{round_}"]), 1)

    def test_two_different_events_for_the_same_payment_pay_it_once(self):
        results = run_concurrently([
            self._deliver_job("payment.captured", "evt_one"),
            self._deliver_job("payment.captured", "evt_two"),
        ])
        self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
        self.assertEqual(sorted(v.value for _, v in results), ["already_recorded", "paid"])
        self.assert_paid()

    def test_a_webhook_racing_the_browser_pays_exactly_once(self):
        gateway = FakeGateway()

        def browser():
            rz, pay_id, order_id = self.rz, self.pay_id, self.order_id  # read once, in this thread's turn
            with new_session() as s:
                return PaymentService(s, gateway).verify_payment(
                    self.user_id, order_id, razorpay_order_id=rz, razorpay_payment_id=pay_id,
                    razorpay_signature=sign(rz, pay_id)).outcome.value

        for round_ in range(4):
            with self.subTest(round=round_):
                self.fresh_round(round_)
                gateway.register_payment(self.pay_id, order_id=self.rz, amount_paise=40621)
                results = run_concurrently([browser, self._deliver_job("payment.captured", f"evt_race{round_}")])
                self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
                self.assert_paid()
                self.assertEqual(self.stock(self.product), (4, 0))

    def test_a_webhook_racing_a_cancel_one_wins_and_money_is_never_lost(self):
        def cancel():
            try:
                user_id, order_id = self.user_id, self.order_id
                with new_session() as s:
                    OrderService(s).cancel_order(user_id, order_id)
                return "cancelled"
            except OrderNotCancellableError:
                return "refused"

        for round_ in range(6):
            with self.subTest(round=round_):
                self.fresh_round(round_)
                results = run_concurrently([cancel, self._deliver_job("payment.captured", f"evt_vs_cancel{round_}")])
                self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
                cancel_result, webhook_result = (v for _, v in results)
                p = self.payment_row()
                self.assertEqual(p.status, S.CAPTURED)  # the money is on record either way
                if webhook_result is O.PAID:
                    self.assertEqual(cancel_result, "refused")
                    self.assert_paid()
                else:
                    self.assertEqual((cancel_result, webhook_result), ("cancelled", O.LATE_PAYMENT))
                    self.assertTrue(p.refund_required)
                    self.assertEqual(self.stock(self.product), (5, 0))
                    self.assertEqual(self.used_count(self.coupon), 0)  # coupon given back once

    def test_a_late_failure_racing_a_capture_never_unpays_it(self):
        for round_ in range(6):
            with self.subTest(round=round_):
                self.fresh_round(round_)
                results = run_concurrently([
                    self._deliver_job("payment.captured", f"evt_cap{round_}"),
                    self._deliver_job("payment.failed", f"evt_fail{round_}", status="failed"),
                ])
                self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
                p = self.payment_row()
                if p.status == S.CAPTURED:
                    self.assert_paid()
                else:
                    # failed first, then captured on top of it: still paid
                    self.fail(f"the payment ended as {p.status}")

    def test_the_webhook_waits_for_an_order_that_is_locked_elsewhere(self):
        """The order lock is what orders the webhook against verify, cancel and expiry."""
        holder = new_session()
        holder.query(Order).filter(Order.id == self.order_id).with_for_update().one()
        done = threading.Event()
        result = {}

        def run():
            result["outcome"] = self.deliver()
            done.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            time.sleep(0.5)
            self.assertFalse(done.is_set(), "the webhook did not wait for the order lock")
        finally:
            holder.rollback()
            holder.close()
        thread.join(30)
        self.assertEqual(result["outcome"], O.PAID)


class PaymentRowLockTests(WebhookCase):
    def test_the_webhook_also_waits_for_the_payment_row_to_be_free(self):
        """Whoever is changing the payment right now finishes first."""
        holder = new_session()
        holder.query(Payment).filter(Payment.id == self.payment.id).with_for_update().one()
        done = threading.Event()
        result = {}

        def run():
            result["outcome"] = self.deliver()
            done.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            time.sleep(0.5)
            self.assertFalse(done.is_set(), "the webhook did not wait for the payment row lock")
        finally:
            holder.rollback()
            holder.close()
        thread.join(30)
        self.assertEqual(result["outcome"], O.PAID)


class PrivacyTests(WebhookCase):
    def test_neither_the_secret_nor_the_customers_details_reach_the_log_or_the_table(self):
        with self.assertLogs(level="DEBUG") as logs:
            logging.getLogger("test").debug("marker")  # assertLogs needs at least one record
            self.deliver("payment.captured", event_id="evt_priv")
            self.deliver("payment.captured", event_id="evt_priv")
            with self.assertRaises(WebhookSignatureError):
                self.deliver(signature="0" * 64)
        text = "\n".join(logs.output)
        for secret in (SECRET, EMAIL, "+919999999999"):
            self.assertNotIn(secret, text)
        self.assertNotIn(webhook_signature(SECRET, make_body()), text)
        self.assertIn("evt_priv", text)  # what IS logged: the event id and the outcome
        with new_session() as s:
            from sqlalchemy import text as sql

            row = s.execute(sql("select to_jsonb(e)::text from payment_webhook_events e limit 1")).scalar()
        self.assertNotIn(EMAIL, row)
        self.assertNotIn("919999999999", row)

    def test_the_service_never_exposes_the_secret(self):
        with new_session() as s:
            service = PaymentWebhookService(s, SECRET)
            self.assertNotIn(SECRET, repr(vars(service).get("db", "")))
            self.assertNotIn(SECRET, str(service.__dict__.get("events", "")))


if __name__ == "__main__":
    unittest.main()
