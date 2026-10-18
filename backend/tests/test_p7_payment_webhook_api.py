"""Phase 7 / Milestone 7: POST /api/payments/webhook over HTTP (PostgreSQL integration)."""

import json
import logging
from unittest import mock

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import payments as payments_api
from app.core.config import settings
from app.models import Order, OrderPaymentStatus, OrderStatus, Payment, PaymentTransactionStatus as S, PaymentWebhookEvent
from app.services.payment_webhook_service import MAX_BODY_BYTES
from app.services.razorpay_signature import webhook_signature
from tests.pg_support import PostgresTestCase, new_session
from tests.test_p7_payment_api import build_app
from tests.test_p7_payment_webhook import EMAIL, PAY, RZ, SECRET, make_body

URL = "/api/payments/webhook"


class WebhookApiCase(PostgresTestCase):
    def setUp(self):
        super().setUp()
        app = build_app()
        app.dependency_overrides[payments_api.get_webhook_secret] = lambda: SECRET
        self.client = TestClient(app)
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.order = self.make_order(self.user, [(self.product, 1)])
        self.payment = self.make_payment(self.order, gateway_order_id=RZ)

    def post(self, raw=None, *, signature=None, event_id="evt_http_1", headers=None, client=None, secret=SECRET, content_type="application/json"):
        raw = make_body() if raw is None else raw
        h = {"Content-Type": content_type}
        if signature is not False:
            h["X-Razorpay-Signature"] = webhook_signature(secret, raw) if signature is None else signature
        if event_id:
            h["X-Razorpay-Event-Id"] = event_id
        h.update(headers or {})
        return (client or self.client).post(URL, content=raw, headers=h)

    def order_row(self):
        with new_session() as s:
            row = s.get(Order, self.order.id)
            s.expunge(row)
            return row

    def payment_row(self):
        with new_session() as s:
            row = s.get(Payment, self.payment.id)
            s.expunge(row)
            return row

    def event_count(self):
        with new_session() as s:
            return s.query(PaymentWebhookEvent).count()


class AcceptedTests(WebhookApiCase):
    def test_a_signed_capture_pays_the_order_with_no_login(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "message": "Event received.", "data": None})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        o = self.order_row()
        self.assertEqual((o.status, o.payment_status), (OrderStatus.CONFIRMED, OrderPaymentStatus.PAID))
        self.assertEqual(self.payment_row().status, S.CAPTURED)

    def test_a_login_token_is_not_needed_and_not_a_substitute_for_the_signature(self):
        response = self.post(signature="0" * 64, headers={"Authorization": "Bearer anything"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_the_same_event_id_again_is_acknowledged_and_does_nothing(self):
        self.post()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Event already processed.")
        self.assertEqual(self.event_count(), 1)

    def test_a_retry_with_a_new_event_id_is_harmless(self):
        self.post(event_id="evt_a")
        self.assertEqual(self.post(event_id="evt_b").status_code, 200)
        self.assertEqual(self.event_count(), 2)
        self.assertEqual(self.payment_row().status, S.CAPTURED)

    def test_events_we_ignore_are_still_a_200_so_razorpay_stops_retrying(self):
        for raw in (make_body("refund.processed"), make_body(rz="order_NOTOURS"), make_body("payment.failed", amount=1)):
            with self.subTest(raw=raw[:60]):
                self.assertEqual(self.post(raw=raw, event_id=f"evt_{len(raw)}_{raw[-12:].hex()}").status_code, 200)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_the_content_type_does_not_matter_only_the_bytes_do(self):
        self.assertEqual(self.post(content_type="text/plain").status_code, 200)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PAID)

    def test_the_signature_is_over_the_raw_bytes_so_pretty_printed_json_works_when_signed_as_sent(self):
        raw = json.dumps(json.loads(make_body()), indent=4, sort_keys=True).encode()
        self.assertEqual(self.post(raw=raw).status_code, 200)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PAID)

    def test_a_late_payment_after_a_cancel_is_a_200_and_flagged(self):
        from app.services.order_service import OrderService

        with new_session() as s:
            OrderService(s).cancel_order(self.user.id, self.order.id)
        self.assertEqual(self.post().status_code, 200)  # not a 4xx: retrying cannot help
        p = self.payment_row()
        self.assertEqual((p.status, p.refund_required), (S.CAPTURED, True))
        self.assertEqual(self.order_row().status, OrderStatus.CANCELLED)


