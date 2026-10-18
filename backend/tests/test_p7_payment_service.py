"""
Phase 7 / Milestone 3: PaymentService.create_razorpay_order on real PostgreSQL,
with a fake gateway (no network).

Groups:
  CreationTests      what a good Razorpay order looks like
  RefusalTests       every refusal changes nothing and never calls Razorpay
  IdempotencyTests   repeated requests keep ONE Razorpay order
  RetryTests         a new attempt after a failed one
  FailureTests       Razorpay down -> nothing stored
  ConcurrencyTests   real threads, real row locks
"""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

from app.core.exceptions import (
    DomainError,
    OrderAlreadyPaidError,
    OrderNotFoundError,
    OrderNotPayableError,
    PaymentGatewayError,
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
from app.repositories.payment_repository import PaymentRepository
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService, build_receipt
from tests.payment_fakes import FakeGateway
from tests.pg_support import PostgresTestCase, new_session, run_concurrently


class PaymentServiceTestCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.order = self.make_order(self.user, [(self.product, 1)])
        self.gateway = FakeGateway()

    def pay(self, order=None, user=None, gateway=None):
        """One request: its own session, like a real API call."""
        order = order or self.order
        user = user or self.user
        with new_session() as session:
            return PaymentService(session, gateway or self.gateway).create_razorpay_order(user.id, order.id)

    def payments(self, order=None):
        with new_session() as s:
            rows = s.query(Payment).filter(Payment.order_id == (order or self.order).id).order_by(Payment.created_at).all()
            s.expunge_all()
            return rows

    def reload_order(self, order=None) -> Order:
        with new_session() as s:
            row = s.get(Order, (order or self.order).id)
            s.expunge(row)
            return row


class CreationTests(PaymentServiceTestCase):
    def test_creates_a_razorpay_order_and_stores_an_initiated_payment(self):
        result = self.pay()
        self.assertTrue(result.created)
        (payment,) = self.payments()
        self.assertEqual(payment.status, S.INITIATED)
        self.assertEqual(payment.payment_gateway, "razorpay")
        self.assertEqual(payment.gateway_order_id, result.intent.razorpay_order_id)
        self.assertEqual(payment.amount, Decimal("406.21"))
        self.assertEqual(payment.currency, "INR")
        self.assertIsNone(payment.gateway_payment_id)
        self.assertIsNone(payment.gateway_signature)
        self.assertIsNone(payment.paid_at)
        self.assertFalse(payment.refund_required)

    def test_406_21_rupees_is_40621_paise_at_razorpay(self):
        result = self.pay()
        (call,) = self.gateway.calls
        self.assertEqual(call["amount_paise"], 40621)
        self.assertIsInstance(call["amount_paise"], int)
        self.assertEqual(result.intent.amount_paise, 40621)
        self.assertEqual(call["currency"], "INR")

    def test_the_amount_always_comes_from_the_stored_order_total(self):
        with new_session() as s:
            s.query(Order).filter(Order.id == self.order.id).update({Order.total_amount: Decimal("123.45")})
            s.commit()
        result = self.pay()
        self.assertEqual(self.gateway.calls[0]["amount_paise"], 12345)
        self.assertEqual(result.intent.amount_paise, 12345)
        self.assertEqual(self.payments()[0].amount, Decimal("123.45"))

    def test_the_amount_includes_gst_and_delivery_not_just_the_subtotal(self):
        with new_session() as s:
            s.query(Order).filter(Order.id == self.order.id).update(
                {Order.subtotal: Decimal("400.00"), Order.tax_amount: Decimal("20.00"),
                 Order.delivery_charge: Decimal("40.00"), Order.total_amount: Decimal("460.00")}
            )
            s.commit()
        self.pay()
        self.assertEqual(self.gateway.calls[0]["amount_paise"], 46000)

    def test_the_response_has_only_the_safe_fields(self):
        intent = self.pay().intent
        self.assertEqual(
            set(intent.model_dump()),
            {"order_id", "order_number", "razorpay_order_id", "razorpay_key_id", "amount_paise", "currency"},
        )
        self.assertEqual(intent.order_id, self.order.id)
        self.assertEqual(intent.order_number, self.order.order_number)
        self.assertEqual(intent.razorpay_key_id, "rzp_test_FAKEKEYID000000")
        self.assertEqual(intent.currency, "INR")

    def test_what_razorpay_is_sent_carries_no_personal_data(self):
        self.pay()
        (call,) = self.gateway.calls
        self.assertEqual(set(call["notes"]), {"pramanika_order_id", "order_number"})
        blob = repr(call)
        for personal in (self.user.email, self.user.phone_number, self.user.first_name, self.user.last_name):
            self.assertNotIn(personal, blob)

    def test_the_receipt_names_the_order_and_the_attempt(self):
        self.pay()
        self.assertEqual(self.gateway.calls[0]["receipt"], f"{self.order.order_number}-1")

    def test_starting_a_payment_changes_nothing_else(self):
        coupon = self.make_coupon()
        order = self.make_order(self.user, [(self.product, 2)], coupon=coupon)
        stock_before, used_before = self.stock(self.product), self.used_count(coupon)
        self.pay(order)
        after = self.reload_order(order)
        self.assertEqual((after.status, after.payment_status, after.inventory_state),
                         (OrderStatus.PENDING, OrderPaymentStatus.PENDING, OrderInventoryState.RESERVED))
        self.assertEqual(self.stock(self.product), stock_before)
        self.assertEqual(self.used_count(coupon), used_before)

    def test_an_order_with_a_future_deadline_or_none_is_payable(self):
        soon = self.make_order(self.user, [(self.product, 1)], expires_at=datetime.now(timezone.utc) + timedelta(minutes=1))
        never = self.make_order(self.user, [(self.product, 1)], expires_at=None)
        self.assertTrue(self.pay(soon).created)
        self.assertTrue(self.pay(never).created)

    def test_the_order_is_locked_until_the_transaction_ends(self):
        """The mechanism behind 'one Razorpay order per click': while the
        payment is being created nobody else can touch the order row."""
        seen = {}

        class SpyGateway(FakeGateway):
            def create_order(inner, **kwargs):  # noqa: N805
                with new_session() as other:
                    other.execute(__import__("sqlalchemy").text("SET LOCAL lock_timeout = '300ms'"))
                    try:
                        other.query(Order).filter(Order.id == self.order.id).with_for_update(nowait=True).first()
                        seen["locked"] = False
                    except Exception:  # noqa: BLE001
                        seen["locked"] = True
                return super().create_order(**kwargs)

        self.pay(gateway=SpyGateway())
        self.assertTrue(seen["locked"])


class RefusalTests(PaymentServiceTestCase):
    def assert_refused(self, exc_type, order=None, user=None, message_part=None):
        before = len(self.payments(order))
        with self.assertRaises(exc_type) as ctx:
            self.pay(order, user)
        self.assertEqual(self.gateway.calls, [], "Razorpay must not be called for a refused order")
        self.assertEqual(len(self.payments(order)), before)
        if message_part:
            self.assertIn(message_part, ctx.exception.message.lower())
        return ctx.exception

    def test_someone_elses_order_looks_like_a_missing_one(self):
        other = self.make_user()
        error = self.assert_refused(OrderNotFoundError, user=other)
        self.assertEqual(error.http_status, 404)

    def test_an_unknown_order(self):
        import uuid

        with self.assertRaises(OrderNotFoundError):
            with new_session() as s:
                PaymentService(s, self.gateway).create_razorpay_order(self.user.id, uuid.uuid4())
        self.assertEqual(self.gateway.calls, [])

    def test_a_customer_cancelled_order(self):
        order = self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CANCELLED,
                                inventory_state=OrderInventoryState.RELEASED)
        error = self.assert_refused(OrderNotPayableError, order, message_part="cancelled")
        self.assertEqual(error.http_status, 409)

    def test_an_expired_order(self):
        order = self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CANCELLED,
                                inventory_state=OrderInventoryState.RELEASED,
                                cancellation_reason=OrderCancellationReason.EXPIRED)
        self.assert_refused(OrderNotPayableError, order, message_part="expired")

    def test_an_order_past_its_deadline_even_though_the_expiry_job_has_not_run(self):
        order = self.make_order(self.user, [(self.product, 1)], expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        self.assert_refused(OrderNotPayableError, order, message_part="expired")
        self.assertEqual(self.reload_order(order).status, OrderStatus.PENDING)  # refusing does not expire it; the job does

    def test_a_paid_order(self):
        order = self.make_order(self.user, [(self.product, 1)], payment_status=OrderPaymentStatus.PAID,
                                inventory_state=OrderInventoryState.CONSUMED)
        error = self.assert_refused(OrderAlreadyPaidError, order)
        self.assertEqual(error.http_status, 409)

    def test_an_order_that_already_has_a_captured_payment(self):
        self.make_payment(self.order, status=S.CAPTURED)
        before = len(self.payments())
        with self.assertRaises(OrderAlreadyPaidError):
            self.pay()
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(len(self.payments()), before)

    def test_an_order_that_is_not_pending(self):
        order = self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CONFIRMED)
        self.assert_refused(OrderNotPayableError, order)

    def test_an_order_that_no_longer_holds_its_stock(self):
        order = self.make_order(self.user, [(self.product, 1)], inventory_state=OrderInventoryState.RELEASED)
        self.assert_refused(OrderNotPayableError, order)

    def test_an_order_with_nothing_to_pay(self):
        order = self.make_order(self.user, [(self.product, 1)])
        with new_session() as s:
            s.query(Order).filter(Order.id == order.id).update({Order.total_amount: Decimal("0.00")})
            s.commit()
        self.assert_refused(OrderNotPayableError, order, message_part="nothing to pay")

    def test_refusals_never_write_a_payment_row(self):
        for status in (OrderStatus.CANCELLED, OrderStatus.CONFIRMED):
            order = self.make_order(self.user, [(self.product, 1)], status=status,
                                    inventory_state=OrderInventoryState.RELEASED)
            with self.assertRaises(DomainError):
                self.pay(order)
        with new_session() as s:
            self.assertEqual(s.query(Payment).count(), 0)


