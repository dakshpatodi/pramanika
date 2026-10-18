"""Phase 7 / Milestone 3: the Razorpay HTTP client (against a mocked transport)
and the rupees -> paise conversion. Pure - no database, no network, no real
credentials."""

import base64
import json
import logging
import unittest
from typing import Optional

import httpx

from app.core.exceptions import PaymentGatewayError
from app.core.money import to_paise
from app.core.payment_config import RazorpayCredentials
from app.services.razorpay_gateway import MAX_RECEIPT_LENGTH, GatewayOrder, RazorpayGateway

KEY_ID = "rzp_test_FAKEKEYID000000"
SECRET = "fake-key-secret-DO-NOT-LEAK-111"


def good_response(**overrides):
    body = {"id": "order_ABC123", "entity": "order", "amount": 40621, "amount_paid": 0, "amount_due": 40621,
            "currency": "INR", "receipt": "PRM-2026-000123-1", "status": "created", "notes": {}}
    body.update(overrides)
    return body


class Recorder:
    """A MockTransport handler that remembers the requests it saw."""

    def __init__(self, response=None, *, status=200, raises: Optional[Exception] = None, raw: Optional[bytes] = None):
        self.requests = []
        self._response, self._status, self._raises, self._raw = response, status, raises, raw

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._raises:
            raise self._raises
        if self._raw is not None:
            return httpx.Response(self._status, content=self._raw)
        return httpx.Response(self._status, json=self._response if self._response is not None else good_response())


def gateway(recorder: Recorder, **kwargs) -> RazorpayGateway:
    return RazorpayGateway(
        RazorpayCredentials(key_id=KEY_ID, key_secret=SECRET),
        transport=httpx.MockTransport(recorder),
        **kwargs,
    )


def create(g: RazorpayGateway, **overrides):
    args = dict(amount_paise=40621, currency="INR", receipt="PRM-2026-000123-1", notes={"pramanika_order_id": "x"})
    args.update(overrides)
    return g.create_order(**args)


class RequestShapeTests(unittest.TestCase):
    def setUp(self):
        self.rec = Recorder()
        self.order = create(gateway(self.rec))
        self.request = self.rec.requests[0]

    def test_it_posts_to_the_orders_endpoint(self):
        self.assertEqual(self.request.method, "POST")
        self.assertEqual(str(self.request.url), "https://api.razorpay.com/v1/orders")

    def test_it_authenticates_with_basic_auth(self):
        header = self.request.headers["Authorization"]
        self.assertTrue(header.startswith("Basic "))
        self.assertEqual(base64.b64decode(header[6:]).decode(), f"{KEY_ID}:{SECRET}")

    def test_the_body_carries_amount_in_paise_as_an_integer(self):
        body = json.loads(self.request.content)
        self.assertEqual(body["amount"], 40621)
        self.assertIsInstance(body["amount"], int)
        self.assertEqual(body["currency"], "INR")
        self.assertEqual(body["receipt"], "PRM-2026-000123-1")
        self.assertEqual(body["notes"], {"pramanika_order_id": "x"})

    def test_the_secret_is_only_ever_in_the_authorization_header(self):
        self.assertNotIn(SECRET.encode(), self.request.content)
        self.assertNotIn(SECRET, str(self.request.url))

    def test_the_result_is_a_small_typed_object(self):
        self.assertEqual(self.order, GatewayOrder(id="order_ABC123", amount_paise=40621, currency="INR"))

    def test_the_base_url_and_timeout_are_configurable(self):
        rec = Recorder()
        g = gateway(rec, base_url="https://example.test/v9/", timeout_seconds=3)
        create(g)
        self.assertEqual(str(rec.requests[0].url), "https://example.test/v9/orders")
        self.assertEqual(g._timeout.read, 3)
        self.assertEqual(g._timeout.connect, 3)  # never longer than the total

    def test_the_timeouts_are_really_applied_to_the_request(self):
        """Not just stored on the gateway: the request that goes out carries them."""
        from app.core.config import settings

        rec = Recorder()
        create(gateway(rec))
        sent = rec.requests[0].extensions["timeout"]
        self.assertEqual(sent["read"], settings.RAZORPAY_TIMEOUT_SECONDS)
        self.assertEqual(sent["write"], settings.RAZORPAY_TIMEOUT_SECONDS)
        self.assertEqual(sent["connect"], min(5.0, settings.RAZORPAY_TIMEOUT_SECONDS))

        rec = Recorder()
        create(gateway(rec, timeout_seconds=2))
        self.assertEqual(rec.requests[0].extensions["timeout"], {"connect": 2, "read": 2, "write": 2, "pool": 2})

    def test_every_phase_of_the_request_has_a_timeout(self):
        t = gateway(Recorder())._timeout
        for value in (t.connect, t.read, t.write, t.pool):
            self.assertIsNotNone(value)

    def test_the_gateway_exposes_only_the_public_key_id(self):
        g = gateway(Recorder())
        self.assertEqual(g.key_id, KEY_ID)
        self.assertNotIn(SECRET, repr(g))
        self.assertNotIn(SECRET, str(vars(g).get("key_id")))

    def test_an_over_long_receipt_is_refused_before_any_request(self):
        rec = Recorder()
        with self.assertRaises(ValueError):
            create(gateway(rec), receipt="x" * (MAX_RECEIPT_LENGTH + 1))
        self.assertEqual(rec.requests, [])

    def test_it_does_not_retry(self):
        rec = Recorder(status=500, response={"error": {"code": "SERVER_ERROR"}})
        with self.assertLogs("app.services.razorpay_gateway", level=logging.ERROR), self.assertRaises(PaymentGatewayError):
            create(gateway(rec))
        self.assertEqual(len(rec.requests), 1)