class RejectedTests(WebhookApiCase):
    def assert_untouched(self):
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)
        self.assertEqual(self.payment_row().status, S.INITIATED)
        self.assertEqual(self.event_count(), 0)

    def test_a_wrong_signature_is_a_400_and_changes_nothing(self):
        response = self.post(signature="f" * 64)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"success": False, "message": "Invalid webhook signature."})
        self.assert_untouched()

    def test_a_missing_signature_header_is_a_400(self):
        self.assertEqual(self.post(signature=False).status_code, 400)
        self.assert_untouched()

    def test_a_body_changed_after_signing_is_a_400(self):
        raw = make_body()
        self.assertEqual(self.post(raw=raw.replace(b"40621", b"1"), signature=webhook_signature(SECRET, raw)).status_code, 400)
        self.assert_untouched()

    def test_a_reserialised_body_does_not_match_the_original_signature(self):
        raw = make_body()
        reserialised = json.dumps(json.loads(raw), indent=2).encode()
        self.assertEqual(self.post(raw=reserialised, signature=webhook_signature(SECRET, raw)).status_code, 400)
        self.assert_untouched()

    def test_the_checkout_api_secret_is_not_the_webhook_secret(self):
        raw = make_body()
        self.assertEqual(self.post(raw=raw, signature=webhook_signature("the-key-secret", raw)).status_code, 400)
        self.assert_untouched()

    def test_a_signed_body_that_is_not_an_event_is_a_400(self):
        raw = b'{"nothing": true}'
        self.assertEqual(self.post(raw=raw).status_code, 400)
        self.assert_untouched()

    def test_an_oversized_body_is_a_413(self):
        raw = b"x" * (MAX_BODY_BYTES + 1)
        self.assertEqual(self.post(raw=raw).status_code, 413)
        self.assert_untouched()

    def test_a_declared_huge_body_is_refused_without_reading_it(self):
        with mock.patch("starlette.requests.Request.body", side_effect=AssertionError("the body was read")):
            response = self.post(raw=b"{}", headers={"Content-Length": str(MAX_BODY_BYTES + 1)})
        self.assertIn(response.status_code, (400, 413))  # a lying length may also be refused by the HTTP layer
        if response.status_code == 413:
            self.assertEqual(response.json()["message"], "Webhook payload is too large.")

    def test_only_post_is_allowed(self):
        for method in ("get", "put", "delete", "patch"):
            self.assertEqual(getattr(self.client, method)(URL).status_code, 405, method)

    def test_a_failure_while_processing_is_a_5xx_so_razorpay_retries_and_the_retry_succeeds(self):
        client = TestClient(self.client.app, raise_server_exceptions=False)
        with mock.patch("app.services.payment_webhook_service.PaymentWebhookService._apply", side_effect=RuntimeError("db down")):
            response = self.post(client=client, event_id="evt_flaky")
        self.assertEqual(response.status_code, 500)
        self.assert_untouched()
        self.assertEqual(self.post(event_id="evt_flaky").status_code, 200)
        self.assertEqual(self.payment_row().status, S.CAPTURED)


class ConfigurationTests(WebhookApiCase):
    """Through the REAL secret lookup (settings), not the test override."""

    def real_client(self):
        app = build_app()  # no webhook-secret override
        return TestClient(app, raise_server_exceptions=False)

    def test_without_a_configured_secret_the_endpoint_is_a_generic_503(self):
        with mock.patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", SecretStr("")):
            response = self.post(client=self.real_client())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["message"], "Online payments are not available right now. Please try again later.")
        self.assertNotIn("RAZORPAY", response.text)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PENDING)

    def test_a_whitespace_only_secret_counts_as_missing(self):
        with mock.patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", SecretStr("   ")):
            self.assertEqual(self.post(client=self.real_client()).status_code, 503)

    def test_with_the_secret_configured_a_correctly_signed_event_is_accepted(self):
        with mock.patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", SecretStr(SECRET)):
            self.assertEqual(self.post(client=self.real_client()).status_code, 200)
        self.assertEqual(self.order_row().payment_status, OrderPaymentStatus.PAID)

    def test_the_configured_secret_with_surrounding_spaces_is_trimmed_like_everywhere_else(self):
        with mock.patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", SecretStr(f"  {SECRET}\n")):
            self.assertEqual(self.post(client=self.real_client()).status_code, 200)

    def test_the_secret_never_appears_in_any_response_or_log(self):
        with mock.patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", SecretStr(SECRET)):
            with self.assertLogs(level="DEBUG") as logs:
                logging.getLogger("t").debug("x")
                ok = self.post(client=self.real_client())
                bad = self.post(client=self.real_client(), signature="0" * 64, event_id="evt_bad")
        for text in (ok.text, bad.text, str(ok.headers), str(bad.headers), "\n".join(logs.output)):
            self.assertNotIn(SECRET, text)
            self.assertNotIn(EMAIL, text)

    def test_the_webhook_route_exists_exactly_once_and_is_not_behind_login(self):
        routes = [r for r in self.client.app.routes if getattr(r, "path", "") == URL]
        self.assertEqual(len(routes), 1)
        self.assertEqual(sorted(routes[0].methods), ["POST"])
        self.assertEqual([d.call for d in routes[0].dependant.dependencies if "user" in getattr(d.call, "__name__", "")], [])
