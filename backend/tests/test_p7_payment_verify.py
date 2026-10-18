"""
Phase 7 / Milestone 5: PaymentService.verify_payment on real PostgreSQL, with a
fake gateway (no network) and the REAL signature check.

Groups:
  PaidTests          a genuine captured payment pays the order and sells the stock
  IdempotencyTests   repeating a verification changes nothing
  RejectionTests     forged, foreign or unconfirmed payments change nothing
  AuthorizedTests    authorized-but-not-captured money does not pay
  LatePaymentTests   money after the order closed is recorded and flagged, never revives it
  AtomicityTests     a failure half-way undoes everything
  ConcurrencyTests   real threads, real row locks
"""

import logging
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

from app.core.exceptions import (
    LatePaymentError,
    OrderAlreadyPaidError,
    OrderNotCancellableError,
    OrderNotFoundError,
    PaymentVerificationError,
    PaymentVerificationUnavailableError,
)
from app.models import (
    Order,
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus as S,
)
from app.repositories.order_repository import OrderRepository
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService, VerifyOutcome
from app.services.reservation_service import ReservationInvariantError, ReservationService
from tests.payment_fakes import FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session, run_concurrently

RZ_ORDER = "order_PAYTEST01"
PAY_ID = "pay_TESTPAYMENT01"


class VerifyTestCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.order = self.make_order(self.user, [(self.product, 1)])   # reserves 1 unit: stock is (5, 1)
        self.payment = self.make_payment(self.order, gateway_order_id=RZ_ORDER)
        self.gateway = FakeGateway()
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621)

    def verify(self, *, order=None, user=None, rz_order=RZ_ORDER, pay_id=PAY_ID, signature=None, gateway=None):
        order, user, gateway = order or self.order, user or self.user, gateway or self.gateway
        signature = sign(rz_order, pay_id) if signature is None else signature
        with new_session() as session:
            return PaymentService(session, gateway).verify_payment(
                user.id, order.id, razorpay_order_id=rz_order, razorpay_payment_id=pay_id, razorpay_signature=signature
            )

    def reload_order(self, order=None) -> Order:
        with new_session() as s:
            row = s.get(Order, (order or self.order).id)
            s.expunge(row)
            return row

    def reload_payment(self, payment=None) -> Payment:
        with new_session() as s:
            row = s.get(Payment, (payment or self.payment).id)
            s.expunge(row)
            return row

    def snapshot(self, order=None, payment=None):
        """Everything a refused verification must leave alone."""
        o, p = self.reload_order(order), self.reload_payment(payment)
        return (
            (o.status, o.payment_status, o.inventory_state, o.cancellation_reason),
            (p.status, p.gateway_payment_id, p.gateway_signature, p.paid_at, p.refund_required),
            self.stock(self.product),
        )

    def assert_unchanged(self, action, *, expect=PaymentVerificationError):
        before = self.snapshot()
        with self.assertRaises(expect):
            action()
        self.assertEqual(self.snapshot(), before)


