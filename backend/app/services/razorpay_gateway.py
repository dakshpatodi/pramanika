"""
The only code that talks to Razorpay's HTTP API.

`PaymentGateway` is the small interface the rest of the backend depends on;
`RazorpayGateway` implements it with httpx. Tests hand `PaymentService` a
fake gateway (or give `RazorpayGateway` an `httpx.MockTransport`), so no
test ever reaches the network or needs a real key.

Rules this module follows:
  * explicit timeouts on every request - a hung gateway must not hang a
    worker thread (or hold a database lock) forever;
  * NO automatic retry: creating a Razorpay order is not idempotent on
    Razorpay's side, so a blind retry after a timeout could create two. The
    caller decides (the customer simply presses Pay again, and our own
    idempotency keeps one Pramanika order -> one open Razorpay order);
  * the response is validated (id, amount, currency) before it is trusted;
  * any failure becomes `PaymentGatewayError` (HTTP 502, generic message).
    The log line carries the HTTP status and Razorpay's error code only -
    never the key, the secret, the Authorization header or the request body.
"""

import logging
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol

import httpx

from app.core.config import settings
from app.core.exceptions import PaymentGatewayError
from app.core.payment_config import RazorpayCredentials
from app.services.razorpay_signature import is_valid_checkout_signature

logger = logging.getLogger(__name__)

MAX_RECEIPT_LENGTH = 40  # Razorpay's limit
CONNECT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class GatewayOrder:
    """What Razorpay told us about the order it just created."""

    id: str
    amount_paise: int
    currency: str


@dataclass(frozen=True)
class GatewayPayment:
    """What Razorpay says about one payment. `status` is Razorpay's own word:
    created / authorized / captured / refunded / failed."""

    id: str
    order_id: str
    amount_paise: int
    currency: str
    status: str


PAYMENT_ID_PATTERN = re.compile(r"^pay_[A-Za-z0-9]{1,100}$")


class PaymentGateway(Protocol):
    key_id: str
    """The public key id (safe for the browser). Never the secret."""

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, notes: Mapping[str, str]
    ) -> GatewayOrder: ...

    def fetch_payment(self, payment_id: str) -> GatewayPayment: ...

    def verify_checkout_signature(self, razorpay_order_id: str, razorpay_payment_id: str, signature: str) -> bool:
        """The key secret never leaves the gateway object: callers ask it to check."""
        ...


class RazorpayGateway:
    def __init__(
        self,
        credentials: RazorpayCredentials,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.key_id = credentials.key_id
        self._secret = credentials.key_secret
        self._base_url = (base_url or settings.RAZORPAY_API_BASE_URL).rstrip("/")
        total = timeout_seconds if timeout_seconds is not None else settings.RAZORPAY_TIMEOUT_SECONDS
        self._timeout = httpx.Timeout(total, connect=min(CONNECT_TIMEOUT_SECONDS, total))
        self._transport = transport

    def __repr__(self) -> str:  # never show the secret
        return f"<RazorpayGateway key_id={self.key_id}>"

    # --- orders -----------------------------------------------------------

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, notes: Mapping[str, str]
    ) -> GatewayOrder:
        if len(receipt) > MAX_RECEIPT_LENGTH:
            raise ValueError("receipt is longer than Razorpay allows")
        body = {"amount": amount_paise, "currency": currency, "receipt": receipt, "notes": dict(notes)}
        data = self._post("/orders", body)

        order_id = data.get("id")
        if not isinstance(order_id, str) or not order_id.startswith("order_") or len(order_id) > 255:
            self._reject("response had no valid order id")
        # bool is an int subclass; an amount of `true` must not pass as 1.
        if isinstance(data.get("amount"), bool) or data.get("amount") != amount_paise:
            self._reject("response amount does not match the amount we asked for")
        if data.get("currency") != currency:
            self._reject("response currency does not match the currency we asked for")
        if "status" in data and data["status"] != "created":
            self._reject("response order is not in the 'created' state")
        return GatewayOrder(id=order_id, amount_paise=amount_paise, currency=currency)

    # --- payments ---------------------------------------------------------

    def fetch_payment(self, payment_id: str) -> GatewayPayment:
        """Ask Razorpay what really happened to a payment. The id is checked
        against Razorpay's id format first, so it can never carry anything
        but letters and digits into the URL."""
        # fullmatch: "$" would also accept a trailing newline
        if not PAYMENT_ID_PATTERN.fullmatch(payment_id or ""):
            raise ValueError("not a Razorpay payment id")
        data = self._request("GET", f"/payments/{payment_id}")

        if data.get("id") != payment_id:
            self._reject("response is for a different payment")
        order_id = data.get("order_id")
        if not isinstance(order_id, str) or not order_id:
            self._reject("response payment has no order id")
        amount = data.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            self._reject("response payment has no valid amount")
        currency, status = data.get("currency"), data.get("status")
        if not isinstance(currency, str) or not isinstance(status, str):
            self._reject("response payment has no currency or status")
        return GatewayPayment(id=payment_id, order_id=order_id, amount_paise=amount, currency=currency, status=status)

    def verify_checkout_signature(self, razorpay_order_id: str, razorpay_payment_id: str, signature: str) -> bool:
        return is_valid_checkout_signature(self._secret, razorpay_order_id, razorpay_payment_id, signature)

    # --- plumbing ---------------------------------------------------------

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body)

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        try:
            with httpx.Client(
                base_url=self._base_url,
                auth=(self.key_id, self._secret),
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.request(method, path, json=body)
        except httpx.TimeoutException:
            logger.error("Razorpay request timed out: %s %s", method, path)
            raise PaymentGatewayError() from None
        except httpx.HTTPError as exc:
            # The exception TEXT can echo the URL; the class name is enough.
            logger.error("Razorpay request failed: %s %s (%s)", method, path, type(exc).__name__)
            raise PaymentGatewayError() from None

        if response.status_code >= 400:
            code = description = None
            try:
                error = response.json().get("error", {})
                code, description = error.get("code"), error.get("description")
            except (ValueError, AttributeError):
                pass
            logger.error(
                "Razorpay rejected %s %s: HTTP %s code=%s description=%s",
                method, path, response.status_code, _clip(code), _clip(description),
            )
            raise PaymentGatewayError()

        try:
            data = response.json()
        except ValueError:
            self._reject("response was not JSON")
        if not isinstance(data, dict):
            self._reject("response was not a JSON object")
        return data

    @staticmethod
    def _reject(reason: str):
        logger.error("Razorpay response rejected: %s", reason)
        raise PaymentGatewayError()


def _clip(value: object, limit: int = 200) -> str:
    return str(value)[:limit]
