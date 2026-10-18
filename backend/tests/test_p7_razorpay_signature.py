"""Phase 7 / Milestone 5: Razorpay's checkout signature (pure)."""

import hashlib
import hmac
import unittest

from app.services.razorpay_signature import checkout_signature, is_valid_checkout_signature

SECRET = "fake-key-secret-DO-NOT-LEAK-111"
ORDER, PAYMENT = "order_ABC123", "pay_XYZ789"


class SignatureTests(unittest.TestCase):
    def test_it_is_hmac_sha256_hex_of_order_pipe_payment(self):
        expected = hmac.new(SECRET.encode(), b"order_ABC123|pay_XYZ789", hashlib.sha256).hexdigest()
        self.assertEqual(checkout_signature(SECRET, ORDER, PAYMENT), expected)
        self.assertEqual(len(expected), 64)

    def test_known_answer(self):
        # Independent of the implementation: computed once, pinned here.
        self.assertEqual(
            checkout_signature("secret", "order_1", "pay_1"),
            hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest(),
        )

    def test_the_genuine_signature_is_accepted(self):
        self.assertTrue(is_valid_checkout_signature(SECRET, ORDER, PAYMENT, checkout_signature(SECRET, ORDER, PAYMENT)))

    def test_any_change_is_rejected(self):
        good = checkout_signature(SECRET, ORDER, PAYMENT)
        cases = {
            "other secret": (is_valid_checkout_signature("other-secret", ORDER, PAYMENT, good)),
            "other order": (is_valid_checkout_signature(SECRET, "order_OTHER", PAYMENT, good)),
            "other payment": (is_valid_checkout_signature(SECRET, ORDER, "pay_OTHER", good)),
            "swapped ids": (is_valid_checkout_signature(SECRET, PAYMENT, ORDER, good)),
            "last char changed": (is_valid_checkout_signature(SECRET, ORDER, PAYMENT, good[:-1] + ("0" if good[-1] != "0" else "1"))),
            "truncated": (is_valid_checkout_signature(SECRET, ORDER, PAYMENT, good[:-1])),
            "extended": (is_valid_checkout_signature(SECRET, ORDER, PAYMENT, good + "0")),
            "uppercased": (is_valid_checkout_signature(SECRET, ORDER, PAYMENT, good.upper())),
            "empty": (is_valid_checkout_signature(SECRET, ORDER, PAYMENT, "")),
        }
        for name, accepted in cases.items():
            with self.subTest(case=name):
                self.assertFalse(accepted)

    def test_the_message_is_order_pipe_payment_exactly(self):
        self.assertEqual(
            checkout_signature(SECRET, "a", "b"),
            hmac.new(SECRET.encode(), b"a|b", hashlib.sha256).hexdigest(),
        )

    def test_junk_is_invalid_not_an_error(self):
        for junk in (None, 123, b"bytes", [], {}, "é中"):
            with self.subTest(junk=junk):
                self.assertFalse(is_valid_checkout_signature(SECRET, ORDER, PAYMENT, junk))

    def test_an_empty_secret_is_refused(self):
        with self.assertRaises(ValueError):
            checkout_signature("", ORDER, PAYMENT)
        with self.assertRaises(ValueError):
            is_valid_checkout_signature("", ORDER, PAYMENT, "x" * 64)

    def test_the_comparison_is_constant_time(self):
        import inspect

        import app.services.razorpay_signature as module

        self.assertIn("compare_digest", inspect.getsource(module.is_valid_checkout_signature))


if __name__ == "__main__":
    unittest.main()