class IdempotencyTests(PaymentServiceTestCase):
    def test_asking_twice_returns_the_same_razorpay_order(self):
        first, second = self.pay(), self.pay()
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.intent, second.intent)
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(len(self.payments()), 1)

    def test_many_repeats_still_make_one_razorpay_order(self):
        for _ in range(10):
            self.pay()
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(len(self.payments()), 1)

    def test_an_authorized_payment_is_resumed_not_duplicated(self):
        payment = self.make_payment(self.order, status=S.AUTHORIZED, gateway_order_id="order_EXISTING1")
        result = self.pay()
        self.assertFalse(result.created)
        self.assertEqual(result.intent.razorpay_order_id, "order_EXISTING1")
        self.assertEqual(result.intent.amount_paise, 40621)
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(len(self.payments()), 1)
        self.assertEqual(self.payments()[0].id, payment.id)

    def test_different_orders_get_different_razorpay_orders(self):
        other = self.make_order(self.user, [(self.product, 1)])
        a, b = self.pay(), self.pay(other)
        self.assertNotEqual(a.intent.razorpay_order_id, b.intent.razorpay_order_id)
        self.assertEqual(len(self.gateway.calls), 2)

    def test_the_insert_backstop_returns_the_winners_payment(self):
        """If the order lock somehow let two requests through, the unique
        index refuses the second insert and it answers with the first's."""
        winner = self.make_payment(self.order, gateway_order_id="order_WINNER01")
        real = PaymentRepository.get_open_for_order
        calls = {"n": 0}

        def stale_first_read(repo, order_id):
            calls["n"] += 1
            return None if calls["n"] == 1 else real(repo, order_id)

        with mock.patch.object(PaymentRepository, "get_open_for_order", stale_first_read):
            result = self.pay()
        self.assertFalse(result.created)
        self.assertEqual(result.intent.razorpay_order_id, "order_WINNER01")
        self.assertEqual([p.id for p in self.payments()], [winner.id])

    def test_an_integrity_error_with_no_winner_is_not_swallowed(self):
        from sqlalchemy.exc import IntegrityError

        with mock.patch.object(PaymentRepository, "add", side_effect=IntegrityError("x", {}, Exception("boom"))):
            with self.assertRaises(IntegrityError):
                self.pay()
        self.assertEqual(self.payments(), [])


