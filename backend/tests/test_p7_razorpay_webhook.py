"""Phase 7 / Milestone 7: webhook signature and body parsing (pure - no database)."""

import json
import unittest

from app.services.razorpay_signature import is_valid_webhook_signature, webhook_signature
from app.services.razorpay_webhook import (
    HANDLED_EVENTS,
    MalformedWebhookError,
    parse_webhook,
)

SECRET = "whsec-test-DO-NOT-LEAK-222"


def body(event="payment.captured", **payment):
    entity = {"id": "pay_ABC123", "order_id": "order_XYZ789", "amount": 40621, "currency": "INR", "status": "captured"}
    entity.update(payment)
    return json.dumps({"entity": "event", "event": event, "payload": {"payment": {"entity": entity}}}).encode()


class SignatureTests(unittest.TestCase):
    def test_the_signature_is_hmac_sha256_of_the_exact_bytes(self):
        import hashlib
        import hmac

        raw = b'{"event":"payment.captured"}'
        self.assertEqual(webhook_signature(SECRET, raw), hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest())

    def test_a_genuine_signature_is_valid(self):
        raw = body()
        self.assertTrue(is_valid_webhook_signature(SECRET, raw, webhook_signature(SECRET, raw)))

    def test_one_changed_byte_invalidates_it(self):
        raw = body()
        signature = webhook_signature(SECRET, raw)
        self.assertFalse(is_valid_webhook_signature(SECRET, raw + b" ", signature))
        self.assertFalse(is_valid_webhook_signature(SECRET, raw.replace(b"40621", b"1"), signature))

    def test_reserialising_the_json_breaks_it_which_is_why_the_raw_body_is_used(self):
        raw = body()
        signature = webhook_signature(SECRET, raw)
        reserialised = json.dumps(json.loads(raw), indent=2).encode()
        self.assertFalse(is_valid_webhook_signature(SECRET, reserialised, signature))

    def test_another_secret_is_invalid(self):
        raw = body()
        self.assertFalse(is_valid_webhook_signature(SECRET, raw, webhook_signature("someone-elses-secret", raw)))

    def test_the_checkout_secret_signature_style_is_not_a_webhook_signature(self):
        from app.services.razorpay_signature import checkout_signature

        raw = b"order_X|pay_Y"
        self.assertFalse(is_valid_webhook_signature(SECRET, raw, checkout_signature(SECRET, "order_X", "pay_Y") + "0"))

    def test_missing_or_odd_signatures_are_just_invalid(self):
        raw = body()
        for bad in (None, "", 0, b"abc", ["x"]):
            with self.subTest(bad=bad):
                self.assertFalse(is_valid_webhook_signature(SECRET, raw, bad))
        self.assertFalse(is_valid_webhook_signature(SECRET, "not bytes", "abc"))  # type: ignore[arg-type]

    def test_signing_needs_a_secret(self):
        with self.assertRaises(ValueError):
            webhook_signature("", b"x")

    def test_a_non_ascii_header_is_invalid_not_a_crash(self):
        self.assertFalse(is_valid_webhook_signature(SECRET, body(), "é" * 64))


class ParseTests(unittest.TestCase):
    def test_a_captured_payment(self):
        e = parse_webhook(body())
        self.assertEqual((e.type, e.gateway_order_id, e.gateway_payment_id, e.amount_paise, e.currency),
                         ("payment.captured", "order_XYZ789", "pay_ABC123", 40621, "INR"))
        self.assertIsNone(e.failure_reason)

    def test_a_failed_payment_carries_a_cleaned_reason(self):
        e = parse_webhook(body("payment.failed", error_description="  Card\x00 declined\n by bank  ", status="failed"))
        self.assertEqual(e.failure_reason, "Card declined by bank")

    def test_a_long_reason_is_cut(self):
        self.assertEqual(len(parse_webhook(body("payment.failed", error_description="x" * 9000)).failure_reason), 500)

    def test_order_paid_is_read_from_the_payment_inside_it(self):
        raw = json.dumps({"event": "order.paid", "payload": {
            "order": {"entity": {"id": "order_XYZ789", "amount_paid": 40621}},
            "payment": {"entity": {"id": "pay_ABC123", "order_id": "order_XYZ789", "amount": 40621, "currency": "INR"}}}}).encode()
        e = parse_webhook(raw)
        self.assertEqual((e.type, e.gateway_payment_id, e.gateway_order_id), ("order.paid", "pay_ABC123", "order_XYZ789"))

    def test_events_we_do_not_act_on_carry_only_their_type(self):
        e = parse_webhook(body("refund.processed"))
        self.assertEqual(e.type, "refund.processed")
        self.assertIsNone(e.gateway_payment_id)
        self.assertNotIn("refund.processed", HANDLED_EVENTS)

    def test_badly_shaped_ids_and_amounts_become_none_not_errors(self):
        cases = [
            dict(id="pay_"), dict(id="not_a_payment"), dict(id="pay_" + "A" * 200), dict(id=123), dict(id="pay_A-B"),
            dict(order_id="ord_X"), dict(order_id=None),
        ]
        for case in cases:
            with self.subTest(case=case):
                e = parse_webhook(body(**case))
                key = next(iter(case))
                self.assertIsNone({"id": e.gateway_payment_id, "order_id": e.gateway_order_id}[key])
        for amount in ("40621", 406.21, True, None, [1]):
            with self.subTest(amount=amount):
                self.assertIsNone(parse_webhook(body(amount=amount)).amount_paise)

    def test_a_handled_event_without_a_payment_entity_has_no_ids(self):
        raw = json.dumps({"event": "payment.captured", "payload": {}}).encode()
        e = parse_webhook(raw)
        self.assertEqual((e.gateway_order_id, e.gateway_payment_id, e.amount_paise), (None, None, None))

    def test_unreadable_bodies_are_malformed(self):
        for raw in (b"", b"not json", b"\xff\xfe", b"[]", b'"x"', b"{}", b'{"event": 5}', b'{"event": "  "}', b"null", b"[" * 100000):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(MalformedWebhookError):
                    parse_webhook(raw)

    def test_a_long_event_type_is_cut(self):
        self.assertEqual(len(parse_webhook(json.dumps({"event": "x" * 500}).encode()).type), 100)


if __name__ == "__main__":
    unittest.main()