class FailureTests(unittest.TestCase):
    """Every way Razorpay can misbehave ends as PaymentGatewayError, and the
    log never contains the secret."""

    def run_failing(self, recorder: Recorder, fetch: bool = False, **overrides):
        with self.assertLogs("app.services.razorpay_gateway", level=logging.ERROR) as logs:
            with self.assertRaises(PaymentGatewayError) as ctx:
                if fetch:
                    gateway(recorder).fetch_payment("pay_ABC123")
                else:
                    create(gateway(recorder), **overrides)
        text = "\n".join(logs.output)
        for secret in (SECRET, "Basic ", base64.b64encode(f"{KEY_ID}:{SECRET}".encode()).decode()):
            self.assertNotIn(secret, text)
        self.assertEqual(ctx.exception.http_status, 502)
        # The customer-facing message is generic.
        self.assertNotIn("razorpay", ctx.exception.message.lower())
        return text

    def test_a_timeout(self):
        self.run_failing(Recorder(raises=httpx.ReadTimeout("slow")))

    def test_a_connection_error(self):
        self.run_failing(Recorder(raises=httpx.ConnectError("no route")))

    def test_a_bad_request_logs_the_code_but_not_the_credentials(self):
        text = self.run_failing(Recorder(status=400, response={"error": {"code": "BAD_REQUEST_ERROR", "description": "Order amount less than minimum amount allowed"}}))
        self.assertIn("BAD_REQUEST_ERROR", text)
        self.assertIn("HTTP 400", text)

    def test_wrong_credentials(self):
        text = self.run_failing(Recorder(status=401, response={"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}}))
        self.assertIn("HTTP 401", text)

    def test_a_server_error_with_a_non_json_body(self):
        self.run_failing(Recorder(status=502, raw=b"<html>Bad gateway</html>"))

    def test_a_2xx_that_is_not_json(self):
        self.run_failing(Recorder(raw=b"ok"))

    def test_a_2xx_json_that_is_not_an_object(self):
        self.run_failing(Recorder(response=[1, 2, 3]))

    def test_a_response_without_an_order_id(self):
        self.run_failing(Recorder(response=good_response(id=None)))

    def test_an_order_id_that_does_not_look_like_one(self):
        for bad in ("pay_123", "", 12345):
            with self.subTest(id=bad):
                self.run_failing(Recorder(response=good_response(id=bad)))

    def test_a_response_amount_that_differs_from_what_we_asked_for(self):
        self.run_failing(Recorder(response=good_response(amount=40622)))

    def test_a_boolean_amount_is_not_the_number_one(self):
        self.run_failing(Recorder(response=good_response(amount=True)), amount_paise=1)

    def test_a_response_currency_that_differs(self):
        self.run_failing(Recorder(response=good_response(currency="USD")))

    def test_an_order_that_is_not_in_the_created_state(self):
        self.run_failing(Recorder(response=good_response(status="paid")))

    def test_a_logged_description_is_clipped(self):
        text = self.run_failing(Recorder(status=400, response={"error": {"code": "X", "description": "d" * 5000}}))
        self.assertLess(len(text), 1000)


def good_payment(**overrides):
    body = {"id": "pay_ABC123", "entity": "payment", "amount": 40621, "currency": "INR", "status": "captured",
            "order_id": "order_XYZ789", "method": "upi"}
    body.update(overrides)
    return body


class FetchPaymentTests(unittest.TestCase):
    def test_it_gets_the_payment_with_basic_auth_and_no_body(self):
        rec = Recorder(good_payment())
        payment = gateway(rec).fetch_payment("pay_ABC123")
        request = rec.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(str(request.url), "https://api.razorpay.com/v1/payments/pay_ABC123")
        self.assertEqual(request.content, b"")
        self.assertEqual(base64.b64decode(request.headers["Authorization"][6:]).decode(), f"{KEY_ID}:{SECRET}")
        self.assertEqual(payment.id, "pay_ABC123")
        self.assertEqual(payment.order_id, "order_XYZ789")
        self.assertEqual(payment.amount_paise, 40621)
        self.assertEqual(payment.currency, "INR")
        self.assertEqual(payment.status, "captured")

    def test_it_reports_razorpays_status_word_unchanged(self):
        for status in ("created", "authorized", "captured", "refunded", "failed"):
            with self.subTest(status=status):
                self.assertEqual(gateway(Recorder(good_payment(status=status))).fetch_payment("pay_ABC123").status, status)

    def test_only_well_formed_payment_ids_are_ever_put_in_the_url(self):
        for bad in ("", "order_1", "pay_", "pay_x/../orders", "pay_x?x=1", "pay_x y", "pay_" + "a" * 101, "../pay_x", None, "pay_\u00e9"):
            rec = Recorder(good_payment())
            with self.subTest(payment_id=bad), self.assertRaises(ValueError):
                gateway(rec).fetch_payment(bad)
            self.assertEqual(rec.requests, [])

    def test_a_response_about_a_different_payment_is_rejected(self):
        FailureTests.run_failing(self, Recorder(good_payment(id="pay_OTHER")), fetch=True)

    def test_a_response_with_missing_or_malformed_fields_is_rejected(self):
        for overrides in ({"order_id": None}, {"order_id": ""}, {"amount": "40621"}, {"amount": True}, {"amount": None},
                          {"currency": None}, {"status": None}, {"status": 5}):
            with self.subTest(overrides=overrides):
                FailureTests.run_failing(self, Recorder(good_payment(**overrides)), fetch=True)

    def test_errors_are_generic_and_leak_nothing(self):
        for rec in (Recorder(raises=httpx.ReadTimeout("slow")), Recorder(raises=httpx.ConnectError("x")),
                    Recorder(status=404, response={"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}}),
                    Recorder(status=500, raw=b"oops"), Recorder(raw=b"not json")):
            with self.subTest():
                FailureTests.run_failing(self, rec, fetch=True)

    def test_it_does_not_retry(self):
        rec = Recorder(status=500, response={"error": {"code": "SERVER_ERROR"}})
        with self.assertLogs("app.services.razorpay_gateway", level=logging.ERROR), self.assertRaises(PaymentGatewayError):
            gateway(rec).fetch_payment("pay_ABC123")
        self.assertEqual(len(rec.requests), 1)


class GatewaySignatureTests(unittest.TestCase):
    def test_the_gateway_checks_signatures_with_its_own_secret(self):
        from app.services.razorpay_signature import checkout_signature

        g = gateway(Recorder())
        good = checkout_signature(SECRET, "order_A", "pay_B")
        self.assertTrue(g.verify_checkout_signature("order_A", "pay_B", good))
        self.assertFalse(g.verify_checkout_signature("order_A", "pay_B", checkout_signature("wrong", "order_A", "pay_B")))
        self.assertFalse(g.verify_checkout_signature("order_A", "pay_C", good))


class ToPaiseTests(unittest.TestCase):
    """The money -> paise conversion (app.core.money.to_paise)."""

    def test_exact_conversions(self):
        from decimal import Decimal

        cases = [
            (Decimal("406.21"), 40621),
            (406.21, 40621),            # a float that prints cleanly is fine
            ("406.21", 40621),
            (Decimal("0.01"), 1),
            (Decimal("0.10"), 10),
            (1, 100),
            (Decimal("406.2100"), 40621),   # trailing zeros are not extra precision
            (Decimal("99999.99"), 9999999),
            (Decimal("1E+2"), 10000),
            (Decimal("19.99"), 1999),       # 19.99 * 100 is 1998.9999999999998 in float arithmetic
            (Decimal("1.15"), 115),         # 1.15 * 100 is 114.99999999999999 in float arithmetic
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                result = to_paise(value)
                self.assertEqual(result, expected)
                self.assertIs(type(result), int)

    def test_float_arithmetic_would_have_been_wrong(self):
        # Documents WHY the conversion is in Decimal.
        self.assertNotEqual(int(19.99 * 100), 1999)
        self.assertEqual(to_paise("19.99"), 1999)

    def test_refuses_amounts_that_are_not_positive(self):
        from decimal import Decimal

        for value in (0, 0.0, Decimal("0.00"), -1, Decimal("-0.01")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_paise(value)

    def test_refuses_more_than_two_decimal_places_instead_of_rounding(self):
        from decimal import Decimal

        for value in (Decimal("1.005"), Decimal("406.211"), "0.001", 0.1 + 0.2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_paise(value)

    def test_refuses_nan_and_infinity(self):
        from decimal import Decimal

        for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_paise(value)


if __name__ == "__main__":
    unittest.main()
