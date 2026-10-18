"""
Phase 7 / Milestone 3: POST /api/orders/{order_id}/payment over HTTP
(PostgreSQL integration; Razorpay is always a fake or a mocked transport).

Builds a small FastAPI app from the real payments router and the real auth
dependencies, exactly like test_p6_order_api.py. The PowerShell/browser
checks (M11) cover the real main.py wiring and real Razorpay test mode.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import payments as payments_api
from app.core.exceptions import DomainError, PaymentsNotConfiguredError
from app.core.payment_config import RazorpayCredentials
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import OrderCancellationReason, OrderInventoryState, OrderPaymentStatus, OrderStatus, Payment
from app.services.razorpay_gateway import RazorpayGateway
from tests.payment_fakes import FakeGateway
from tests.pg_support import PostgresTestCase, new_session

KEY_ID = "rzp_test_FAKEKEYID000000"
SECRET = "fake-key-secret-DO-NOT-LEAK-111"


def build_app(gateway=None) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.http_status, content={"success": False, "message": exc.message})

    def override_get_db():
        session = new_session()
        try:
            yield session
        finally:
            session.close()

    app.include_router(payments_api.router)
    app.dependency_overrides[get_db] = override_get_db
    if gateway is not None:
        app.dependency_overrides[payments_api.get_payment_gateway] = lambda: gateway
    return app


class PaymentApiTestCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.gateway = FakeGateway()
        self.client = TestClient(build_app(self.gateway))
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.order = self.make_order(self.user, [(self.product, 1)])

    def auth(self, user=None):
        user = user or self.user
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def start(self, order=None, user=None, **kwargs):
        order = order or self.order
        return self.client.post(f"/api/orders/{order.id}/payment", headers=self.auth(user), **kwargs)


class AuthenticationTests(PaymentApiTestCase):
    def test_a_login_is_required(self):
        for headers in ({}, {"Authorization": "Bearer not-a-token"}):
            with self.subTest(headers=headers):
                response = self.client.post(f"/api/orders/{self.order.id}/payment", headers=headers)
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.gateway.calls, [])

    def test_an_anonymous_caller_gets_401_even_when_payments_are_not_configured(self):
        """401 before 503: a stranger must not learn whether Razorpay is set up."""
        client = TestClient(build_app())  # the real gateway dependency
        with mock.patch.object(payments_api, "get_razorpay_credentials", side_effect=PaymentsNotConfiguredError()):
            response = client.post(f"/api/orders/{self.order.id}/payment")
        self.assertEqual(response.status_code, 401)

    def test_someone_elses_order_is_a_404(self):
        response = self.start(user=self.make_user())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"success": False, "message": "Order was not found."})
        self.assertEqual(self.gateway.calls, [])


class SuccessTests(PaymentApiTestCase):
    def test_the_first_call_creates_the_razorpay_order(self):
        response = self.start()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(
            body["data"],
            {
                "order_id": str(self.order.id),
                "order_number": self.order.order_number,
                "razorpay_order_id": "order_FAKE000001",
                "razorpay_key_id": KEY_ID,
                "amount_paise": 40621,
                "currency": "INR",
            },
        )

    def test_a_repeat_returns_the_same_order_with_200(self):
        first, second = self.start(), self.start()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["data"], second.json()["data"])
        self.assertEqual(len(self.gateway.calls), 1)

    def test_the_response_is_not_cacheable(self):
        for response in (self.start(), self.start()):
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_a_client_cannot_choose_the_amount(self):
        for kwargs in (
            {"json": {"amount": 1, "amount_paise": 1, "total_amount": "0.01", "currency": "USD"}},
            {"params": {"amount": 1}},
            {"headers": {"X-Amount": "1"}},
        ):
            with self.subTest(kwargs=list(kwargs)):
                headers = {**self.auth(), **kwargs.pop("headers", {})}
                response = self.client.post(f"/api/orders/{self.order.id}/payment", headers=headers, **kwargs)
                self.assertIn(response.status_code, (200, 201))
                self.assertEqual(response.json()["data"]["amount_paise"], 40621)
        self.assertEqual({c["amount_paise"] for c in self.gateway.calls}, {40621})
        self.assertEqual({c["currency"] for c in self.gateway.calls}, {"INR"})

    def test_the_payment_is_stored_against_the_order(self):
        self.start()
        with new_session() as s:
            (payment,) = s.query(Payment).all()
            self.assertEqual(payment.order_id, self.order.id)
            self.assertEqual(payment.gateway_order_id, "order_FAKE000001")


class RefusalTests(PaymentApiTestCase):
    def assert_409(self, order, fragment):
        response = self.start(order)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertIn(fragment, response.json()["message"].lower())
        self.assertEqual(self.gateway.calls, [])

    def test_cancelled(self):
        self.assert_409(
            self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CANCELLED,
                            inventory_state=OrderInventoryState.RELEASED),
            "cancelled",
        )

    def test_expired(self):
        self.assert_409(
            self.make_order(self.user, [(self.product, 1)], status=OrderStatus.CANCELLED,
                            inventory_state=OrderInventoryState.RELEASED,
                            cancellation_reason=OrderCancellationReason.EXPIRED),
            "expired",
        )

    def test_past_its_deadline(self):
        self.assert_409(
            self.make_order(self.user, [(self.product, 1)], expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
            "expired",
        )

    def test_already_paid(self):
        self.assert_409(
            self.make_order(self.user, [(self.product, 1)], payment_status=OrderPaymentStatus.PAID,
                            inventory_state=OrderInventoryState.CONSUMED),
            "already been paid",
        )

    def test_a_malformed_order_id_is_a_422(self):
        response = self.client.post("/api/orders/not-a-uuid/payment", headers=self.auth())
        self.assertEqual(response.status_code, 422)

    def test_an_unknown_order_is_a_404(self):
        response = self.client.post(f"/api/orders/{uuid.uuid4()}/payment", headers=self.auth())
        self.assertEqual(response.status_code, 404)


class GatewayFailureTests(PaymentApiTestCase):
    def test_razorpay_failing_is_a_502_with_a_generic_message_and_nothing_stored(self):
        client = TestClient(build_app(FakeGateway(fail=True)))
        response = client.post(f"/api/orders/{self.order.id}/payment", headers=self.auth())
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["success"])
        self.assertIn("nothing was charged", response.json()["message"].lower())
        with new_session() as s:
            self.assertEqual(s.query(Payment).count(), 0)

    def test_unconfigured_payments_are_a_503_with_a_generic_message(self):
        client = TestClient(build_app())
        with mock.patch.object(payments_api, "get_razorpay_credentials", side_effect=PaymentsNotConfiguredError()):
            response = client.post(f"/api/orders/{self.order.id}/payment", headers=self.auth())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("RAZORPAY", response.text)
        with new_session() as s:
            self.assertEqual(s.query(Payment).count(), 0)


class EndToEndWithMockedRazorpayTests(PaymentApiTestCase):
    """The real RazorpayGateway, with only the network replaced."""

    def setUp(self):
        super().setUp()
        self.seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": "order_REAL0001", "amount": body["amount"], "currency": body["currency"],
                                             "status": "created", "receipt": body["receipt"]})

        gateway = RazorpayGateway(RazorpayCredentials(key_id=KEY_ID, key_secret=SECRET), transport=httpx.MockTransport(handler))
        self.client = TestClient(build_app(gateway))

    def test_the_wire_request_and_the_response(self):
        with self.assertNoLogs(level=logging.WARNING):
            response = self.start()
        self.assertEqual(response.status_code, 201)
        (request,) = self.seen
        self.assertEqual(json.loads(request.content)["amount"], 40621)
        self.assertEqual(response.json()["data"]["razorpay_order_id"], "order_REAL0001")

    def test_the_secret_never_appears_in_any_response(self):
        responses = [self.start(), self.start(), self.start(user=self.make_user())]
        for response in responses:
            self.assertNotIn(SECRET, response.text)
            self.assertNotIn(SECRET, json.dumps(dict(response.headers)))
            self.assertNotIn("secret", response.text.lower())
            self.assertNotIn("signature", response.text.lower())

    def test_razorpay_rejecting_the_request_gives_a_502_and_leaks_nothing(self):
        def handler(request):
            return httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}})

        gateway = RazorpayGateway(RazorpayCredentials(key_id=KEY_ID, key_secret=SECRET), transport=httpx.MockTransport(handler))
        client = TestClient(build_app(gateway))
        with self.assertLogs("app.services.razorpay_gateway", level=logging.ERROR) as logs:
            response = client.post(f"/api/orders/{self.order.id}/payment", headers=self.auth())
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("Authentication failed", response.text)
        self.assertNotIn(SECRET, response.text + "\n".join(logs.output))
