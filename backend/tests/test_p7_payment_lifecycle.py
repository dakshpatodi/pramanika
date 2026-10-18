"""Phase 7 / Milestone 6: how payments and the Phase 6 cancel flow interact."""

import unittest

from app.core.exceptions import (
    LatePaymentError,
    OrderAlreadyPaidError,
    OrderNotCancellableError,
    OrderNotPayableError,
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
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.payment_state import REASON_ORDER_CANCELLED
from tests.payment_fakes import FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session, run_concurrently

RZ = "order_LIFE01"
PAY = "pay_LIFE01"


class LifecycleCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.coupon = self.make_coupon(usage_limit=10, used_count=1)  # this order's use is counted
        self.order = self.make_order(self.user, [(self.product, 1)], coupon=self.coupon)
        self.payment = self.make_payment(self.order, gateway_order_id=RZ)
        self.gateway = FakeGateway()
        self.gateway.register_payment(PAY, order_id=RZ, amount_paise=40621)

    def cancel(self):
        with new_session() as s:
            return OrderService(s).cancel_order(self.user.id, self.order.id)

    def verify(self):
        with new_session() as s:
            return PaymentService(s, self.gateway).verify_payment(
                self.user.id, self.order.id,
                razorpay_order_id=RZ, razorpay_payment_id=PAY, razorpay_signature=sign(RZ, PAY),
            )

    def start(self):
        with new_session() as s:
            return PaymentService(s, self.gateway).create_razorpay_order(self.user.id, self.order.id)

    def order_row(self):
        with new_session() as s:
            row = s.get(Order, self.order.id)
            s.expunge(row)
            return row

    def payment_rows(self):
        with new_session() as s:
            rows = s.query(Payment).filter(Payment.order_id == self.order.id).order_by(Payment.created_at).all()
            for r in rows:
                s.expunge(r)
            return rows


class CancelClosesPaymentTests(LifecycleCase):
    def test_cancelling_closes_the_open_payment_so_it_cannot_be_paid_as_if_the_order_lived(self):
        self.cancel()
        (p,) = self.payment_rows()
        self.assertEqual(p.status, S.EXPIRED)
        self.assertEqual(p.failure_reason, REASON_ORDER_CANCELLED)
        self.assertIsNone(p.paid_at)
        self.assertFalse(p.refund_required)

    def test_an_authorized_payment_is_closed_too(self):
        self.db.query(Payment).filter(Payment.id == self.payment.id).update({Payment.status: S.AUTHORIZED})
        self.db.commit()
        self.cancel()
        self.assertEqual(self.payment_rows()[0].status, S.EXPIRED)

    def test_the_order_keeps_its_phase_6_shape(self):
        self.cancel()
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status, o.inventory_state, o.cancellation_reason),
                         (OrderStatus.CANCELLED, OrderPaymentStatus.PENDING, OrderInventoryState.RELEASED,
                          OrderCancellationReason.CUSTOMER))

    def test_stock_and_coupon_are_still_given_back_exactly_once(self):
        self.assertEqual(self.stock(self.product), (5, 1))
        used = self.used_count(self.coupon)
        self.cancel()
        self.assertEqual(self.stock(self.product), (5, 0))
        self.assertEqual(self.used_count(self.coupon), used - 1)

    def test_cancelling_twice_changes_nothing_the_second_time(self):
        self.cancel()
        snapshot = (self.stock(self.product), self.used_count(self.coupon),
                    [(p.status, p.failure_reason) for p in self.payment_rows()])
        self.cancel()
        self.assertEqual((self.stock(self.product), self.used_count(self.coupon),
                          [(p.status, p.failure_reason) for p in self.payment_rows()]), snapshot)

    def test_cancelling_an_order_with_no_payment_still_works(self):
        order = self.make_order(self.user, [(self.product, 1)])
        with new_session() as s:
            OrderService(s).cancel_order(self.user.id, order.id)
        self.assertEqual(self.stock(self.product), (5, 1))  # the first order's unit is still reserved

    def test_a_failed_attempt_is_left_as_failed(self):
        self.db.query(Payment).filter(Payment.id == self.payment.id).update(
            {Payment.status: S.FAILED, Payment.failure_reason: "declined"})
        self.db.commit()
        self.cancel()
        p = self.payment_rows()[0]
        self.assertEqual((p.status, p.failure_reason), (S.FAILED, "declined"))

    def test_a_failure_while_closing_payments_undoes_the_whole_cancel(self):
        from unittest import mock

        with mock.patch("app.services.order_service.close_open_payments", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.cancel()
        o = self.order_row()
        self.assertEqual((o.status, o.inventory_state), (OrderStatus.PENDING, OrderInventoryState.RESERVED))
        self.assertEqual(self.stock(self.product), (5, 1))
        self.assertEqual(self.payment_rows()[0].status, S.INITIATED)


class PaidOrdersCannotBeCancelledTests(LifecycleCase):
    def test_a_paid_order_is_refused_and_nothing_changes(self):
        self.verify()
        before = (self.stock(self.product), self.used_count(self.coupon), self.payment_rows()[0].status)
        with self.assertRaises(OrderNotCancellableError):
            self.cancel()
        self.assertEqual((self.stock(self.product), self.used_count(self.coupon), self.payment_rows()[0].status), before)
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status), (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID))
        self.assertEqual(self.payment_rows()[0].status, S.CAPTURED)


