"""
Phase 7 / Milestone 12: regression tests for what the security review found.

Each class pins one finding, so it cannot quietly come back:

  1. the webhook size cap also holds for chunked uploads (no Content-Length)
  2. Razorpay ids match end-to-end: a trailing newline is not part of an id
  3. a few stuck orders cannot keep the orders behind them from expiring
  4. a weak webhook secret / a plain-http Razorpay address stops the app starting
  5. captured money that cannot be booked raises a CRITICAL alert (and still rolls back)
"""

import asyncio
import logging
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.api import payments as payments_api
from app.core.exceptions import WebhookTooLargeError
from app.models import Order, OrderStatus, PaymentTransactionStatus as S
from app.services.order_expiry_service import ExpireOutcome, OrderExpiryService
from app.services.payment_webhook_service import MAX_BODY_BYTES
from app.services.razorpay_gateway import RazorpayGateway
from app.services.razorpay_signature import webhook_signature
from app.services.razorpay_webhook import parse_webhook
from app.services.reservation_service import ReservationInvariantError, ReservationService
from tests.payment_fakes import FakeGateway, sign
from tests.pg_support import PostgresTestCase, new_session
from tests.test_p7_order_expiry import MINUTE, NOW, ExpiryCase, clock
from tests.test_p7_payment_api import KEY_ID as GATEWAY_KEY_ID, build_app
from tests.test_p7_payment_config import KEY_SECRET, WEBHOOK_SECRET, configured, make_settings
from tests.test_p7_payment_webhook import PAY, RZ, SECRET, make_body


# --- 1. chunked bodies ----------------------------------------------------------------


class _FakeRequest:
    """Just enough of a Starlette request: headers and a counted body stream."""

    def __init__(self, chunks, headers=None):
        self.headers = headers or {}
        self.chunks = chunks
        self.pulled = 0

    async def stream(self):
        for chunk in self.chunks:
            self.pulled += 1
            yield chunk


