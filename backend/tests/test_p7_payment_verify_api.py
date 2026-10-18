"""
Phase 7 / Milestone 5: POST /api/orders/{order_id}/payment/verify over HTTP
(PostgreSQL integration; Razorpay is a fake or a mocked transport).
"""

import json
import logging
import uuid

import httpx
from fastapi.testclient import TestClient

from app.core.payment_config import RazorpayCredentials
from app.core.security import create_access_token
from app.models import Order, OrderCancellationReason, OrderInventoryState, OrderPaymentStatus, OrderStatus, Payment
from app.models import PaymentTransactionStatus as S
from app.services.razorpay_gateway import RazorpayGateway
from tests.payment_fakes import FAKE_SECRET, FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session
from tests.test_p7_payment_api import build_app

RZ_ORDER, PAY_ID = "order_APITEST01", "pay_APITEST01"


class VerifyApiTestCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.gateway = FakeGateway()
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621)
        self.client = TestClient(build_app(self.gateway))
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.order = self.make_order(self.user, [(self.product, 1)])
        self.payment = self.make_payment(self.order, gateway_order_id=RZ_ORDER)

    def auth(self, user=None):
        user = user or self.user
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def body(self, **overrides):
        values = {"razorpay_order_id": RZ_ORDER, "razorpay_payment_id": PAY_ID, "razorpay_signature": sign(RZ_ORDER, PAY_ID)}
        values.update(overrides)
        return values

    def verify(self, order=None, user=None, client=None, headers=None, **overrides):
        order = order or self.order
        h = self.auth(user) if headers is None else headers
        return (client or self.client).post(f"/api/orders/{order.id}/payment/verify", json=self.body(**overrides), headers=h)

    def order_row(self):
        with new_session() as s:
            row = s.get(Order, self.order.id)
            s.expunge(row)
            return row


class AuthenticationTests(VerifyApiTestCase):
    def test_a_login_is_required(self):
        for headers in ({}, {"Authorization": "Bearer not-a-token"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.verify(headers=headers).status_code, 401)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(self.gateway.fetches, [])

    def test_someone_elses_order_is_a_404_even_with_a_genuine_signature(self):
        response = self.verify(user=self.make_user())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"success": False, "message": "Order was not found."})
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_an_unknown_order_is_a_404(self):
        self.assertEqual(self.client.post(f"/api/orders/{uuid.uuid4()}/payment/verify", json=self.body(), headers=self.auth()).status_code, 404)


class PaidTests(VerifyApiTestCase):
    def test_a_genuine_payment_pays_the_order_and_returns_it(self):
        response = self.verify()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], "Payment confirmed.")
        data = body["data"]
        self.assertEqual((data["id"], data["status"], data["payment_status"]), (str(self.order.id), "confirmed", "paid"))
        self.assertIs(data["can_cancel"], False)
        self.assertEqual(data["totals"]["total"], 406.21)
        row = self.order_row()
        self.assertEqual((row.status, row.payment_status, row.inventory_state),
                         (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID, OrderInventoryState.CONSUMED))
        self.assertEqual(self.stock(self.product), (4, 0))

    def test_repeating_it_is_a_harmless_200(self):
        first, second = self.verify(), self.verify()
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(second.json()["message"], "This payment was already confirmed.")
        self.assertEqual(second.json()["data"]["payment_status"], "paid")
        self.assertEqual(self.stock(self.product), (4, 0))
        self.assertEqual(len(self.gateway.fetches), 1)

    def test_the_response_is_not_cacheable_and_does_not_echo_the_signature_or_any_secret(self):
        response = self.verify()
        self.assertEqual(response.headers["cache-control"], "no-store")
        for needle in (sign(RZ_ORDER, PAY_ID), FAKE_SECRET, "razorpay_signature", PAY_ID, "secret"):
            self.assertNotIn(needle, response.text)

    def test_the_whole_flow_through_the_api(self):
        """Start a payment, 'pay' it at Razorpay, verify: the order ends paid."""
        order = self.make_order(self.user, [(self.product, 1)])
        started = self.client.post(f"/api/orders/{order.id}/payment", headers=self.auth())
        self.assertEqual(started.status_code, 201)
        rz_order = started.json()["data"]["razorpay_order_id"]
        amount = started.json()["data"]["amount_paise"]
        self.gateway.register_payment("pay_FLOW01", order_id=rz_order, amount_paise=amount)
        response = self.client.post(
            f"/api/orders/{order.id}/payment/verify",
            json={"razorpay_order_id": rz_order, "razorpay_payment_id": "pay_FLOW01", "razorpay_signature": sign(rz_order, "pay_FLOW01")},
            headers=self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["payment_status"], "paid")
        # and paying again is now refused
        again = self.client.post(f"/api/orders/{order.id}/payment", headers=self.auth())
        self.assertEqual(again.status_code, 409)


