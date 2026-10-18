"""Phase 7 / Milestone 2: the Phase 6 code paths that fill the new order
columns - checkout sets `expires_at`, a customer cancel records its reason."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models import Order, OrderCancellationReason, OrderStatus
from app.services.order_service import OrderService
from tests.pg_support import new_session
from tests.test_p6_checkout import CheckoutTestCase

T0 = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)


class CheckoutExpiryTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=20)

    def place(self, **service_kwargs):
        self.fill_cart(self.user, [(self.product, 1)])
        return self.checkout(self.user, self.address, **service_kwargs)

    def stored(self, order_id):
        with new_session() as s:
            return s.get(Order, order_id)

    def test_expires_30_minutes_after_checkout_by_default(self):
        order = self.place(clock=lambda: T0).order
        self.assertEqual(self.stored(order.id).expires_at, T0 + timedelta(minutes=30))

    def test_the_window_comes_from_configuration(self):
        with patch("app.services.checkout_service.settings.ORDER_PAYMENT_WINDOW_MINUTES", 10):
            order = self.place(clock=lambda: T0).order
        self.assertEqual(self.stored(order.id).expires_at, T0 + timedelta(minutes=10))

    def test_an_explicit_window_overrides_configuration(self):
        order = self.place(clock=lambda: T0, payment_window=timedelta(minutes=45)).order
        self.assertEqual(self.stored(order.id).expires_at, T0 + timedelta(minutes=45))

    def test_a_replayed_checkout_does_not_extend_the_deadline(self):
        self.fill_cart(self.user, [(self.product, 1)])
        first = self.checkout(self.user, self.address, key="k-replay-0001", clock=lambda: T0)
        later = self.checkout(self.user, self.address, key="k-replay-0001", clock=lambda: T0 + timedelta(minutes=20))
        self.assertTrue(first.created)
        self.assertFalse(later.created)
        self.assertEqual(self.stored(later.order.id).expires_at, T0 + timedelta(minutes=30))

    def test_a_new_order_is_open_and_has_no_cancellation_reason(self):
        order = self.stored(self.place().order.id)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertIsNone(order.cancellation_reason)
        self.assertIsNone(order.cancelled_at)


class CustomerCancelReasonTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=20)
        self.fill_cart(self.user, [(self.product, 2)])
        self.order = self.checkout(self.user, self.address).order

    def row(self):
        with new_session() as s:
            o = s.get(Order, self.order.id)
            return o.status, o.cancellation_reason, o.cancelled_at

    def test_a_customer_cancel_records_the_customer_reason(self):
        OrderService(self.db).cancel_order(self.user.id, self.order.id)
        status, reason, cancelled_at = self.row()
        self.assertEqual(status, OrderStatus.CANCELLED)
        self.assertEqual(reason, OrderCancellationReason.CUSTOMER)
        self.assertIsNotNone(cancelled_at)

    def test_cancelling_again_changes_neither_reason_nor_time(self):
        OrderService(self.db).cancel_order(self.user.id, self.order.id)
        before = self.row()
        OrderService(self.db).cancel_order(self.user.id, self.order.id)
        self.assertEqual(self.row(), before)

    def test_cancelling_still_releases_stock(self):
        self.assertEqual(self.stock(self.product), (20, 2))
        OrderService(self.db).cancel_order(self.user.id, self.order.id)
        self.assertEqual(self.stock(self.product), (20, 0))
