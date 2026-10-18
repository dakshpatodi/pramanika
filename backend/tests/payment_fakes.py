"""Test doubles for the payment gateway. Nothing here touches the network."""

import threading
import time
from typing import Dict, List, Mapping, Optional

from app.core.exceptions import PaymentGatewayError
from app.services.razorpay_gateway import GatewayOrder, GatewayPayment
from app.services.razorpay_signature import checkout_signature, is_valid_checkout_signature

FAKE_SECRET = "fake-key-secret-DO-NOT-LEAK-111"


def sign(razorpay_order_id: str, razorpay_payment_id: str, secret: str = FAKE_SECRET) -> str:
    """The signature Razorpay Checkout would return (for tests)."""
    return checkout_signature(secret, razorpay_order_id, razorpay_payment_id)


class FakeGateway:
    """Stands in for `RazorpayGateway`. Records every call; thread-safe, so
    concurrency tests can count how many Razorpay calls were really made.

    `register_payment` sets what Razorpay "knows" about a payment; the
    signature check is the real HMAC with a fake secret."""

    def __init__(
        self,
        *,
        key_id: str = "rzp_test_FAKEKEYID000000",
        delay: float = 0.0,
        fail: bool = False,
        fetch_fails: bool = False,
        secret: str = FAKE_SECRET,
    ):
        self.key_id = key_id
        self.delay = delay
        self.fail = fail
        self.fetch_fails = fetch_fails
        self._secret = secret
        self.calls: List[dict] = []
        self.fetches: List[str] = []
        self.payments: Dict[str, GatewayPayment] = {}
        self._lock = threading.Lock()
        self._n = 0

    def create_order(self, *, amount_paise: int, currency: str, receipt: str, notes: Mapping[str, str]) -> GatewayOrder:
        if self.delay:
            time.sleep(self.delay)  # widens the window two racing requests would both pass through
        with self._lock:
            self._n += 1
            n = self._n
            self.calls.append(dict(amount_paise=amount_paise, currency=currency, receipt=receipt, notes=dict(notes)))
        if self.fail:
            raise PaymentGatewayError()
        return GatewayOrder(id=f"order_FAKE{n:06d}", amount_paise=amount_paise, currency=currency)

    # --- payments (M5) ---

    def register_payment(
        self, payment_id: str, *, order_id: str, amount_paise: int, status: str = "captured", currency: str = "INR"
    ) -> GatewayPayment:
        payment = GatewayPayment(id=payment_id, order_id=order_id, amount_paise=amount_paise, currency=currency, status=status)
        self.payments[payment_id] = payment
        return payment

    def fetch_payment(self, payment_id: str) -> GatewayPayment:
        if self.delay:
            time.sleep(self.delay)
        with self._lock:
            self.fetches.append(payment_id)
        if self.fetch_fails or payment_id not in self.payments:
            raise PaymentGatewayError()
        return self.payments[payment_id]

    def verify_checkout_signature(self, razorpay_order_id: str, razorpay_payment_id: str, signature: str) -> bool:
        return is_valid_checkout_signature(self._secret, razorpay_order_id, razorpay_payment_id, signature)