class PayAfterCloseTests(LifecycleCase):
    def test_a_cancelled_order_cannot_start_a_new_payment(self):
        self.cancel()
        with self.assertRaises(OrderNotPayableError):
            self.start()
        self.assertEqual(len(self.payment_rows()), 1)

    def test_a_paid_order_cannot_start_a_new_payment(self):
        self.verify()
        with self.assertRaises(OrderAlreadyPaidError):
            self.start()

    def test_money_arriving_after_a_customer_cancel_is_recorded_and_flagged_not_applied(self):
        self.cancel()
        with self.assertRaises(LatePaymentError):
            self.verify()
        p = self.payment_rows()[0]
        self.assertEqual((p.status, p.refund_required, p.gateway_payment_id), (S.CAPTURED, True, PAY))
        self.assertIsNotNone(p.paid_at)
        self.assertIsNone(p.failure_reason)  # the 'closed' note is cleared once it is captured
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status, o.inventory_state),
                         (OrderStatus.CANCELLED, OrderPaymentStatus.PENDING, OrderInventoryState.RELEASED))
        self.assertEqual(self.stock(self.product), (5, 0))  # not sold, not re-reserved

    def test_the_same_late_payment_is_not_applied_twice(self):
        self.cancel()
        for _ in range(2):
            with self.assertRaises(LatePaymentError):
                self.verify()
        self.assertEqual(len(self.payment_rows()), 1)
        self.assertEqual(self.stock(self.product), (5, 0))


class RetryTests(LifecycleCase):
    def test_after_a_failed_attempt_the_customer_may_pay_again_on_the_same_order(self):
        self.db.query(Payment).filter(Payment.id == self.payment.id).update(
            {Payment.status: S.FAILED, Payment.failure_reason: "declined"})
        self.db.commit()
        result = self.start()
        self.assertTrue(result.created)
        rows = self.payment_rows()
        self.assertEqual(sorted(p.status.value for p in rows), ["failed", "initiated"])
        with new_session() as s:
            self.assertEqual(s.query(Order).filter(Order.user_id == self.user.id).count(), 1)

    def test_an_open_attempt_is_reused_not_duplicated(self):
        first = self.start()
        again = self.start()
        self.assertEqual(first.intent.razorpay_order_id, again.intent.razorpay_order_id)
        self.assertFalse(again.created)


class CancelRacesVerifyTests(LifecycleCase):
    def test_exactly_one_side_wins_and_money_is_never_lost_or_double_counted(self):
        for attempt in range(6):
            with self.subTest(attempt=attempt):
                self.fresh_order(attempt)
                results = run_concurrently([self.verify_outcome, self.cancel_outcome])
                self.assertEqual([kind for kind, _ in results], ["ok", "ok"], results)  # no crash, no deadlock
                verify, cancel = (value for _, value in results)
                o, p = self.order_row(), self.payment_rows()[0]
                if o.payment_status == OrderPaymentStatus.PAID:
                    self.assertEqual((verify, cancel), ("paid", "refused"))
                    self.assertEqual((o.status, p.status, p.refund_required), (OrderStatus.CONFIRMED, S.CAPTURED, False))
                    self.assertEqual(self.stock(self.product), (4, 0))
                    self.assertEqual(self.used_count(self.coupon), 1)  # a paid order keeps its coupon use
                else:
                    self.assertEqual((verify, cancel), ("late", "cancelled"))
                    self.assertEqual((o.status, o.inventory_state), (OrderStatus.CANCELLED, OrderInventoryState.RELEASED))
                    self.assertEqual((p.status, p.refund_required), (S.CAPTURED, True))
                    self.assertEqual(self.stock(self.product), (5, 0))
                    self.assertEqual(self.used_count(self.coupon), 0)  # given back exactly once

    # helpers -----------------------------------------------------------------

    def fresh_order(self, n):
        self.db.query(type(self.coupon)).filter_by(id=self.coupon.id).update({"used_count": 1})
        self.db.commit()
        self.order = self.make_order(self.user, [(self.product, 1)], coupon=self.coupon)
        self.rz, self.pay_id = f"order_RACE{n}", f"pay_RACE{n}"
        self.payment = self.make_payment(self.order, gateway_order_id=self.rz)
        self.user_id, self.order_id = self.user.id, self.order.id  # plain ids: ORM objects are not thread-safe
        self.gateway.register_payment(self.pay_id, order_id=self.rz, amount_paise=40621)
        # earlier iterations left their stock consumed or released; reset to (5, 1)
        from app.models import Inventory
        self.db.query(Inventory).filter(Inventory.product_id == self.product.id).update(
            {Inventory.quantity: 5, Inventory.reserved_quantity: 1})
        self.db.commit()

    def verify_outcome(self):
        with new_session() as s:
            try:
                PaymentService(s, self.gateway).verify_payment(
                    self.user_id, self.order_id, razorpay_order_id=self.rz,
                    razorpay_payment_id=self.pay_id, razorpay_signature=sign(self.rz, self.pay_id))
                return "paid"
            except LatePaymentError:
                return "late"

    def cancel_outcome(self):
        try:
            with new_session() as s:
                OrderService(s).cancel_order(self.user_id, self.order_id)
            return "cancelled"
        except OrderNotCancellableError:
            return "refused"


if __name__ == "__main__":
    unittest.main()