class PaidTests(VerifyTestCase):
    def test_a_genuine_captured_payment_pays_the_order(self):
        result = self.verify()
        self.assertIs(result.outcome, VerifyOutcome.PAID)

        order = self.reload_order()
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.inventory_state, OrderInventoryState.CONSUMED)
        self.assertIsNone(order.cancellation_reason)

        payment = self.reload_payment()
        self.assertEqual(payment.status, S.CAPTURED)
        self.assertEqual(payment.gateway_payment_id, PAY_ID)
        self.assertEqual(payment.gateway_signature, sign(RZ_ORDER, PAY_ID))
        self.assertIsNotNone(payment.paid_at)
        self.assertFalse(payment.refund_required)
        self.assertIsNone(payment.failure_reason)

    def test_the_reply_is_the_order_as_it_now_stands(self):
        order = self.verify().order
        self.assertEqual(order.id, self.order.id)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertFalse(order.can_cancel)  # a paid order is not cancellable
        self.assertEqual(order.totals.total, 406.21)

    def test_the_reserved_units_become_sold_units(self):
        self.assertEqual(self.stock(self.product), (5, 1))
        self.verify()
        self.assertEqual(self.stock(self.product), (4, 0))  # quantity down by one, nothing left reserved

    def test_every_line_of_the_order_is_consumed(self):
        other = self.make_product(price="100.00", stock=10)
        order = self.make_order(self.user, [(self.product, 2), (other, 3)])
        total = int(Decimal("406.21") * 2 * 100 + 300 * 100)
        payment = self.make_payment(order, gateway_order_id="order_MULTI01", amount=order.total_amount)
        self.gateway.register_payment("pay_MULTI01", order_id="order_MULTI01", amount_paise=total)
        before_first, before_other = self.stock(self.product), self.stock(other)
        self.verify(order=order, rz_order="order_MULTI01", pay_id="pay_MULTI01")
        self.assertEqual(self.stock(self.product), (before_first[0] - 2, before_first[1] - 2))
        self.assertEqual(self.stock(other), (before_other[0] - 3, before_other[1] - 3))
        self.assertEqual(self.reload_payment(payment).status, S.CAPTURED)

    def test_the_coupon_use_is_kept_not_given_back(self):
        coupon = self.make_coupon()
        with new_session() as s:
            from app.models import Coupon

            s.query(Coupon).filter(Coupon.id == coupon.id).update({Coupon.used_count: 1})
            s.commit()
        order = self.make_order(self.user, [(self.product, 1)], coupon=coupon)
        self.make_payment(order, gateway_order_id="order_CPN01", amount=order.total_amount)
        self.gateway.register_payment("pay_CPN01", order_id="order_CPN01", amount_paise=40621)
        self.verify(order=order, rz_order="order_CPN01", pay_id="pay_CPN01")
        self.assertEqual(self.used_count(coupon), 1)

    def test_it_asks_razorpay_what_really_happened(self):
        self.verify()
        self.assertEqual(self.gateway.fetches, [PAY_ID])

    def test_a_late_success_after_a_failed_attempt_pays_the_order(self):
        with new_session() as s:
            s.query(Payment).filter(Payment.id == self.payment.id).update({Payment.status: S.FAILED, Payment.failure_reason: "declined"})
            s.commit()
        self.assertIs(self.verify().outcome, VerifyOutcome.PAID)
        payment = self.reload_payment()
        self.assertEqual(payment.status, S.CAPTURED)
        self.assertIsNone(payment.failure_reason)

    def test_it_pays_from_an_authorized_payment_too(self):
        with new_session() as s:
            s.query(Payment).filter(Payment.id == self.payment.id).update({Payment.status: S.AUTHORIZED})
            s.commit()
        self.assertIs(self.verify().outcome, VerifyOutcome.PAID)

    def test_an_order_past_its_deadline_but_still_holding_stock_is_paid(self):
        """The expiry job has not run yet; the customer did pay, and the stock is still theirs."""
        with new_session() as s:
            s.query(Order).filter(Order.id == self.order.id).update({Order.expires_at: datetime.now(timezone.utc) - timedelta(minutes=5)})
            s.commit()
        self.assertIs(self.verify().outcome, VerifyOutcome.PAID)
        self.assertEqual(self.stock(self.product), (4, 0))


