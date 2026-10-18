"""
Phase 7 / Milestone 8: unpaid orders expire (real PostgreSQL, real threads).

Groups:
  ExpireTests          what expiring one order does, and what it must never touch
  PaymentInteraction   payments that are open, failed, captured; money arriving after expiry
  PassTests            batches, ordering, draining, failures, busy orders
  AtomicityTests       a failure half-way leaves the order exactly as it was
  ConcurrencyTests     many workers, and expiry racing cancel / verify / webhook
  JobTests             command line, background loop, lifespan, configuration
"""

import asyncio
import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from app.core.exceptions import LatePaymentError, OrderNotCancellableError, OrderNotPayableError
from app.models import (
    Coupon,
    Inventory,
    Order,
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus as S,
)
from app.repositories.order_expiry_repository import OrderExpiryRepository
from app.services.order_expiry_service import ExpireOutcome, ExpiryRun, OrderExpiryService, run_expiry_pass
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.payment_state import REASON_ORDER_EXPIRED
from app.services.payment_webhook_service import PaymentWebhookService, WebhookOutcome
from app.services.razorpay_signature import webhook_signature
from tests.payment_fakes import FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session, run_concurrently

NOW = datetime.now(timezone.utc).replace(microsecond=0)  # real time, so the command line (real clock) sees the same deadlines
MINUTE = timedelta(minutes=1)
SECRET = "whsec-expiry-test"


def clock():
    return NOW


class ExpiryCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.coupon = self.make_coupon(usage_limit=10, used_count=1)
        self.user_id = self.user.id
        self.order = self.make_due_order()  # stock (5, 1), coupon used once

    def make_due_order(self, *, product=None, qty=1, due=True, coupon=True, **kwargs):
        expires = kwargs.pop("expires_at", NOW - 5 * MINUTE if due else NOW + 5 * MINUTE)
        return self.make_order(self.user, [(product or self.product, qty)], coupon=self.coupon if coupon else None,
                               expires_at=expires, **kwargs)

    # --- act ---

    def expire(self, **kwargs):
        return run_expiry_pass(new_session, clock=clock, **kwargs)

    def expire_one(self, order=None):
        with new_session() as s:
            return OrderExpiryService(s, clock=clock).expire_order((order or self.order).id)

    # --- read ---

    def order_row(self, order=None) -> Order:
        with new_session() as s:
            row = s.get(Order, (order or self.order).id)
            s.expunge(row)
            return row

    def payment_rows(self, order=None):
        with new_session() as s:
            rows = s.query(Payment).filter(Payment.order_id == (order or self.order).id).order_by(Payment.created_at).all()
            for r in rows:
                s.expunge(r)
            return rows

    def snapshot(self, order=None):
        o = self.order_row(order)
        return ((o.status, o.payment_status, o.inventory_state, o.cancellation_reason, o.cancelled_at),
                [(p.status, p.failure_reason, p.refund_required) for p in self.payment_rows(order)],
                self.stock(self.product), self.used_count(self.coupon))

    def order_state(self, order=None):
        """This order and its payments only (stock and coupon are shared with other orders)."""
        o = self.order_row(order)
        return ((o.status, o.payment_status, o.inventory_state, o.cancellation_reason, o.cancelled_at),
                [(p.status, p.failure_reason, p.refund_required) for p in self.payment_rows(order)])

    def assert_expired(self, order=None):
        o = self.order_row(order)
        self.assertEqual((o.status, o.cancellation_reason, o.inventory_state),
                         (OrderStatus.CANCELLED, OrderCancellationReason.EXPIRED, OrderInventoryState.RELEASED))
        self.assertEqual(o.payment_status, OrderPaymentStatus.PENDING)  # nothing was paid
        self.assertEqual(o.cancelled_at, NOW)


