"""Phase 7 / Milestone 10-11: the read-only inspection script used in the Razorpay TEST-mode run."""

import io
import contextlib
from unittest import mock

from app.models import Order, OrderInventoryState, OrderPaymentStatus, OrderStatus, PaymentTransactionStatus as S
from scripts import p7_inspect
from tests.pg_support import PostgresTestCase, new_session


class InspectScriptTests(PostgresTestCase):
    def run_script(self, *argv):
        out = io.StringIO()
        # the script uses the app's own session factory; point it at the test database
        with mock.patch.object(p7_inspect, "SessionLocal", new_session), contextlib.redirect_stdout(out):
            code = p7_inspect.main(list(argv))
        return code, out.getvalue()

    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="100.00", stock=5)

    def test_a_healthy_open_order_prints_and_passes_the_check(self):
        order = self.make_order(self.user, [(self.product, 2)])
        self.make_payment(order, gateway_order_id="order_INSPECT1")
        code, text = self.run_script("--order", order.order_number, "--check")
        self.assertEqual(code, 0, text)
        for needle in (order.order_number, "pending", "order_INSPECT1", "initiated", "CHECK OK", "quantity 5, reserved 2"):
            self.assertIn(needle, text)

    def test_a_late_payment_is_shown_with_its_refund_flag_and_is_still_healthy(self):
        order = self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CANCELLED,
                                inventory_state=OrderInventoryState.RELEASED, reserve_stock=False)
        self.make_payment(order, gateway_order_id="order_INSPECT2", status=S.CAPTURED, refund_required=True)
        code, text = self.run_script("--order", order.order_number, "--check")
        self.assertEqual(code, 0, text)
        self.assertIn("REFUND REQUIRED", text)

    def test_a_broken_order_fails_the_check_with_status_1(self):
        order = self.make_order(self.user, [(self.product, 1)])
        with new_session() as s:  # corrupt it: paid but still pending
            s.query(Order).filter(Order.id == order.id).update({Order.payment_status: OrderPaymentStatus.PAID})
            s.commit()
        code, text = self.run_script("--order", order.order_number, "--check")
        self.assertEqual(code, 1)
        self.assertIn("CHECK FAILED", text)

    def test_it_changes_nothing_and_never_prints_a_signature(self):
        order = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(order, gateway_order_id="order_INSPECT3", status=S.CAPTURED, gateway_signature="deadbeef" * 8)
        before = self.stock(self.product)
        code, text = self.run_script("--latest", "5")
        self.assertEqual(code, 0)
        self.assertNotIn("deadbeef", text)
        self.assertEqual(self.stock(self.product), before)

    def test_an_unknown_order_number_is_reported(self):
        code, text = self.run_script("--order", "PRM-0000-000000")
        self.assertEqual(code, 2)
        self.assertIn("No order numbered", text)