class IdempotencyTests(VerifyTestCase):
    def test_repeating_the_verification_changes_nothing_and_asks_razorpay_once(self):
        first = self.verify()
        after_first = self.snapshot()
        second = self.verify()
        third = self.verify()
        self.assertIs(first.outcome, VerifyOutcome.PAID)
        self.assertIs(second.outcome, VerifyOutcome.ALREADY_PAID)
        self.assertIs(third.outcome, VerifyOutcome.ALREADY_PAID)
        self.assertEqual(second.order.payment_status, OrderPaymentStatus.PAID)
        self.assertEqual(self.snapshot(), after_first)
        self.assertEqual(self.gateway.fetches, [PAY_ID])   # the repeats were answered from the database
        self.assertEqual(self.stock(self.product), (4, 0))  # consumed exactly once

    def test_a_repeat_works_even_if_razorpay_is_down(self):
        self.verify()
        self.assertIs(self.verify(gateway=FakeGateway(fetch_fails=True)).outcome, VerifyOutcome.ALREADY_PAID)

    def test_a_repeat_still_needs_a_genuine_signature(self):
        self.verify()
        self.assert_unchanged(lambda: self.verify(signature="0" * 64))

    def test_a_different_signed_payment_id_for_a_paid_razorpay_order_is_refused(self):
        self.verify()
        other = "pay_SECONDPAY01"
        self.gateway.register_payment(other, order_id=RZ_ORDER, amount_paise=40621)
        self.assert_unchanged(lambda: self.verify(pay_id=other), expect=OrderAlreadyPaidError)
        self.assertEqual(self.reload_payment().gateway_payment_id, PAY_ID)

    def test_a_refunded_payment_is_reported_as_it_is(self):
        self.verify()
        with new_session() as s:
            s.query(Payment).filter(Payment.id == self.payment.id).update({Payment.status: S.REFUNDED})
            s.commit()
        before = self.snapshot()
        self.assertIs(self.verify().outcome, VerifyOutcome.ALREADY_PAID)
        self.assertEqual(self.snapshot(), before)


class RejectionTests(VerifyTestCase):
    def test_a_wrong_signature_is_refused_before_anything_else(self):
        for bad in ("0" * 64, sign(RZ_ORDER, PAY_ID, secret="another-secret"), sign(RZ_ORDER, "pay_OTHER"), sign("order_OTHER", PAY_ID), "x"):
            with self.subTest(signature=bad[:12]):
                self.assert_unchanged(lambda bad=bad: self.verify(signature=bad))
        self.assertEqual(self.gateway.fetches, [])  # never even asked Razorpay

    def test_the_browsers_own_success_is_worth_nothing_without_a_signature(self):
        self.assert_unchanged(lambda: self.verify(signature=""))
        self.assertEqual(self.reload_order().payment_status, OrderPaymentStatus.PENDING)

    def test_a_rejected_signature_is_logged_without_the_signature_or_secret(self):
        with self.assertLogs("app.services.payment_service", level=logging.WARNING) as logs:
            with self.assertRaises(PaymentVerificationError):
                self.verify(signature="deadbeef" * 8)
        text = "\n".join(logs.output)
        self.assertNotIn("deadbeef", text)
        self.assertNotIn("fake-key-secret", text)

    def test_a_razorpay_order_that_belongs_to_a_different_order_is_refused(self):
        other_order = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(other_order, gateway_order_id="order_OTHERS01", amount=other_order.total_amount)
        self.gateway.register_payment("pay_OTHERS01", order_id="order_OTHERS01", amount_paise=40621)
        # A perfectly genuine payment for ANOTHER order, presented for this one.
        self.assert_unchanged(lambda: self.verify(rz_order="order_OTHERS01", pay_id="pay_OTHERS01"))
        self.assertEqual(self.reload_order(other_order).payment_status, OrderPaymentStatus.PENDING)

    def test_an_unknown_razorpay_order_is_refused(self):
        self.gateway.register_payment("pay_GHOST01", order_id="order_GHOST01", amount_paise=40621)
        self.assert_unchanged(lambda: self.verify(rz_order="order_GHOST01", pay_id="pay_GHOST01"))

    def test_someone_elses_order_looks_like_a_missing_one_even_with_a_genuine_signature(self):
        stranger = self.make_user()
        self.assert_unchanged(lambda: self.verify(user=stranger), expect=OrderNotFoundError)
        self.assertEqual(self.gateway.fetches, [])

    def test_an_unknown_order(self):
        import uuid

        with self.assertRaises(OrderNotFoundError):
            with new_session() as s:
                PaymentService(s, self.gateway).verify_payment(
                    self.user.id, uuid.uuid4(), razorpay_order_id=RZ_ORDER, razorpay_payment_id=PAY_ID,
                    razorpay_signature=sign(RZ_ORDER, PAY_ID),
                )

    def test_razorpays_own_record_must_match_ours(self):
        mismatches = {
            "different order": dict(order_id="order_SOMEOTHER"),
            "less money": dict(amount_paise=40620),
            "more money": dict(amount_paise=40622),
            "tiny amount": dict(amount_paise=1),
            "different currency": dict(currency="USD"),
        }
        for name, change in mismatches.items():
            with self.subTest(case=name):
                values = dict(order_id=RZ_ORDER, amount_paise=40621, status="captured", currency="INR")
                values.update(change)
                self.gateway.register_payment(PAY_ID, **values)
                self.assert_unchanged(self.verify)

    def test_a_razorpay_reply_about_a_different_payment_is_refused(self):
        from app.services.razorpay_gateway import GatewayPayment

        self.gateway.payments[PAY_ID] = GatewayPayment(id="pay_SOMEONEELSE", order_id=RZ_ORDER, amount_paise=40621, currency="INR", status="captured")
        self.assert_unchanged(self.verify)

    def test_a_payment_that_is_not_captured_or_authorized_is_refused(self):
        for status in ("created", "failed", "refunded", "something_new"):
            with self.subTest(status=status):
                self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status=status)
                self.assert_unchanged(self.verify)

    def test_razorpay_being_unreachable_is_a_502_that_does_not_claim_nothing_was_charged(self):
        gateway = FakeGateway(fetch_fails=True)
        before = self.snapshot()
        with self.assertRaises(PaymentVerificationUnavailableError) as ctx:
            self.verify(gateway=gateway)
        self.assertEqual(ctx.exception.http_status, 502)
        self.assertNotIn("nothing was charged", ctx.exception.message.lower())
        self.assertIn("don't pay again", ctx.exception.message)
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.verify().outcome, VerifyOutcome.PAID)  # and it works once Razorpay is back

    def test_a_payment_id_already_used_elsewhere_is_refused(self):
        other_order = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(other_order, gateway_order_id="order_OTHERS02", status=S.CAPTURED, gateway_payment_id=PAY_ID,
                          amount=other_order.total_amount)
        self.assert_unchanged(self.verify)