class ExpireTests(ExpiryCase):
    def test_an_order_past_its_deadline_expires_and_gives_everything_back(self):
        self.assertEqual(self.stock(self.product), (5, 1))
        run = self.expire()
        self.assertEqual((run.expired, run.failed), (1, 0))
        self.assert_expired()
        self.assertEqual(self.stock(self.product), (5, 0))          # the unit is available again
        self.assertEqual(self.used_count(self.coupon), 0)           # the coupon use is back

    def test_the_reason_is_expired_not_customer_so_the_ui_can_say_so(self):
        self.expire()
        self.assertEqual(self.order_row().cancellation_reason, OrderCancellationReason.EXPIRED)

    def test_every_line_is_released(self):
        other = self.make_product(price="100.00", stock=10)
        order = self.make_due_order(product=other, qty=3, coupon=False)
        self.expire()
        self.assertEqual(self.stock(other), (10, 0))
        self.assert_expired(order)

    def test_a_order_with_two_lines_releases_both(self):
        other = self.make_product(price="100.00", stock=10)
        order = self.make_order(self.user, [(self.product, 2), (other, 3)], expires_at=NOW - MINUTE)
        self.assertEqual(self.stock(self.product), (5, 3))   # the setUp order's 1 + this order's 2
        self.expire()
        self.assertEqual(self.stock(self.product), (5, 0))
        self.assertEqual(self.stock(other), (10, 0))
        self.assert_expired(order)

    def test_an_order_whose_deadline_is_in_the_future_is_left_alone(self):
        future = self.make_due_order(due=False)
        before = self.order_state(future)
        self.expire()
        self.assertEqual(self.order_state(future), before)
        self.assertEqual(self.order_row(future).status, OrderStatus.PENDING)

    def test_the_deadline_itself_counts_as_due(self):
        order = self.make_due_order(expires_at=NOW)
        self.expire()
        self.assert_expired(order)

    def test_one_second_before_the_deadline_is_not_due(self):
        order = self.make_due_order(expires_at=NOW + timedelta(seconds=1))
        self.expire()
        self.assertEqual(self.order_row(order).status, OrderStatus.PENDING)

    def test_an_order_with_no_deadline_never_expires(self):
        order = self.make_order(self.user, [(self.product, 1)], expires_at=None)
        self.expire()
        self.assertEqual(self.order_row(order).status, OrderStatus.PENDING)

    def test_a_paid_order_is_never_expired_however_late(self):
        order = self.make_due_order(status=OrderStatus.CONFIRMED, payment_status=OrderPaymentStatus.PAID,
                                    inventory_state=OrderInventoryState.CONSUMED, coupon=False)
        before = self.order_state(order)
        run = self.expire()
        self.assertEqual(self.order_state(order), before)
        self.assertEqual(run.expired, 1)  # only the setUp order

    def test_a_customer_cancelled_order_is_not_touched_again(self):
        with new_session() as s:
            OrderService(s).cancel_order(self.user_id, self.order.id)
        before = self.snapshot()
        run = self.expire()
        self.assertEqual((run.expired, run.batches), (0, 0))   # not even a candidate
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.order_row().cancellation_reason, OrderCancellationReason.CUSTOMER)

    def test_running_it_again_changes_nothing(self):
        self.expire()
        after = self.snapshot()
        for _ in range(3):
            self.assertEqual(self.expire().expired, 0)
        self.assertEqual(self.snapshot(), after)

    def test_expire_order_twice_the_second_is_not_due_and_releases_nothing(self):
        self.assertIs(self.expire_one(), ExpireOutcome.EXPIRED)
        after = self.snapshot()
        self.assertIs(self.expire_one(), ExpireOutcome.NOT_DUE)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.stock(self.product), (5, 0))
        self.assertEqual(self.used_count(self.coupon), 0)

    def test_an_unknown_order_is_just_busy_not_an_error(self):
        import uuid

        with new_session() as s:
            self.assertIs(OrderExpiryService(s, clock=clock).expire_order(uuid.uuid4()), ExpireOutcome.BUSY)

    def test_the_customer_cancelling_an_expired_order_later_changes_nothing(self):
        self.expire()
        after = self.snapshot()
        with new_session() as s:
            result = OrderService(s).cancel_order(self.user_id, self.order.id)
        self.assertEqual(result.status.value if hasattr(result.status, "value") else result.status, "cancelled")
        self.assertEqual(self.snapshot(), after)  # stock not released twice, coupon not restored twice

    def test_the_customer_cancelling_an_unexpired_but_due_order_is_a_normal_cancel(self):
        """Past its deadline but the job has not run: the customer's cancel still works, reason customer."""
        with new_session() as s:
            OrderService(s).cancel_order(self.user_id, self.order.id)
        o = self.order_row()
        self.assertEqual(o.cancellation_reason, OrderCancellationReason.CUSTOMER)
        self.assertEqual(self.stock(self.product), (5, 0))
        self.expire()
        self.assertEqual(self.stock(self.product), (5, 0))
        self.assertEqual(self.used_count(self.coupon), 0)

    def test_the_gate_checks_every_condition_on_its_own(self):
        """expire_pending must refuse each wrong state by itself (a stale read cannot expire a live order)."""
        cases = {
            "paid": dict(payment_status=OrderPaymentStatus.PAID),
            "confirmed": dict(status=OrderStatus.CONFIRMED),
            "released": dict(inventory_state=OrderInventoryState.RELEASED),
            "consumed": dict(inventory_state=OrderInventoryState.CONSUMED),
            "future": dict(expires_at=NOW + MINUTE),
            "no deadline": dict(expires_at=None),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                order = self.make_due_order(coupon=False, reserve_stock=False)
                with new_session() as s:
                    s.query(Order).filter(Order.id == order.id).update(change)
                    s.commit()
                with new_session() as s:
                    self.assertFalse(OrderExpiryRepository(s).expire_pending(order.id, NOW))
                    s.rollback()
        with new_session() as s:  # and the one right state does
            order = self.make_due_order(coupon=False, reserve_stock=False)
            self.assertTrue(OrderExpiryRepository(s).expire_pending(order.id, NOW))
            s.rollback()


class PaymentInteraction(ExpiryCase):
    def test_an_open_payment_attempt_is_closed_with_a_reason(self):
        payment = self.make_payment(self.order, gateway_order_id="order_EXP1")
        self.expire()
        (p,) = self.payment_rows()
        self.assertEqual((p.id, p.status, p.failure_reason, p.paid_at, p.refund_required),
                         (payment.id, S.EXPIRED, REASON_ORDER_EXPIRED, None, False))

    def test_an_authorized_payment_is_closed_too(self):
        self.make_payment(self.order, gateway_order_id="order_EXP2", status=S.AUTHORIZED)
        self.expire()
        self.assertEqual(self.payment_rows()[0].status, S.EXPIRED)

    def test_failed_payments_stay_failed_and_the_order_still_expires(self):
        self.make_payment(self.order, gateway_order_id="order_F1", status=S.FAILED, failure_reason="declined")
        self.expire()
        self.assertEqual([(p.status, p.failure_reason) for p in self.payment_rows()], [(S.FAILED, "declined")])
        self.assert_expired()

    def test_an_order_with_no_payment_attempt_expires_fine(self):
        self.expire()
        self.assert_expired()

    def test_an_expired_order_cannot_start_a_new_payment(self):
        self.expire()
        with new_session() as s, self.assertRaises(OrderNotPayableError) as ctx:
            PaymentService(s, FakeGateway()).create_razorpay_order(self.user_id, self.order.id)
        self.assertIn("expired", ctx.exception.message.lower())

    def test_money_arriving_by_webhook_after_expiry_is_recorded_and_flagged_not_applied(self):
        self.make_payment(self.order, gateway_order_id="order_LATE", amount=self.order.total_amount)
        self.expire()
        raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_LATE", "order_id": "order_LATE", "amount": 40621, "currency": "INR"}}}}).encode()
        with new_session() as s:
            outcome = PaymentWebhookService(s, SECRET).handle(raw, webhook_signature(SECRET, raw), "evt_late")
        self.assertIs(outcome, WebhookOutcome.LATE_PAYMENT)
        p = self.payment_rows()[0]
        self.assertEqual((p.status, p.refund_required), (S.CAPTURED, True))
        self.assert_expired()
        self.assertEqual(self.stock(self.product), (5, 0))  # not sold, not re-reserved
        self.assertEqual(self.used_count(self.coupon), 0)

    def test_money_arriving_by_browser_verify_after_expiry_is_a_late_payment(self):
        self.make_payment(self.order, gateway_order_id="order_LATE2", amount=self.order.total_amount)
        self.expire()
        gateway = FakeGateway()
        gateway.register_payment("pay_LATE2", order_id="order_LATE2", amount_paise=40621)
        with new_session() as s, self.assertRaises(LatePaymentError):
            PaymentService(s, gateway).verify_payment(self.user_id, self.order.id, razorpay_order_id="order_LATE2",
                                                      razorpay_payment_id="pay_LATE2", razorpay_signature=sign("order_LATE2", "pay_LATE2"))
        self.assertEqual(self.payment_rows()[0].refund_required, True)
        self.assert_expired()

    def test_an_expired_order_can_never_become_paid_by_any_route(self):
        self.expire()
        with new_session() as s:
            from app.repositories.order_repository import OrderRepository

            self.assertFalse(OrderRepository(s).mark_paid(self.order.id))
            s.rollback()
        self.assert_expired()


class PassTests(ExpiryCase):
    def test_it_drains_a_backlog_in_batches_oldest_first(self):
        big = self.make_product(price="10.00", stock=100)
        orders = [self.make_due_order(product=big, coupon=False, expires_at=NOW - (10 + i) * MINUTE) for i in range(6)]
        run = self.expire(batch_size=2)
        self.assertEqual(run.expired, 7)   # six here + the setUp order
        self.assertGreaterEqual(run.batches, 3)
        for o in orders:
            self.assert_expired(o)
        self.assertEqual(self.stock(big), (100, 0))

    def test_the_oldest_deadline_is_listed_first(self):
        oldest = self.make_due_order(coupon=False, expires_at=NOW - 60 * MINUTE)
        middle = self.make_due_order(coupon=False, expires_at=NOW - 30 * MINUTE)
        with new_session() as s:
            ids = OrderExpiryRepository(s).list_due_ids(NOW, 10)
        self.assertEqual(ids[:2], [oldest.id, middle.id])
        with new_session() as s:
            self.assertEqual(len(OrderExpiryRepository(s).list_due_ids(NOW, 2)), 2)  # the limit is honoured

    def test_the_batch_cap_stops_a_pass_from_looping_forever(self):
        big = self.make_product(price="10.00", stock=100)
        for _ in range(5):
            self.make_due_order(product=big, coupon=False)
        run = self.expire(batch_size=1, max_batches=2)
        self.assertEqual((run.batches, run.expired), (2, 2))
        self.assertEqual(self.expire().expired, 4)  # the rest on the next pass

    def test_a_bad_batch_size_is_refused(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                self.expire(batch_size=bad)

    def test_one_failing_order_does_not_stop_the_others(self):
        good = self.make_due_order(coupon=False, expires_at=NOW - 20 * MINUTE)
        real = OrderExpiryService._expire
        bad_id = self.order.id

        def flaky(service, order_id):
            if order_id == bad_id:
                raise RuntimeError("boom")
            return real(service, order_id)

        with mock.patch.object(OrderExpiryService, "_expire", flaky):
            run = self.expire()
        self.assertEqual((run.expired, run.failed), (1, 1))
        self.assert_expired(good)
        self.assertEqual(self.order_row().status, OrderStatus.PENDING)  # retried on the next pass
        self.assertEqual(self.expire().expired, 1)
        self.assert_expired()

    def test_a_pass_where_nothing_can_progress_ends_instead_of_spinning(self):
        holder = new_session()
        holder.query(Order).filter(Order.id == self.order.id).with_for_update().one()
        try:
            started = time.time()
            run = self.expire(batch_size=1)
            self.assertLess(time.time() - started, 5)
            self.assertEqual((run.expired, run.busy), (0, 1))
        finally:
            holder.rollback()
            holder.close()

    def test_a_busy_order_is_skipped_not_waited_for_and_expires_on_the_next_pass(self):
        holder = new_session()
        holder.query(Order).filter(Order.id == self.order.id).with_for_update().one()  # e.g. a verification in flight
        try:
            self.assertIs(self.expire_one(), ExpireOutcome.BUSY)
            self.assertEqual(self.order_row().status, OrderStatus.PENDING)
        finally:
            holder.rollback()
            holder.close()
        self.assertEqual(self.expire().expired, 1)
        self.assert_expired()

    def test_the_run_totals_add_up(self):
        a, b = ExpiryRun(expired=1, busy=2, not_due=3, failed=4, batches=5), ExpiryRun(expired=1, batches=1)
        a += b
        self.assertEqual((a.expired, a.busy, a.not_due, a.failed, a.batches), (2, 2, 3, 4, 6))


class AtomicityTests(ExpiryCase):
    def test_a_failure_releasing_stock_leaves_the_order_exactly_as_it_was(self):
        self.make_payment(self.order, gateway_order_id="order_ATOM")
        before = self.snapshot()
        with mock.patch("app.services.reservation_service.ReservationService.release_items", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                self.expire_one()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.order_row().status, OrderStatus.PENDING)
        self.assertEqual(self.payment_rows()[0].status, S.INITIATED)
        self.assertEqual(self.used_count(self.coupon), 1)
        self.assertIs(self.expire_one(), ExpireOutcome.EXPIRED)  # and the retry works
        self.assert_expired()

    def test_after_a_failure_the_same_session_cannot_commit_the_half_done_work(self):
        with new_session() as s:
            service = OrderExpiryService(s, clock=clock)
            with mock.patch("app.services.reservation_service.ReservationService.release_items", side_effect=RuntimeError("x")):
                with self.assertRaises(RuntimeError):
                    service.expire_order(self.order.id)
            s.commit()  # whatever the caller does next must not persist the order change
        self.assertEqual(self.order_row().status, OrderStatus.PENDING)

    def test_a_failure_restoring_the_coupon_undoes_the_order_and_payment_changes(self):
        self.make_payment(self.order, gateway_order_id="order_ATOM2")
        before = self.snapshot()
        with mock.patch("app.services.coupon_usage.CouponUsageService.restore", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                self.expire_one()
        self.assertEqual(self.snapshot(), before)

    def test_a_failure_closing_the_payment_undoes_the_order_change(self):
        self.make_payment(self.order, gateway_order_id="order_ATOM3")
        before = self.snapshot()
        with mock.patch("app.services.order_expiry_service.close_open_payments", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                self.expire_one()
        self.assertEqual(self.snapshot(), before)

    def test_the_stock_books_must_balance_or_the_expiry_is_rolled_back(self):
        with new_session() as s:  # someone corrupted the reservation: nothing reserved
            s.query(Inventory).filter(Inventory.product_id == self.product.id).update({Inventory.reserved_quantity: 0})
            s.commit()
        before = self.snapshot()
        with self.assertRaises(Exception):
            self.expire_one()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.order_row().status, OrderStatus.PENDING)


class ConcurrencyTests(ExpiryCase):
    def test_many_workers_expire_each_order_exactly_once(self):
        big = self.make_product(price="10.00", stock=50)
        for _ in range(11):
            self.make_due_order(product=big, coupon=True)
        with new_session() as s:
            s.query(Coupon).filter(Coupon.id == self.coupon.id).update({Coupon.used_count: 12, Coupon.usage_limit: 50})  # 12 orders use it
            s.commit()

        def worker():
            return run_expiry_pass(new_session, clock=clock, batch_size=3)

        results = run_concurrently([worker] * 5)
        self.assertEqual([k for k, _ in results], ["ok"] * 5, results)
        self.assertEqual(sum(r.failed for _, r in results), 0)
        self.assertEqual(sum(r.expired for _, r in results), 12)   # every order once, none twice
        self.assertEqual(self.stock(big), (50, 0))
        self.assertEqual(self.stock(self.product), (5, 0))
        self.assertEqual(self.used_count(self.coupon), 0)
        with new_session() as s:
            self.assertEqual(s.query(Order).filter(Order.status == OrderStatus.CANCELLED).count(), 12)

    def test_expiry_racing_a_customer_cancel_releases_exactly_once(self):
        user_id = self.user_id
        for round_ in range(6):
            with self.subTest(round=round_):
                order = self.make_due_order()
                order_id = order.id
                with new_session() as s:
                    s.query(Coupon).filter(Coupon.id == self.coupon.id).update({Coupon.used_count: 1})
                    s.query(Inventory).filter(Inventory.product_id == self.product.id).update(
                        {Inventory.quantity: 5, Inventory.reserved_quantity: 1})
                    s.query(Order).filter(Order.id != order_id).update({Order.expires_at: NOW + 60 * MINUTE})
                    s.commit()

                def cancel():
                    try:
                        with new_session() as s:
                            OrderService(s).cancel_order(user_id, order_id)
                        return "cancelled"
                    except OrderNotCancellableError:
                        return "refused"

                results = run_concurrently([cancel, lambda: run_expiry_pass(new_session, clock=clock)])
                self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
                o = self.order_row(order)
                self.assertEqual((o.status, o.inventory_state), (OrderStatus.CANCELLED, OrderInventoryState.RELEASED))
                self.assertIn(o.cancellation_reason, (OrderCancellationReason.CUSTOMER, OrderCancellationReason.EXPIRED))
                self.assertEqual(self.stock(self.product), (5, 0))          # released once
                self.assertEqual(self.used_count(self.coupon), 0)           # restored once

    def test_expiry_racing_a_webhook_capture_one_wins_and_money_is_never_lost(self):
        raw_for = lambda rz, pid: json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": pid, "order_id": rz, "amount": 40621, "currency": "INR"}}}}).encode()
        for round_ in range(6):
            with self.subTest(round=round_):
                with new_session() as s:
                    s.query(Order).update({Order.expires_at: NOW + 60 * MINUTE})
                    s.query(Coupon).filter(Coupon.id == self.coupon.id).update({Coupon.used_count: 1})
                    s.query(Inventory).filter(Inventory.product_id == self.product.id).update(
                        {Inventory.quantity: 5, Inventory.reserved_quantity: 0})
                    s.commit()
                order = self.make_due_order()  # reserves 1
                rz, pid = f"order_RACE{round_}", f"pay_RACE{round_}"
                payment = self.make_payment(order, gateway_order_id=rz, amount=order.total_amount)
                raw = raw_for(rz, pid)

                def webhook():
                    with new_session() as s:
                        return PaymentWebhookService(s, SECRET).handle(raw, webhook_signature(SECRET, raw), f"evt_{round_}")

                results = run_concurrently([webhook, lambda: run_expiry_pass(new_session, clock=clock)])
                self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
                o, p = self.order_row(order), self.payment_rows(order)[0]
                self.assertEqual(p.status, S.CAPTURED)  # the money is on record either way
                if o.payment_status == OrderPaymentStatus.PAID:
                    self.assertEqual((o.status, o.inventory_state), (OrderStatus.CONFIRMED, OrderInventoryState.CONSUMED))
                    self.assertFalse(p.refund_required)
                    self.assertEqual(self.stock(self.product), (4, 0))
                    self.assertEqual(self.used_count(self.coupon), 1)
                else:
                    self.assertEqual((o.status, o.cancellation_reason), (OrderStatus.CANCELLED, OrderCancellationReason.EXPIRED))
                    self.assertTrue(p.refund_required)
                    self.assertEqual(self.stock(self.product), (5, 0))
                    self.assertEqual(self.used_count(self.coupon), 0)

    def test_expiry_racing_a_browser_verify_one_wins_and_money_is_never_lost(self):
        for round_ in range(5):
            with self.subTest(round=round_):
                with new_session() as s:
                    s.query(Order).update({Order.expires_at: NOW + 60 * MINUTE})
                    s.query(Coupon).filter(Coupon.id == self.coupon.id).update({Coupon.used_count: 1})
                    s.query(Inventory).filter(Inventory.product_id == self.product.id).update(
                        {Inventory.quantity: 5, Inventory.reserved_quantity: 0})
                    s.commit()
                order = self.make_due_order()
                rz, pid = f"order_VRACE{round_}", f"pay_VRACE{round_}"
                self.make_payment(order, gateway_order_id=rz, amount=order.total_amount)
                gateway = FakeGateway()
                gateway.register_payment(pid, order_id=rz, amount_paise=40621)
                order_id, user_id = order.id, self.user_id

                def verify():
                    try:
                        with new_session() as s:
                            return PaymentService(s, gateway).verify_payment(
                                user_id, order_id, razorpay_order_id=rz, razorpay_payment_id=pid,
                                razorpay_signature=sign(rz, pid)).outcome.value
                    except LatePaymentError:
                        return "late"

                results = run_concurrently([verify, lambda: run_expiry_pass(new_session, clock=clock)])
                self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
                o, p = self.order_row(order), self.payment_rows(order)[0]
                self.assertEqual(p.status, S.CAPTURED)
                if o.payment_status == OrderPaymentStatus.PAID:
                    self.assertEqual(results[0][1], "paid")
                    self.assertEqual(self.stock(self.product), (4, 0))
                else:
                    self.assertEqual((results[0][1], p.refund_required, o.cancellation_reason),
                                     ("late", True, OrderCancellationReason.EXPIRED))
                    self.assertEqual(self.stock(self.product), (5, 0))

    def test_an_order_being_verified_is_skipped_so_it_can_still_be_paid(self):
        """verify holds the order lock while it asks Razorpay; expiry must not slip in."""
        gateway = FakeGateway(delay=1.0)
        self.make_payment(self.order, gateway_order_id="order_SLOW", amount=self.order.total_amount)
        gateway.register_payment("pay_SLOW", order_id="order_SLOW", amount_paise=40621)
        order_id, user_id = self.order.id, self.user_id
        outcome = {}

        def verify():
            with new_session() as s:
                outcome["verify"] = PaymentService(s, gateway).verify_payment(
                    user_id, order_id, razorpay_order_id="order_SLOW", razorpay_payment_id="pay_SLOW",
                    razorpay_signature=sign("order_SLOW", "pay_SLOW")).outcome.value

        thread = threading.Thread(target=verify, daemon=True)
        thread.start()
        time.sleep(0.4)  # verify now holds the lock, waiting on 'Razorpay'
        run = self.expire()
        thread.join(30)
        self.assertEqual((run.expired, run.busy), (0, 1))
        self.assertEqual(outcome["verify"], "paid")
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status), (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID))


class JobTests(ExpiryCase):
    def test_the_command_line_runs_one_pass_and_reports(self):
        from app.jobs import expire_orders

        out = io.StringIO()
        with mock.patch.object(expire_orders, "SessionLocal", new_session), redirect_stdout(out):
            code = expire_orders.main(["--batch-size", "10"])
        self.assertEqual(code, 0)
        self.assertIn("expired=1", out.getvalue())
        self.assertEqual(self.order_row().status, OrderStatus.CANCELLED)

    def test_the_command_line_exits_1_when_an_order_failed(self):
        from app.jobs import expire_orders

        out = io.StringIO()
        with mock.patch.object(expire_orders, "SessionLocal", new_session), redirect_stdout(out), \
                mock.patch.object(OrderExpiryService, "_expire", side_effect=RuntimeError("x")):
            self.assertEqual(expire_orders.main([]), 1)
        self.assertIn("failed=1", out.getvalue())

    def test_the_command_line_loop_keeps_going_until_interrupted(self):
        from app.jobs import expire_orders

        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise KeyboardInterrupt

        out = io.StringIO()
        with mock.patch.object(expire_orders, "SessionLocal", new_session), redirect_stdout(out), \
                mock.patch.object(expire_orders.time, "sleep", fake_sleep):
            self.assertEqual(expire_orders.main(["--loop", "--interval", "7"]), 0)
        self.assertEqual(sleeps, [7, 7])
        self.assertEqual(out.getvalue().count("expired="), 2)
        self.assertIn("stopped", out.getvalue())

    def test_the_command_line_refuses_nonsense_arguments(self):
        from app.jobs import expire_orders

        for argv in (["--batch-size", "0"], ["--interval", "0"], ["--batch-size", "x"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), \
                    mock.patch("sys.stderr", io.StringIO()):
                expire_orders.main(argv)

    def test_the_background_loop_expires_due_orders_and_stops_when_told(self):
        from app.jobs.expiry_worker import expiry_loop

        async def scenario():
            stop = asyncio.Event()
            task = asyncio.create_task(expiry_loop(new_session, interval=0.05, batch_size=10, stop=stop))
            for _ in range(100):
                await asyncio.sleep(0.05)
                if self.order_row().status == OrderStatus.CANCELLED:
                    break
            stop.set()
            await asyncio.wait_for(task, 10)

        with mock.patch("app.jobs.expiry_worker.run_expiry_pass", lambda f, batch_size: run_expiry_pass(f, batch_size=batch_size, clock=clock)):
            asyncio.run(scenario())
        self.assert_expired()

    def test_the_background_loop_survives_a_failed_pass(self):
        from app.jobs.expiry_worker import expiry_loop

        calls = []

        def flaky(factory, batch_size):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("database restarting")
            return run_expiry_pass(factory, batch_size=batch_size, clock=clock)

        async def scenario():
            stop = asyncio.Event()
            task = asyncio.create_task(expiry_loop(new_session, interval=0.05, batch_size=10, stop=stop))
            for _ in range(100):
                await asyncio.sleep(0.05)
                if self.order_row().status == OrderStatus.CANCELLED:
                    break
            stop.set()
            await asyncio.wait_for(task, 10)

        with mock.patch("app.jobs.expiry_worker.run_expiry_pass", flaky), self.assertLogs("app.jobs.expiry_worker", level="ERROR"):
            asyncio.run(scenario())
        self.assertGreaterEqual(len(calls), 2)
        self.assert_expired()

    def test_the_lifespan_starts_and_stops_the_worker(self):
        from app.jobs import expiry_worker

        async def scenario():
            async with expiry_worker.expiry_lifespan(None):
                for _ in range(100):
                    await asyncio.sleep(0.05)
                    if self.order_row().status == OrderStatus.CANCELLED:
                        break
                names = [t.get_name() for t in asyncio.all_tasks()]
                self.assertIn("order-expiry-worker", names)
            await asyncio.sleep(0.1)
            self.assertNotIn("order-expiry-worker", [t.get_name() for t in asyncio.all_tasks()])

        with mock.patch("app.database.session.SessionLocal", new_session), \
                mock.patch.object(expiry_worker.settings, "ORDER_EXPIRY_INTERVAL_SECONDS", 0.05), \
                mock.patch("app.jobs.expiry_worker.run_expiry_pass", lambda f, batch_size: run_expiry_pass(f, batch_size=batch_size, clock=clock)):
            asyncio.run(scenario())
        self.assert_expired()

    def test_the_lifespan_shuts_the_worker_down_promptly_even_with_a_long_interval(self):
        from app.jobs import expiry_worker

        async def scenario():
            async with expiry_worker.expiry_lifespan(None):
                await asyncio.sleep(0.3)  # the worker is now asleep for ~30 s
            return time.time()

        with mock.patch("app.database.session.SessionLocal", new_session), \
                mock.patch.object(expiry_worker.settings, "ORDER_EXPIRY_INTERVAL_SECONDS", 30.0):
            started = time.time()
            finished = asyncio.run(scenario())
        self.assertLess(finished - started, 5)

    def test_the_lifespan_does_nothing_when_disabled(self):
        from app.jobs import expiry_worker

        async def scenario():
            async with expiry_worker.expiry_lifespan(None):
                self.assertNotIn("order-expiry-worker", [t.get_name() for t in asyncio.all_tasks()])

        with mock.patch.object(expiry_worker.settings, "ORDER_EXPIRY_WORKER_ENABLED", False):
            asyncio.run(scenario())
        self.assertEqual(self.order_row().status, OrderStatus.PENDING)

    def test_the_lifespan_plugs_into_fastapi(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.jobs import expiry_worker

        app = FastAPI(lifespan=expiry_worker.expiry_lifespan)
        with mock.patch("app.database.session.SessionLocal", new_session), \
                mock.patch.object(expiry_worker.settings, "ORDER_EXPIRY_INTERVAL_SECONDS", 0.05), \
                mock.patch("app.jobs.expiry_worker.run_expiry_pass", lambda f, batch_size: run_expiry_pass(f, batch_size=batch_size, clock=clock)):
            with TestClient(app):
                for _ in range(100):
                    time.sleep(0.05)
                    if self.order_row().status == OrderStatus.CANCELLED:
                        break
        self.assert_expired()


class ConfigTests(unittest.TestCase):
    def test_defaults_and_bounds(self):
        from pydantic import ValidationError

        from app.core.config import Settings

        s = Settings()
        self.assertEqual((s.ORDER_PAYMENT_WINDOW_MINUTES, s.ORDER_EXPIRY_WORKER_ENABLED, s.ORDER_EXPIRY_BATCH_SIZE), (30, True, 50))
        self.assertEqual(s.ORDER_EXPIRY_INTERVAL_SECONDS, 60.0)
        for bad in ({"ORDER_EXPIRY_INTERVAL_SECONDS": 0}, {"ORDER_EXPIRY_BATCH_SIZE": 0}, {"ORDER_EXPIRY_BATCH_SIZE": 501},
                    {"ORDER_EXPIRY_INTERVAL_SECONDS": 99999}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                Settings(**bad)


if __name__ == "__main__":
    unittest.main()