class RetryTests(PaymentServiceTestCase):
    def test_after_a_failed_attempt_a_new_razorpay_order_is_created_for_the_same_order(self):
        failed = self.make_payment(self.order, status=S.FAILED, gateway_order_id="order_FAILED001", failure_reason="declined")
        result = self.pay()
        self.assertTrue(result.created)
        self.assertNotEqual(result.intent.razorpay_order_id, "order_FAILED001")
        rows = self.payments()
        self.assertEqual(len(rows), 2)
        self.assertEqual({p.id: p.status for p in rows}[failed.id], S.FAILED)
        self.assertEqual(self.gateway.calls[0]["receipt"], f"{self.order.order_number}-2")

    def test_no_second_pramanika_order_is_created_by_a_retry(self):
        self.make_payment(self.order, status=S.FAILED)
        self.pay()
        with new_session() as s:
            self.assertEqual(s.query(Order).count(), 1)

    def test_an_order_payment_status_stays_pending_after_a_failed_attempt_so_a_retry_is_allowed(self):
        self.make_payment(self.order, status=S.FAILED)
        self.assertEqual(self.reload_order().payment_status, OrderPaymentStatus.PENDING)
        self.assertTrue(self.pay().created)

    def test_a_row_for_an_expired_attempt_does_not_block_a_new_one(self):
        self.make_payment(self.order, status=S.EXPIRED)
        self.assertTrue(self.pay().created)

    def test_receipts_stay_within_razorpays_limit(self):
        class O:
            def __init__(self, number):
                import uuid

                self.order_number, self.id = number, uuid.uuid4()

        for number in ("PRM-2026-000123", "X" * 30, "X" * 100, None):
            for attempt in (1, 9, 10, 12345):
                with self.subTest(number=number, attempt=attempt):
                    receipt = build_receipt(O(number), attempt)
                    self.assertLessEqual(len(receipt), 40)
                    self.assertTrue(receipt.endswith(f"-{attempt}"))
        self.assertEqual(build_receipt(O("PRM-2026-000123"), 2), "PRM-2026-000123-2")
        self.assertRegex(build_receipt(O(None), 1), re.compile(r"^[0-9a-f]{32}-1$"))


