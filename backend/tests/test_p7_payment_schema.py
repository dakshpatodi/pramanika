"""Phase 7 / Milestone 2: the database itself refuses impossible payment and
order states (real PostgreSQL - these are CHECKs and partial unique indexes)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.models import (
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus as S,
    PaymentWebhookEvent,
)
from tests.pg_support import PostgresTestCase, new_session


class PaymentSchemaTestCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product()
        self.order = self.make_order(self.user, [(self.product, 1)])

    def assert_rejected(self, constraint: str, **values):
        """Inserting this payment must fail, naming `constraint`."""
        base = dict(
            order_id=self.order.id, payment_gateway="razorpay", gateway_order_id=f"order_X{id(values)}",
            amount=Decimal("10.00"), currency="INR", status=S.INITIATED,
        )
        base.update(values)
        with new_session() as s:
            s.add(Payment(**base))
            with self.assertRaises((IntegrityError, DataError)) as ctx:
                s.commit()
            self.assertIn(constraint, str(ctx.exception))


class PaymentConstraintTests(PaymentSchemaTestCase):
    def test_a_normal_pending_payment_is_accepted(self):
        payment = self.make_payment(self.order)
        self.assertEqual(payment.status, S.INITIATED)
        self.assertFalse(payment.refund_required)
        self.assertIsNone(payment.paid_at)

    def test_amount_must_be_positive(self):
        for bad in (Decimal("0"), Decimal("-1.00")):
            with self.subTest(amount=bad):
                self.assert_rejected("ck_payments_amount_positive", amount=bad)

    def test_money_keeps_exact_decimal_values(self):
        payment = self.make_payment(self.order, amount=Decimal("406.21"))
        with new_session() as s:
            stored = s.get(Payment, payment.id).amount
        self.assertEqual(stored, Decimal("406.21"))
        self.assertIsInstance(stored, Decimal)

    def test_currency_must_be_three_letters(self):
        self.assert_rejected("ck_payments_currency_three_letters", currency="RS")

    def test_a_razorpay_row_needs_a_razorpay_order_id(self):
        self.assert_rejected("ck_payments_razorpay_has_gateway_order_id", gateway_order_id=None)

    def test_other_gateways_may_omit_the_gateway_order_id(self):
        self.make_payment(self.order, payment_gateway="other", gateway_order_id=None)

    def test_captured_needs_paid_at_and_a_payment_id(self):
        self.assert_rejected(
            "ck_payments_paid_at_matches_status", status=S.CAPTURED, gateway_payment_id="pay_1", paid_at=None
        )
        self.assert_rejected(
            "ck_payments_paid_has_gateway_payment_id", status=S.CAPTURED, gateway_payment_id=None,
            paid_at=datetime.now(timezone.utc),
        )

    def test_refunded_is_a_paid_state_too(self):
        self.assert_rejected(
            "ck_payments_paid_at_matches_status", status=S.REFUNDED, gateway_payment_id="pay_2", paid_at=None
        )
        self.make_payment(self.order, status=S.REFUNDED)

    def test_paid_at_is_only_allowed_on_captured_or_refunded_rows(self):
        for status in (S.INITIATED, S.AUTHORIZED, S.FAILED, S.EXPIRED):
            with self.subTest(status=status):
                self.assert_rejected("ck_payments_paid_at_matches_status", status=status, paid_at=datetime.now(timezone.utc))

    def test_a_captured_payment_is_accepted(self):
        payment = self.make_payment(self.order, status=S.CAPTURED)
        self.assertIsNotNone(payment.paid_at)

    def test_refund_required_only_on_captured_rows(self):
        self.assert_rejected("ck_payments_refund_required_only_when_captured", status=S.FAILED, refund_required=True)
        self.assert_rejected(
            "ck_payments_refund_required_only_when_captured", status=S.REFUNDED, refund_required=True,
            gateway_payment_id="pay_3", paid_at=datetime.now(timezone.utc),
        )
        payment = self.make_payment(self.order, status=S.CAPTURED, refund_required=True)
        self.assertTrue(payment.refund_required)

    def test_the_expired_status_exists(self):
        payment = self.make_payment(self.order, status=S.EXPIRED)
        self.assertEqual(payment.status, S.EXPIRED)
        with new_session() as s:
            labels = [r[0] for r in s.execute(text(
                "select e.enumlabel from pg_enum e join pg_type t on t.oid = e.enumtypid "
                "where t.typname = 'payment_transaction_status'"))]
        self.assertEqual(set(labels), {"initiated", "authorized", "captured", "failed", "refunded", "expired"})


class PaymentUniquenessTests(PaymentSchemaTestCase):
    def test_a_razorpay_order_id_can_only_be_used_once(self):
        self.make_payment(self.order, gateway_order_id="order_dup", status=S.FAILED)
        other = self.make_order(self.user, [(self.product, 1)])
        self.assert_rejected("uq_payments_gateway_order_id", order_id=other.id, gateway_order_id="order_dup")

    def test_a_razorpay_payment_id_can_only_be_used_once(self):
        self.make_payment(self.order, status=S.CAPTURED, gateway_payment_id="pay_dup")
        other = self.make_order(self.user, [(self.product, 1)])
        self.assert_rejected(
            "uq_payments_gateway_payment_id", order_id=other.id, status=S.CAPTURED, gateway_payment_id="pay_dup",
            paid_at=datetime.now(timezone.utc),
        )

    def test_many_rows_without_a_payment_id_are_fine(self):
        for _ in range(3):
            self.make_payment(self.order, status=S.FAILED)

    def test_only_one_open_payment_per_order(self):
        self.make_payment(self.order, status=S.INITIATED)
        self.assert_rejected("uq_payments_one_open_per_order", status=S.INITIATED)
        self.assert_rejected("uq_payments_one_open_per_order", status=S.AUTHORIZED, gateway_payment_id="pay_a")

    def test_a_new_attempt_is_allowed_once_the_old_one_is_closed(self):
        for closed in (S.FAILED, S.EXPIRED, S.CAPTURED):
            order = self.make_order(self.user, [(self.product, 1)])
            self.make_payment(order, status=closed)
            self.make_payment(order, status=S.INITIATED)

    def test_two_orders_can_each_have_an_open_payment(self):
        other = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(self.order)
        self.make_payment(other)

    def test_a_second_captured_payment_can_still_be_recorded(self):
        """Paying twice must not lose the second payment's record."""
        self.make_payment(self.order, status=S.CAPTURED)
        second = self.make_payment(self.order, status=S.CAPTURED, refund_required=True)
        self.assertTrue(second.refund_required)

    def test_concurrent_creation_of_open_payments_lets_exactly_one_in(self):
        from tests.pg_support import run_concurrently

        order_id = self.order.id  # read once, here: threads must not touch the shared session

        def attempt(n):
            def job():
                with new_session() as s:
                    s.add(Payment(order_id=order_id, payment_gateway="razorpay", gateway_order_id=f"order_race{n}",
                                  amount=Decimal("10.00"), currency="INR", status=S.INITIATED))
                    s.commit()
            return job

        results = run_concurrently([attempt(i) for i in range(8)])
        self.assertEqual([r[0] for r in results].count("ok"), 1)
        for kind, value in results:
            if kind == "err":
                self.assertIsInstance(value, IntegrityError)
        with new_session() as s:
            self.assertEqual(s.query(Payment).filter(Payment.order_id == order_id).count(), 1)

    def test_deleting_an_order_removes_its_payments(self):
        payment_id, order_id = self.make_payment(self.order).id, self.order.id
        with new_session() as s:
            s.execute(text("delete from orders where id = :id"), {"id": order_id})
            s.commit()
            self.assertIsNone(s.get(Payment, payment_id))


