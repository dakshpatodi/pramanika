"""
Phase 7 / Milestone 9: what the order endpoints tell the customer about payment
(PostgreSQL integration; no Razorpay).

The server decides: `can_pay`, `expires_at`, `cancellation_reason` and the small
`payment` summary are what the order pages show. No gateway ids, amounts or bank
messages ever leave in them.
"""

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api import orders as orders_api
from app.core.security import create_access_token
from app.models import (
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus as S,
)
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from tests.payment_fakes import FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session
from tests.test_p7_payment_api import build_app

NOW = datetime.now(timezone.utc).replace(microsecond=0)
MINUTE = timedelta(minutes=1)


class ViewCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.user_id = self.user.id
        self.product = self.make_product(price="406.21", stock=20)
        app = build_app(FakeGateway())
        app.include_router(orders_api.router)
        self.client = TestClient(app)

    def headers(self):
        return {"Authorization": f"Bearer {create_access_token(self.user_id, self.user.role.value)}"}

    def get(self, order):
        response = self.client.get(f"/api/orders/{order.id}", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def new_order(self, **kwargs):
        kwargs.setdefault("expires_at", NOW + 20 * MINUTE)
        return self.make_order(self.user, [(self.product, 1)], **kwargs)

    def service_view(self, order):
        with new_session() as s:
            return OrderService(s).get_order(self.user_id, order.id)


class DetailTests(ViewCase):
    def test_a_fresh_unpaid_order_can_be_paid_and_says_when_it_expires(self):
        order = self.new_order()
        data = self.get(order)
        self.assertTrue(data["can_pay"])
        self.assertTrue(data["can_cancel"])
        self.assertIsNone(data["cancellation_reason"])
        self.assertEqual(datetime.fromisoformat(data["expires_at"]), NOW + 20 * MINUTE)
        self.assertEqual(data["payment"], {"last_attempt": None, "refund_pending": False})

    def test_an_open_attempt_is_reported_and_the_order_stays_payable(self):
        order = self.new_order()
        self.make_payment(order, gateway_order_id="order_V1")
        data = self.get(order)
        self.assertEqual((data["payment"]["last_attempt"], data["can_pay"]), ("initiated", True))

    def test_a_failed_attempt_leaves_the_order_payable_so_the_customer_can_retry(self):
        order = self.new_order()
        self.make_payment(order, gateway_order_id="order_V2", status=S.FAILED, failure_reason="declined by bank")
        data = self.get(order)
        self.assertEqual((data["payment"]["last_attempt"], data["can_pay"], data["payment_status"]), ("failed", True, "pending"))
        self.assertNotIn("declined", json.dumps(data))  # the bank's wording is not passed on

    def test_the_latest_attempt_is_the_one_reported(self):
        order = self.new_order()
        self.make_payment(order, gateway_order_id="order_V3a", status=S.FAILED)
        self.make_payment(order, gateway_order_id="order_V3b", status=S.EXPIRED)
        self.make_payment(order, gateway_order_id="order_V3c", status=S.AUTHORIZED)
        self.assertEqual(self.get(order)["payment"]["last_attempt"], "authorized")

    def test_an_order_past_its_deadline_is_not_payable_even_before_the_expiry_job_runs(self):
        order = self.new_order(expires_at=NOW - MINUTE)
        data = self.get(order)
        self.assertEqual((data["status"], data["can_pay"]), ("pending", False))
        self.assertTrue(data["can_cancel"])  # the customer may still cancel it

    def test_payability_is_judged_by_the_service_clock(self):
        order = self.new_order(expires_at=NOW + 20 * MINUTE)
        with new_session() as s:
            later = OrderService(s, clock=lambda: NOW + 30 * MINUTE).get_order(self.user_id, order.id)
            earlier = OrderService(s, clock=lambda: NOW).get_order(self.user_id, order.id)
        self.assertEqual((later.can_pay, earlier.can_pay), (False, True))

    def test_an_order_with_no_deadline_stays_payable(self):
        self.assertTrue(self.get(self.new_order(expires_at=None))["can_pay"])

    def test_an_expired_order_says_expired_and_cannot_be_paid_or_cancelled(self):
        order = self.new_order(expires_at=NOW - MINUTE)
        self.make_payment(order, gateway_order_id="order_V4")
        from app.services.order_expiry_service import run_expiry_pass

        run_expiry_pass(new_session, clock=lambda: NOW)
        data = self.get(order)
        self.assertEqual((data["status"], data["cancellation_reason"], data["can_pay"], data["can_cancel"], data["payment_status"]),
                         ("cancelled", "expired", False, False, "pending"))
        self.assertEqual(data["payment"], {"last_attempt": "expired", "refund_pending": False})

    def test_a_customer_cancelled_order_says_customer(self):
        order = self.new_order()
        with new_session() as s:
            OrderService(s).cancel_order(self.user_id, order.id)
        data = self.get(order)
        self.assertEqual((data["status"], data["cancellation_reason"], data["can_pay"]), ("cancelled", "customer", False))

    def test_a_paid_order_cannot_be_paid_again_or_cancelled(self):
        order = self.new_order()
        payment = self.make_payment(order, gateway_order_id="order_V5", amount=order.total_amount)
        gateway = FakeGateway()
        gateway.register_payment("pay_V5", order_id="order_V5", amount_paise=40621)
        with new_session() as s:
            result = PaymentService(s, gateway).verify_payment(
                self.user_id, order.id, razorpay_order_id="order_V5", razorpay_payment_id="pay_V5", razorpay_signature=sign("order_V5", "pay_V5"))
        # the verify response itself already carries the new fields
        self.assertEqual((result.order.can_pay, result.order.can_cancel, result.order.payment.last_attempt), (False, False, "captured"))
        data = self.get(order)
        self.assertEqual((data["can_pay"], data["can_cancel"], data["payment_status"], data["payment"]["last_attempt"]),
                         (False, False, "paid", "captured"))
        self.assertFalse(data["payment"]["refund_pending"])
        self.assertEqual(payment.id, self.payment_id_of(order))

    def payment_id_of(self, order):
        with new_session() as s:
            return s.query(Payment).filter(Payment.order_id == order.id).one().id

    def test_money_that_arrived_after_the_order_closed_shows_as_refund_pending(self):
        order = self.new_order(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED,
                               cancellation_reason=OrderCancellationReason.EXPIRED)
        self.make_payment(order, gateway_order_id="order_V6", status=S.CAPTURED, refund_required=True)
        data = self.get(order)
        self.assertEqual((data["can_pay"], data["payment"]), (False, {"last_attempt": "captured", "refund_pending": True}))
        self.assertEqual(data["payment_status"], "pending")  # the order was not paid

    def test_nothing_internal_leaks(self):
        order = self.new_order()
        self.make_payment(order, gateway_order_id="order_SECRETISH", status=S.CAPTURED, gateway_payment_id="pay_SECRETISH",
                          gateway_signature="sig-secretish")
        text = json.dumps(self.get(order))
        for forbidden in ("order_SECRETISH", "pay_SECRETISH", "sig-secretish", "gateway", "razorpay", "failure_reason", "idempotency"):
            self.assertNotIn(forbidden, text.lower() if forbidden.islower() else text)

    def test_someone_elses_order_is_still_a_404(self):
        order = self.new_order()
        other = self.make_user()
        response = self.client.get(f"/api/orders/{order.id}",
                                   headers={"Authorization": f"Bearer {create_access_token(other.id, other.role.value)}"})
        self.assertEqual(response.status_code, 404)


class ListTests(ViewCase):
    def test_each_row_carries_its_own_pay_and_expiry_state(self):
        payable = self.new_order()
        overdue = self.new_order(expires_at=NOW - MINUTE)
        cancelled = self.new_order(status=OrderStatus.CANCELLED, inventory_state=OrderInventoryState.RELEASED,
                                   cancellation_reason=OrderCancellationReason.EXPIRED)
        paid = self.new_order(status=OrderStatus.CONFIRMED, payment_status=OrderPaymentStatus.PAID,
                              inventory_state=OrderInventoryState.CONSUMED)
        response = self.client.get("/api/orders?page=1&page_size=10", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        rows = {r["id"]: r for r in response.json()["data"]["orders"]}
        self.assertEqual(len(rows), 4)
        self.assertEqual([rows[str(o.id)]["can_pay"] for o in (payable, overdue, cancelled, paid)], [True, False, False, False])
        self.assertEqual(rows[str(cancelled.id)]["cancellation_reason"], "expired")
        self.assertIsNone(rows[str(payable.id)]["cancellation_reason"])
        self.assertIsNotNone(rows[str(payable.id)]["expires_at"])

    def test_the_list_does_not_carry_the_detail_payment_summary(self):
        self.new_order()
        rows = self.client.get("/api/orders", headers=self.headers()).json()["data"]["orders"]
        self.assertNotIn("payment", rows[0])