class AuthorizedTests(VerifyTestCase):
    def test_authorized_money_is_recorded_but_does_not_pay_the_order(self):
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status="authorized")
        result = self.verify()
        self.assertIs(result.outcome, VerifyOutcome.PENDING_CAPTURE)
        self.assertEqual(result.order.payment_status, OrderPaymentStatus.PENDING)

        order, payment = self.reload_order(), self.reload_payment()
        self.assertEqual((order.status, order.payment_status, order.inventory_state),
                         (OrderStatus.PENDING, OrderPaymentStatus.PENDING, OrderInventoryState.RESERVED))
        self.assertEqual(payment.status, S.AUTHORIZED)
        self.assertEqual(payment.gateway_payment_id, PAY_ID)
        self.assertIsNone(payment.paid_at)
        self.assertEqual(self.stock(self.product), (5, 1))  # nothing sold yet

    def test_once_it_is_captured_the_same_call_pays_the_order(self):
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status="authorized")
        self.verify()
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status="captured")
        self.assertIs(self.verify().outcome, VerifyOutcome.PAID)
        self.assertEqual(self.stock(self.product), (4, 0))

    def test_repeating_while_authorized_is_harmless(self):
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status="authorized")
        self.verify()
        before = self.snapshot()
        self.assertIs(self.verify().outcome, VerifyOutcome.PENDING_CAPTURE)
        self.assertEqual(self.snapshot(), before)