class WebhookEventTests(PostgresTestCase):
    def test_an_event_id_can_only_be_recorded_once(self):
        with new_session() as s:
            s.add(PaymentWebhookEvent(event_id="evt_1", event_type="payment.captured"))
            s.commit()
        with new_session() as s:
            s.add(PaymentWebhookEvent(event_id="evt_1", event_type="payment.captured"))
            with self.assertRaises(IntegrityError) as ctx:
                s.commit()
            self.assertIn("uq_payment_webhook_events_event_id", str(ctx.exception))

    def test_defaults_and_nullable_references(self):
        with new_session() as s:
            s.add(PaymentWebhookEvent(event_id="evt_2", event_type="order.paid"))
            s.commit()
            row = s.query(PaymentWebhookEvent).filter_by(event_id="evt_2").one()
            self.assertEqual(row.outcome, "received")
            self.assertIsNone(row.gateway_order_id)
            self.assertIsNotNone(row.received_at)

    def test_it_has_no_column_that_could_hold_a_payload(self):
        with new_session() as s:
            cols = {r[0] for r in s.execute(text(
                "select column_name from information_schema.columns where table_name = 'payment_webhook_events'"))}
        self.assertEqual(
            cols, {"id", "event_id", "event_type", "gateway_order_id", "gateway_payment_id", "outcome", "received_at"}
        )


class OrderExpiryColumnTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product()

    def test_a_cancelled_order_must_have_a_reason(self):
        with new_session() as s:
            s.execute(text("update orders set id = id where false"))  # session sanity
        order = self.make_order(self.user, [(self.product, 1)])
        with new_session() as s:
            with self.assertRaises(IntegrityError) as ctx:
                s.execute(text("update orders set status = 'cancelled' where id = :id"), {"id": order.id})
                s.commit()
            self.assertIn("ck_orders_cancellation_reason_matches_status", str(ctx.exception))

    def test_a_reason_is_only_allowed_on_a_cancelled_order(self):
        order = self.make_order(self.user, [(self.product, 1)])
        with new_session() as s:
            with self.assertRaises(IntegrityError) as ctx:
                s.execute(text("update orders set cancellation_reason = 'expired' where id = :id"), {"id": order.id})
                s.commit()
            self.assertIn("ck_orders_cancellation_reason_matches_status", str(ctx.exception))

    def test_both_reasons_are_accepted_on_cancelled_orders(self):
        for reason in OrderCancellationReason:
            with self.subTest(reason=reason):
                order = self.make_order(
                    self.user, [(self.product, 1)], status=OrderStatus.CANCELLED,
                    inventory_state=OrderInventoryState.RELEASED, cancellation_reason=reason, reserve_stock=False,
                )
                with new_session() as s:
                    from app.models import Order
                    self.assertEqual(s.get(Order, order.id).cancellation_reason, reason)

    def test_expires_at_round_trips_and_is_optional(self):
        deadline = datetime.now(timezone.utc) + timedelta(minutes=30)
        with_deadline = self.make_order(self.user, [(self.product, 1)], expires_at=deadline)
        without = self.make_order(self.user, [(self.product, 1)])
        from app.models import Order
        with new_session() as s:
            self.assertEqual(s.get(Order, with_deadline.id).expires_at, deadline)
            self.assertIsNone(s.get(Order, without.id).expires_at)

    def test_the_expiry_sweep_index_covers_only_open_unpaid_reserved_orders(self):
        with new_session() as s:
            definition = s.execute(text(
                "select indexdef from pg_indexes where indexname = 'ix_orders_open_expires_at'")).scalar_one()
        self.assertIn("expires_at", definition)
        for part in ("pending", "reserved"):
            self.assertIn(part, definition)