class FailureTests(PaymentServiceTestCase):
    def test_when_razorpay_fails_nothing_is_stored(self):
        gateway = FakeGateway(fail=True)
        with self.assertRaises(PaymentGatewayError) as ctx:
            self.pay(gateway=gateway)
        self.assertEqual(ctx.exception.http_status, 502)
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(self.payments(), [])
        after = self.reload_order()
        self.assertEqual((after.status, after.payment_status, after.inventory_state),
                         (OrderStatus.PENDING, OrderPaymentStatus.PENDING, OrderInventoryState.RESERVED))

    def test_the_customer_can_simply_try_again_after_a_gateway_failure(self):
        with self.assertRaises(PaymentGatewayError):
            self.pay(gateway=FakeGateway(fail=True))
        self.assertTrue(self.pay().created)

    def test_a_failure_releases_the_order_lock(self):
        with self.assertRaises(PaymentGatewayError):
            self.pay(gateway=FakeGateway(fail=True))
        with new_session() as s:  # would block (and the test hang) if the lock leaked
            s.execute(__import__("sqlalchemy").text("SET LOCAL lock_timeout = '1s'"))
            self.assertIsNotNone(s.query(Order).filter(Order.id == self.order.id).with_for_update().first())

    def test_a_database_failure_after_razorpay_accepted_stores_nothing_and_leaks_no_lock(self):
        with mock.patch.object(PaymentRepository, "add", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                self.pay()
        self.assertEqual(self.payments(), [])
        self.assertTrue(self.pay().created)  # a clean retry works


class ConcurrencyTests(PaymentServiceTestCase):
    def test_simultaneous_requests_for_one_order_create_exactly_one_razorpay_order(self):
        gateway = FakeGateway(delay=0.25)  # a slow gateway is what makes the race real
        user_id, order_id = self.user.id, self.order.id  # read ORM attributes before the threads start

        def job():
            with new_session() as s:
                return PaymentService(s, gateway).create_razorpay_order(user_id, order_id)

        results = run_concurrently([job] * 8)
        self.assertEqual([r[0] for r in results], ["ok"] * 8, results)
        intents = {r[1].intent.razorpay_order_id for r in results}
        self.assertEqual(len(intents), 1)
        self.assertEqual(sum(1 for r in results if r[1].created), 1)
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(len(self.payments()), 1)

    def test_simultaneous_requests_for_different_orders_each_get_their_own(self):
        order_ids = [self.make_order(self.user, [(self.product, 1)]).id for _ in range(4)]
        user_id = self.user.id
        gateway = FakeGateway(delay=0.1)

        def make_job(order_id):
            def job():
                with new_session() as s:
                    return PaymentService(s, gateway).create_razorpay_order(user_id, order_id)
            return job

        results = run_concurrently([make_job(i) for i in order_ids])
        self.assertEqual([r[0] for r in results], ["ok"] * 4, results)
        self.assertEqual(len({r[1].intent.razorpay_order_id for r in results}), 4)
        self.assertEqual(len(gateway.calls), 4)

    def test_paying_and_cancelling_at_the_same_time_neither_deadlocks_nor_corrupts_the_order(self):
        gateway = FakeGateway(delay=0.3)
        user_id, order_id = self.user.id, self.order.id

        def pay():
            with new_session() as s:
                return PaymentService(s, gateway).create_razorpay_order(user_id, order_id)

        def cancel():
            import time

            time.sleep(0.1)  # let the payment take the lock first
            with new_session() as s:
                return OrderService(s).cancel_order(user_id, order_id)

        results = run_concurrently([pay, cancel])
        self.assertEqual([r[0] for r in results], ["ok", "ok"], results)
        after = self.reload_order()
        self.assertEqual(after.status, OrderStatus.CANCELLED)
        self.assertEqual(after.inventory_state, OrderInventoryState.RELEASED)
        self.assertEqual(self.stock(self.product), (5, 0))  # the order's unit was released exactly once

    def test_a_cancel_that_wins_the_race_means_no_razorpay_order_at_all(self):
        gateway = FakeGateway()
        with new_session() as s:
            OrderService(s).cancel_order(self.user.id, self.order.id)
        with self.assertRaises(OrderNotPayableError):
            self.pay(gateway=gateway)
        self.assertEqual(gateway.calls, [])
        self.assertEqual(self.payments(), [])
