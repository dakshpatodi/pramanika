"""
Razorpay's checkout signature (pure - no database, no network).

After a successful payment Razorpay Checkout hands the browser three values.
The signature is

    HMAC-SHA256(key_secret, "<razorpay_order_id>|<razorpay_payment_id>")  as hex

computed with the merchant's key SECRET, which only Razorpay and this server
know. A correct signature therefore proves Razorpay itself issued that
payment id for that Razorpay order - the browser cannot forge one, and
nothing in the browser's own "success" callback is worth anything without it.

The comparison is constant-time (`hmac.compare_digest`) so response timing
cannot be used to guess a signature one character at a time.
"""

import hashlib
import hmac


def checkout_signature(secret: str, razorpay_order_id: str, razorpay_payment_id: str) -> str:
    if not secret:
        raise ValueError("a signing secret is required")
    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def is_valid_checkout_signature(secret: str, razorpay_order_id: str, razorpay_payment_id: str, signature: object) -> bool:
    """True only for the exact signature. Anything that is not a string (or is
    empty) is simply invalid - never an exception."""
    if not isinstance(signature, str) or not signature:
        return False
    expected = checkout_signature(secret, razorpay_order_id, razorpay_payment_id)
    return hmac.compare_digest(expected.encode("utf-8"), signature.encode("utf-8"))


# --- webhooks -----------------------------------------------------------------
#
# A webhook is signed differently from the checkout callback: the HMAC-SHA256
# (hex) is taken over the EXACT BYTES of the request body, with the webhook
# secret configured in the Razorpay dashboard (a different secret from the API
# key secret). It arrives in the `X-Razorpay-Signature` header. The bytes must
# be the raw body: parsing the JSON and re-serialising it changes whitespace
# and key order, and the signature would no longer match.


def webhook_signature(secret: str, raw_body: bytes) -> str:
    if not secret:
        raise ValueError("a signing secret is required")
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def is_valid_webhook_signature(secret: str, raw_body: bytes, signature: object) -> bool:
    """True only for the exact signature of exactly these bytes. A missing,
    empty or non-string header is simply invalid - never an exception."""
    if not isinstance(signature, str) or not signature or not isinstance(raw_body, (bytes, bytearray)):
        return False
    expected = webhook_signature(secret, bytes(raw_body))
    return hmac.compare_digest(expected.encode("utf-8"), signature.encode("utf-8", "replace"))