class LatePaymentTests(VerifyTestCase):
    """Money arrived but the order can no longer be bought: record it, flag it
    for a refund, and leave the order exactly as it was."""

    def closed_order(self, **kwargs):
        order = self.make_order(self.user, [(self.product, 1)], **kwargs)
        self.make_payment(order, gateway_order_id="order_LATE01", amount=order.total_amount)
        self.gateway.register_payment("pay_LATE01", order_id="order_LATE01", amount_paise=40621)
        return order

    def verify_late(self, order):
        return self.verify(order=order, rz_order="order_LATE01", pay_id="pay_LATE01")

    def assert_recorded_for_refund(self, order):
        with new_session() as s:
            payment = s.query(Payment).filter(Payment.order_id == order.id).one()
            self.assertEqual(payment.status, S.CAPTURED)
            self.assertEqual(payment.gateway_payment_id, "pay_LATE01")
            self.assertTrue(payment.refund_required)
            self.assertIsNotNone(payment.paid_at)

    def test_after_the_customer_cancelled(self):
        order = self.closed_order(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED)
        stock_before = self.stock(self.product)
        with self.assertRaises(LatePaymentError) as ctx:
            self.verify_late(order)
        self.assertEqual(ctx.exception.http_status, 409)
        self.assertIn("refund", ctx.exception.message.lower())

        self.assert_recorded_for_refund(order)  # recorded even though the call raised
        after = self.reload_order(order)
        self.assertEqual((after.status, after.payment_status, after.inventory_state),
                         (OrderStatus.CANCELLED, OrderPaymentStatus.PENDING, OrderInventoryState.RELEASED))
        self.assertEqual(self.stock(self.product), stock_before)  # stock is not touched again

    def test_after_the_order_expired(self):
        order = self.closed_order(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED,
                                  cancellation_reason=OrderCancellationReason.EXPIRED)
        with self.assertRaises(LatePaymentError):
            self.verify_late(order)
        self.assert_recorded_for_refund(order)
        after = self.reload_order(order)
        self.assertEqual((after.status, after.cancellation_reason), (OrderStatus.CANCELLED, OrderCancellationReason.EXPIRED))

    def test_when_the_stock_has_already_been_given_back(self):
        order = self.closed_order(inventory_state=OrderInventoryState.RELEASED)
        before = self.stock(self.product)
        with self.assertRaises(LatePaymentError):
            self.verify_late(order)
        self.assert_recorded_for_refund(order)
        self.assertEqual(self.reload_order(order).payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(self.stock(self.product), before)

    def test_a_second_payment_for_an_order_that_is_already_paid(self):
        """First Razorpay order failed, a retry paid, then the first one's bank finally went through."""
        order = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(order, gateway_order_id="order_FIRST01", status=S.FAILED, amount=order.total_amount)
        self.make_payment(order, gateway_order_id="order_SECOND01", amount=order.total_amount)
        self.gateway.register_payment("pay_SECOND01", order_id="order_SECOND01", amount_paise=40621)
        self.gateway.register_payment("pay_FIRST01", order_id="order_FIRST01", amount_paise=40621)
        self.verify(order=order, rz_order="order_SECOND01", pay_id="pay_SECOND01")
        stock_after_payment = self.stock(self.product)

        with self.assertRaises(LatePaymentError):
            self.verify(order=order, rz_order="order_FIRST01", pay_id="pay_FIRST01")
        with new_session() as s:
            rows = {p.gateway_order_id: p for p in s.query(Payment).filter(Payment.order_id == order.id).all()}
            self.assertEqual(rows["order_SECOND01"].status, S.CAPTURED)
            self.assertFalse(rows["order_SECOND01"].refund_required)
            self.assertEqual(rows["order_FIRST01"].status, S.CAPTURED)
            self.assertTrue(rows["order_FIRST01"].refund_required)  # the duplicate is the one to refund
        self.assertEqual(self.stock(self.product), stock_after_payment)  # consumed once, not twice

    def test_repeating_a_late_verification_stays_a_late_payment_and_changes_nothing(self):
        order = self.closed_order(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED)
        with self.assertRaises(LatePaymentError):
            self.verify_late(order)
        with new_session() as s:
            first = s.query(Payment).filter(Payment.order_id == order.id).one()
            snapshot = (first.status, first.paid_at, first.refund_required, first.gateway_payment_id)
        fetches = len(self.gateway.fetches)
        with self.assertRaises(LatePaymentError):
            self.verify_late(order)
        with new_session() as s:
            again = s.query(Payment).filter(Payment.order_id == order.id).one()
            self.assertEqual((again.status, again.paid_at, again.refund_required, again.gateway_payment_id), snapshot)
        self.assertEqual(len(self.gateway.fetches), fetches)

    def test_a_late_payment_never_revives_an_order_whatever_its_state(self):
        for kwargs in (
            dict(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED),
            dict(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED,
                 cancellation_reason=OrderCancellationReason.EXPIRED),
        ):
            order = self.make_order(self.user, [(self.product, 1)], **kwargs)
            rz, pay = f"order_REV{order.order_number[-3:]}".replace("-", ""), f"pay_REV{order.order_number[-3:]}".replace("-", "")
            self.make_payment(order, gateway_order_id=rz, amount=order.total_amount)
            self.gateway.register_payment(pay, order_id=rz, amount_paise=40621)
            with self.assertRaises(LatePaymentError):
                self.verify(order=order, rz_order=rz, pay_id=pay)
            self.assertEqual(self.reload_order(order).status, OrderStatus.CANCELLED)


class AtomicityTests(VerifyTestCase):
    def test_a_failure_while_consuming_stock_undoes_the_payment_too(self):
        before = self.snapshot()
        with mock.patch.object(ReservationService, "consume_for_order", side_effect=ReservationInvariantError("books do not balance")):
            with self.assertRaises(ReservationInvariantError):
                self.verify()
        self.assertEqual(self.snapshot(), before)  # payment still initiated, order still pending, stock untouched
        self.assertIs(self.verify().outcome, VerifyOutcome.PAID)  # and a retry succeeds cleanly

    def test_a_consume_that_finds_nothing_to_consume_rolls_everything_back(self):
        before = self.snapshot()
        with mock.patch.object(ReservationService, "consume_for_order", return_value=False):
            with self.assertRaises(ReservationInvariantError):
                self.verify()
        self.assertEqual(self.snapshot(), before)

    def test_an_order_that_cannot_be_marked_paid_rolls_everything_back(self):
        before = self.snapshot()
        with mock.patch.object(OrderRepository, "mark_paid", return_value=False):
            with self.assertRaises(ReservationInvariantError):
                self.verify()
        self.assertEqual(self.snapshot(), before)

    def test_a_failure_leaves_no_lock_behind(self):
        with mock.patch.object(ReservationService, "consume_for_order", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.verify()
        with new_session() as s:
            s.execute(__import__("sqlalchemy").text("SET LOCAL lock_timeout = '1s'"))
            self.assertIsNotNone(s.query(Order).filter(Order.id == self.order.id).with_for_update().first())

    def test_mark_paid_is_a_compare_and_set(self):
        with new_session() as s:
            repo = OrderRepository(s)
            self.assertTrue(repo.mark_paid(self.order.id))
            self.assertFalse(repo.mark_paid(self.order.id))   # already paid: nothing to do
            s.commit()
        cancelled = self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED)
        with new_session() as s:
            self.assertFalse(OrderRepository(s).mark_paid(cancelled.id))   # a cancelled order can never become paid
        with new_session() as s:
            self.assertEqual(s.get(Order, cancelled.id).status, OrderStatus.CANCELLED)

    def test_mark_paid_needs_every_condition_on_its_own(self):
        """pending status, pending payment and a held reservation - each one alone blocks it."""
        cases = {
            "cancelled but still reserved": dict(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RESERVED, reserve_stock=False),
            "pending but stock released": dict(inventory_state=OrderInventoryState.RELEASED),
            "pending but stock consumed": dict(inventory_state=OrderInventoryState.CONSUMED),
            "confirmed, unpaid, reserved": dict(status=OrderStatus.CONFIRMED, reserve_stock=False),
            "failed payment status": dict(payment_status=OrderPaymentStatus.FAILED, reserve_stock=False),
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                order = self.make_order(self.user, [(self.product, 1)], **kwargs)
                with new_session() as s:
                    self.assertFalse(OrderRepository(s).mark_paid(order.id))
                    s.rollback()
                self.assertNotEqual(self.reload_order(order).payment_status, OrderPaymentStatus.PAID)

    def test_the_order_is_confirmed_only_together_with_being_paid(self):
        self.verify()
        o = self.reload_order()
        self.assertEqual((o.status, o.payment_status), (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID))


class ConcurrencyTests(VerifyTestCase):
    def test_simultaneous_verifications_pay_once_and_consume_once(self):
        gateway = FakeGateway(delay=0.2)
        gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621)
        user_id, order_id = self.user.id, self.order.id
        signature = sign(RZ_ORDER, PAY_ID)

        def job():
            with new_session() as s:
                return PaymentService(s, gateway).verify_payment(
                    user_id, order_id, razorpay_order_id=RZ_ORDER, razorpay_payment_id=PAY_ID, razorpay_signature=signature
                )

        results = run_concurrently([job] * 8)
        self.assertEqual([r[0] for r in results], ["ok"] * 8, results)
        outcomes = [r[1].outcome for r in results]
        self.assertEqual(outcomes.count(VerifyOutcome.PAID), 1)
        self.assertEqual(outcomes.count(VerifyOutcome.ALREADY_PAID), 7)
        self.assertEqual(len(gateway.fetches), 1)
        self.assertEqual(self.stock(self.product), (4, 0))
        with new_session() as s:
            self.assertEqual(s.query(Payment).filter(Payment.status == S.CAPTURED).count(), 1)

    def test_a_cancel_racing_a_verification_cannot_both_win(self):
        """The verification holds the order lock while it asks Razorpay; the cancel waits, then finds a paid order."""
        gateway = FakeGateway(delay=0.3)
        gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621)
        user_id, order_id = self.user.id, self.order.id
        signature = sign(RZ_ORDER, PAY_ID)

        def verify():
            with new_session() as s:
                return PaymentService(s, gateway).verify_payment(
                    user_id, order_id, razorpay_order_id=RZ_ORDER, razorpay_payment_id=PAY_ID, razorpay_signature=signature
                )

        def cancel():
            import time

            time.sleep(0.1)  # let the verification take the lock first
            with new_session() as s:
                return OrderService(s).cancel_order(user_id, order_id)

        results = run_concurrently([verify, cancel])
        self.assertEqual(results[0][0], "ok", results)
        self.assertEqual(results[1][0], "err", results)
        self.assertIsInstance(results[1][1], OrderNotCancellableError)
        order = self.reload_order()
        self.assertEqual((order.status, order.payment_status, order.inventory_state),
                         (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID, OrderInventoryState.CONSUMED))
        self.assertEqual(self.stock(self.product), (4, 0))

    def test_a_cancel_that_wins_first_makes_the_payment_a_late_one(self):
        with new_session() as s:
            OrderService(s).cancel_order(self.user.id, self.order.id)
        stock_after_cancel = self.stock(self.product)
        with self.assertRaises(LatePaymentError):
            self.verify()
        self.assertEqual(self.stock(self.product), stock_after_cancel)
        payment = self.reload_payment()
        self.assertEqual((payment.status, payment.refund_required), (S.CAPTURED, True))
        self.assertEqual(self.reload_order().status, OrderStatus.CANCELLED)

    def test_verification_does_not_deadlock_with_payment_creation(self):
        """Opening a new Razorpay order while a verification is in progress waits its turn."""
        from app.models import Payment as P

        with new_session() as s:
            s.query(P).filter(P.id == self.payment.id).update({P.status: S.FAILED})
            s.commit()
        gateway = FakeGateway(delay=0.2)
        gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621)
        user_id, order_id = self.user.id, self.order.id
        signature = sign(RZ_ORDER, PAY_ID)

        def verify():
            with new_session() as s:
                return PaymentService(s, gateway).verify_payment(
                    user_id, order_id, razorpay_order_id=RZ_ORDER, razorpay_payment_id=PAY_ID, razorpay_signature=signature
                )

        def create():
            import time

            time.sleep(0.05)
            with new_session() as s:
                return PaymentService(s, gateway).create_razorpay_order(user_id, order_id)

        results = run_concurrently([verify, create])
        self.assertEqual(results[0][0], "ok", results)
        # Either the creation ran first (and the order was payable) or it ran after the payment (and is refused): never a hang or a corrupt state.
        order = self.reload_order()
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)


if __name__ == "__main__":
    unittest.main()