class RejectionTests(VerifyApiTestCase):
    def test_a_forged_signature_is_a_400_with_one_generic_message(self):
        response = self.verify(razorpay_signature="0" * 64)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"success": False, "message": "We could not verify this payment."})
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(self.gateway.fetches, [])

    def test_every_cause_gets_the_same_answer(self):
        """A caller cannot tell a wrong signature from a foreign Razorpay order from a mismatch."""
        other_order = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(other_order, gateway_order_id="order_APIOTHER1", amount=other_order.total_amount)
        self.gateway.register_payment("pay_APIOTHER1", order_id="order_APIOTHER1", amount_paise=40621)
        self.gateway.register_payment("pay_APIMISMATCH", order_id=RZ_ORDER, amount_paise=1)
        answers = {
            self.verify(razorpay_signature="1" * 64).text,
            self.verify(razorpay_order_id="order_APIOTHER1", razorpay_payment_id="pay_APIOTHER1",
                        razorpay_signature=sign("order_APIOTHER1", "pay_APIOTHER1")).text,
            self.verify(razorpay_payment_id="pay_APIMISMATCH", razorpay_signature=sign(RZ_ORDER, "pay_APIMISMATCH")).text,
        }
        self.assertEqual(len(answers), 1)

    def test_malformed_values_never_reach_the_payment_logic(self):
        bad = [
            {"razorpay_order_id": "pay_notanorder"},
            {"razorpay_payment_id": "order_notapayment"},
            {"razorpay_payment_id": "pay_x/../../orders"},
            {"razorpay_payment_id": "pay_x?x=1"},
            {"razorpay_payment_id": "pay_" + "a" * 200},
            {"razorpay_signature": "short"},
            {"razorpay_signature": "G" * 64},
            {"razorpay_signature": sign(RZ_ORDER, PAY_ID).upper()},
            {"razorpay_signature": ""},
            {"razorpay_order_id": ""},
        ]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.verify(**overrides).status_code, 422)
        for missing in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature"):
            body = self.body()
            del body[missing]
            response = self.client.post(f"/api/orders/{self.order.id}/payment/verify", json=body, headers=self.auth())
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.gateway.fetches, [])
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_extra_fields_such_as_an_amount_are_ignored(self):
        response = self.client.post(
            f"/api/orders/{self.order.id}/payment/verify",
            json={**self.body(), "amount": 1, "status": "paid", "payment_status": "paid"},
            headers=self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        # What was recorded is what Razorpay confirmed for the stored amount, not anything the client said.
        with new_session() as s:
            self.assertEqual(s.query(Payment).one().amount, self.order_row().total_amount)

    def test_razorpay_not_confirming_the_payment_is_a_400(self):
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status="failed")
        self.assertEqual(self.verify().status_code, 400)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_razorpay_being_unreachable_is_a_502_that_tells_the_customer_not_to_pay_again(self):
        client = TestClient(build_app(FakeGateway(fetch_fails=True)))
        response = self.verify(client=client)
        self.assertEqual(response.status_code, 502)
        self.assertIn("don't pay again", response.json()["message"])
        self.assertNotIn("nothing was charged", response.json()["message"].lower())
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_a_different_payment_id_for_an_already_paid_razorpay_order_is_a_409(self):
        self.verify()
        self.gateway.register_payment("pay_APIEXTRA01", order_id=RZ_ORDER, amount_paise=40621)
        response = self.verify(razorpay_payment_id="pay_APIEXTRA01", razorpay_signature=sign(RZ_ORDER, "pay_APIEXTRA01"))
        self.assertEqual(response.status_code, 409)
        self.assertIn("already been paid", response.json()["message"])