class ChunkedBodyCapTests(unittest.TestCase):
    def read(self, request):
        return asyncio.run(payments_api._read_capped_body(request))

    def test_a_body_without_a_declared_length_is_cut_off_at_the_cap(self):
        chunk = b"x" * 16_384
        request = _FakeRequest([chunk] * 1000)  # 16 MB offered, no Content-Length
        with self.assertRaises(WebhookTooLargeError):
            self.read(request)
        self.assertLessEqual(request.pulled, MAX_BODY_BYTES // len(chunk) + 1)  # stopped reading, did not buffer it all

    def test_a_lying_content_length_does_not_help(self):
        request = _FakeRequest([b"x" * (MAX_BODY_BYTES + 1)], headers={"content-length": "10"})
        with self.assertRaises(WebhookTooLargeError):
            self.read(request)

    def test_a_big_declared_length_is_refused_before_reading_anything(self):
        request = _FakeRequest([b"x"], headers={"content-length": str(MAX_BODY_BYTES + 1)})
        with self.assertRaises(WebhookTooLargeError):
            self.read(request)
        self.assertEqual(request.pulled, 0)

    def test_a_body_exactly_at_the_cap_is_accepted_and_returned_whole(self):
        pieces = [b"a" * 1000, b"b" * (MAX_BODY_BYTES - 1000)]
        self.assertEqual(self.read(_FakeRequest(pieces)), b"".join(pieces))

    def test_an_empty_body_is_just_empty(self):
        self.assertEqual(self.read(_FakeRequest([])), b"")


class ChunkedWebhookHttpTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        app = build_app()
        app.dependency_overrides[payments_api.get_webhook_secret] = lambda: SECRET
        self.client = TestClient(app)

    def chunks(self, data, size=8192):
        for i in range(0, len(data), size):
            yield data[i:i + size]

    def test_an_oversized_chunked_upload_gets_413(self):
        response = self.client.post("/api/payments/webhook", content=self.chunks(b"x" * (MAX_BODY_BYTES + 5000)),
                                    headers={"X-Razorpay-Signature": "0" * 64})
        self.assertEqual(response.status_code, 413)

    def test_a_normal_chunked_webhook_still_works(self):
        user = self.make_user()
        product = self.make_product(price="406.21", stock=5)
        order = self.make_order(user, [(product, 1)])
        self.make_payment(order, gateway_order_id=RZ)
        raw = make_body()
        response = self.client.post("/api/payments/webhook", content=self.chunks(raw, 64),
                                    headers={"X-Razorpay-Signature": webhook_signature(SECRET, raw), "X-Razorpay-Event-Id": "evt_chunked_ok"})
        self.assertEqual(response.status_code, 200, response.text)
        with new_session() as s:
            self.assertEqual(s.get(Order, order.id).payment_status.value, "paid")


# --- 2. ids match end to end ----------------------------------------------------------------


class IdPatternTests(unittest.TestCase):
    def test_the_gateway_refuses_an_id_with_a_trailing_newline_before_building_a_url(self):
        gateway = RazorpayGateway(mock.Mock(key_id=GATEWAY_KEY_ID, key_secret="x"), transport=mock.Mock())
        for bad in ("pay_abc\n", "pay_abc\r\n", "pay_abc ", "pay_abc/../orders", "pay_", "", None, "pay_" + "a" * 101):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    gateway.fetch_payment(bad)

    def test_a_webhook_with_a_newline_in_an_id_is_not_actionable(self):
        for payment_id, order_id in (("pay_a\n", "order_X"), ("pay_a", "order_X\n"), ("pay_a\n", "order_X\n")):
            with self.subTest(payment_id=payment_id, order_id=order_id):
                event = parse_webhook(make_body(pid=payment_id, rz=order_id))
                self.assertIsNone(event.gateway_payment_id if "\n" in payment_id else event.gateway_order_id)

    def test_well_formed_ids_still_parse(self):
        event = parse_webhook(make_body(pid="pay_Abc123", rz="order_Xyz789"))
        self.assertEqual((event.gateway_payment_id, event.gateway_order_id), ("pay_Abc123", "order_Xyz789"))


# --- 3. the expiry sweep cannot be blocked by stuck orders -----------------------------------------


class StuckOrdersTests(ExpiryCase):
    def setUp(self):
        super().setUp()
        # self.order is the oldest due order; add three more, each due a little later
        self.later = [self.make_due_order(coupon=False, expires_at=NOW - (4 - i) * MINUTE) for i in range(3)]
        with new_session() as s:
            s.query(Order).filter(Order.id == self.order.id).update({Order.expires_at: NOW - 60 * MINUTE})
            s.commit()

    def status(self, order):
        with new_session() as s:
            return s.get(Order, order.id).status

    def test_orders_that_always_fail_do_not_hold_up_the_ones_behind_them(self):
        stuck = {self.order.id, self.later[0].id}
        real = OrderExpiryService._expire

        def flaky(service, order_id):
            if order_id in stuck:
                raise RuntimeError("a bad row")
            return real(service, order_id)

        with mock.patch.object(OrderExpiryService, "_expire", flaky):
            run = self.expire(batch_size=2)  # the first batch is nothing but stuck orders
        self.assertEqual((run.expired, run.failed), (2, 2))
        self.assertEqual([self.status(self.later[1]), self.status(self.later[2])], [OrderStatus.CANCELLED] * 2)
        self.assertEqual([self.status(self.order), self.status(self.later[0])], [OrderStatus.PENDING] * 2)  # tried again next pass

    def test_busy_orders_do_not_hold_up_the_ones_behind_them(self):
        holders = []
        try:
            for stuck in (self.order, self.later[0]):
                holder = new_session()
                holders.append(holder)
                holder.query(Order).filter(Order.id == stuck.id).with_for_update().one()
            run = self.expire(batch_size=2)
            self.assertEqual((run.expired, run.busy), (2, 2))
            self.assertEqual([self.status(self.later[1]), self.status(self.later[2])], [OrderStatus.CANCELLED] * 2)
        finally:
            for holder in holders:
                holder.rollback()
                holder.close()
        self.assertEqual(self.expire(batch_size=2).expired, 2)  # and the freed ones go on the next pass

    def test_each_order_is_tried_at_most_once_per_pass(self):
        calls = []
        real = OrderExpiryService._expire

        def counting(service, order_id):
            calls.append(order_id)
            raise RuntimeError("always fails")

        with mock.patch.object(OrderExpiryService, "_expire", counting):
            run = self.expire(batch_size=1)
        self.assertEqual(len(calls), len(set(calls)), "an order was retried inside one pass")
        self.assertEqual((run.expired, run.failed), (0, 4))

    def test_the_candidate_list_can_leave_out_the_ones_already_tried(self):
        with new_session() as s:
            service = OrderExpiryService(s, clock=clock)
            everything = service.due_order_ids(10)
            self.assertEqual(len(everything), 4)
            self.assertEqual(service.due_order_ids(10, {everything[0], everything[1]}), everything[2:])
            self.assertEqual(service.due_order_ids(10, set(everything)), [])


# --- 4. settings that make the app unsafe are refused at startup -----------------------------------------


class UnsafeSettingsTests(unittest.TestCase):
    def test_a_short_webhook_secret_is_refused_without_echoing_it(self):
        for short in ("sh0rt-s3cret", "tiny-9917", "q" * 15):
            with self.subTest(secret=short):
                with self.assertRaises(ValueError) as caught:
                    configured(RAZORPAY_WEBHOOK_SECRET=short)
                self.assertIn("too short", str(caught.exception))
                self.assertNotIn(short, str(caught.exception))
                self.assertNotIn(KEY_SECRET, str(caught.exception))  # nor its neighbour

    def test_no_settings_error_ever_prints_a_secret(self):
        """Pydantic's default error text includes the raw input - secrets as typed in .env."""
        broken = (
            dict(RAZORPAY_KEY_ID="not-a-razorpay-key"),
            dict(RAZORPAY_KEY_ID="rzp_live_AbCdEfGh123456"),  # a live key outside production
            dict(RAZORPAY_API_BASE_URL="http://insecure.example"),
            dict(RAZORPAY_WEBHOOK_SECRET=KEY_SECRET),
            dict(RAZORPAY_WEBHOOK_SECRET="short"),
            dict(RAZORPAY_TIMEOUT_SECONDS=0),
        )
        for overrides in broken:
            with self.subTest(overrides=sorted(overrides)):
                with self.assertRaises(ValueError) as caught:
                    configured(**overrides)
                text = str(caught.exception)
                for secret in (KEY_SECRET, WEBHOOK_SECRET, "short"):
                    if secret == "short" and "short" in str(overrides.get("RAZORPAY_WEBHOOK_SECRET", "")):
                        continue  # the word appears in the message itself ("too short")
                    self.assertNotIn(secret, text)
                self.assertNotIn("input_value", text)

    def test_sixteen_characters_is_enough(self):
        self.assertEqual(configured(RAZORPAY_WEBHOOK_SECRET="x" * 16).RAZORPAY_WEBHOOK_SECRET.get_secret_value(), "x" * 16)

    def test_no_webhook_secret_at_all_still_starts_the_app(self):
        # unset is handled elsewhere (the endpoint answers 503); only a WEAK one is dangerous
        make_settings()
        configured(RAZORPAY_WEBHOOK_SECRET="")

    def test_the_webhook_secret_must_differ_from_the_key_secret(self):
        with self.assertRaises(ValueError) as caught:
            configured(RAZORPAY_WEBHOOK_SECRET=KEY_SECRET)
        self.assertIn("must differ", str(caught.exception))
        self.assertNotIn(KEY_SECRET, str(caught.exception))

    def test_the_razorpay_address_must_be_https(self):
        for bad in ("http://api.razorpay.com/v1", "ftp://api.razorpay.com", "api.razorpay.com/v1", "http://localhost.evil.com/v1", "http://127.0.0.1.evil.com"):
            with self.subTest(url=bad):
                with self.assertRaises(ValueError):
                    configured(RAZORPAY_API_BASE_URL=bad)

    def test_https_and_a_local_mock_server_are_fine(self):
        for good in ("https://api.razorpay.com/v1", "https://example.test/v9", "http://localhost:9000/v1", "http://127.0.0.1:8080", "http://localhost"):
            with self.subTest(url=good):
                self.assertEqual(configured(RAZORPAY_API_BASE_URL=good).RAZORPAY_API_BASE_URL, good)

    def test_the_default_still_works(self):
        self.assertTrue(make_settings().RAZORPAY_API_BASE_URL.startswith("https://"))
        configured()


# --- 5. captured money that cannot be booked is loud ----------------------------------------------------


class CapturedButUnbookedTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product(price="406.21", stock=5)
        self.order = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(self.order, gateway_order_id=RZ)
        self.user_id, self.order_id = self.user.id, self.order.id

    def verify(self):
        from app.services.payment_service import PaymentService

        gateway = FakeGateway()
        gateway.register_payment(PAY, order_id=RZ, amount_paise=40621)
        with new_session() as s:
            PaymentService(s, gateway).verify_payment(
                self.user_id, self.order_id, razorpay_order_id=RZ, razorpay_payment_id=PAY, razorpay_signature=sign(RZ, PAY))

    def test_a_broken_reservation_is_logged_as_critical_and_nothing_half_done_is_stored(self):
        with mock.patch.object(ReservationService, "consume_for_order", return_value=False):
            with self.assertLogs("app.services.payment_capture", level="CRITICAL") as logs:
                with self.assertRaises(ReservationInvariantError):
                    self.verify()
        text = "\n".join(logs.output)
        self.assertIn("CAPTURED MONEY NOT RECORDED", text)
        self.assertIn(str(self.order_id), text)
        self.assertIn(PAY, text)
        self.assertNotIn(sign(RZ, PAY), text)  # ids only: never a signature
        with new_session() as s:
            order = s.get(Order, self.order_id)
            self.assertEqual((order.status, order.payment_status.value), (OrderStatus.PENDING, "pending"))
            payment = order.payments[0]
            self.assertEqual(payment.status, S.INITIATED)  # rolled back whole, so Razorpay's retry starts clean

    def test_an_order_that_cannot_be_marked_paid_is_logged_as_critical_too(self):
        from app.repositories.order_repository import OrderRepository

        with mock.patch.object(OrderRepository, "mark_paid", return_value=False):
            with self.assertLogs("app.services.payment_capture", level="CRITICAL") as logs:
                with self.assertRaises(ReservationInvariantError):
                    self.verify()
        self.assertIn("could not be marked paid", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