class AuthorizedAndLateTests(VerifyApiTestCase):
    def test_authorized_money_answers_200_with_the_order_still_unpaid(self):
        self.gateway.register_payment(PAY_ID, order_id=RZ_ORDER, amount_paise=40621, status="authorized")
        response = self.verify()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Your payment is being confirmed.")
        self.assertEqual(response.json()["data"]["payment_status"], "pending")  # a 200 alone is NOT "paid"
        self.assertEqual(self.stock(self.product), (5, 1))

    def test_a_payment_after_the_order_closed_is_a_409_and_is_recorded_for_refund(self):
        with new_session() as s:
            s.query(Order).filter(Order.id == self.order.id).update({
                Order.status: OrderStatus.CANCELLED, Order.cancellation_reason: OrderCancellationReason.EXPIRED,
                Order.inventory_state: OrderInventoryState.RELEASED,
            })
            s.commit()
        response = self.verify()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertIn("refunded", response.json()["message"])
        with new_session() as s:
            payment = s.query(Payment).one()
            self.assertEqual((payment.status, payment.refund_required), (S.CAPTURED, True))
        self.assertEqual(self.order_row().status, OrderStatus.CANCELLED)  # never revived
        again = self.verify()
        self.assertEqual(again.status_code, 409)


class EndToEndWithMockedRazorpayTests(VerifyApiTestCase):
    """The real RazorpayGateway (real HMAC, real HTTP client) with only the network replaced."""

    def setUp(self):
        super().setUp()
        self.seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            return httpx.Response(200, json={"id": PAY_ID, "order_id": RZ_ORDER, "amount": 40621, "currency": "INR", "status": "captured"})

        self.secret = "mock-transport-secret-9999"
        gateway = RazorpayGateway(
            RazorpayCredentials(key_id="rzp_test_FAKEKEYID000000", key_secret=self.secret),
            transport=httpx.MockTransport(handler),
        )
        self.real_client = TestClient(build_app(gateway))

    def test_it_verifies_with_the_real_signature_check_and_asks_razorpay_with_a_get(self):
        signature = sign(RZ_ORDER, PAY_ID, secret=self.secret)
        response = self.verify(client=self.real_client, razorpay_signature=signature)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["payment_status"], "paid")
        (request,) = self.seen
        self.assertEqual((request.method, str(request.url)), ("GET", f"https://api.razorpay.com/v1/payments/{PAY_ID}"))

    def test_a_signature_made_with_the_wrong_secret_is_refused_and_razorpay_is_never_asked(self):
        response = self.verify(client=self.real_client, razorpay_signature=sign(RZ_ORDER, PAY_ID, secret="not-the-secret"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.seen, [])

    def test_no_secret_reaches_a_response_or_a_log(self):
        with self.assertLogs(level=logging.INFO) as logs:
            logging.getLogger("test").info("start")
            ok = self.verify(client=self.real_client, razorpay_signature=sign(RZ_ORDER, PAY_ID, secret=self.secret))
            bad = self.verify(client=self.real_client, razorpay_signature="0" * 64)
        for text in (ok.text, bad.text, "\n".join(logs.output)):
            self.assertNotIn(self.secret, text)
