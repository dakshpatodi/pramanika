"""
Reading a Razorpay webhook body (pure - no database, no network, no secrets).

Only called AFTER the signature has been verified, so the content comes from
Razorpay. It is still read defensively: every id and amount is checked for
shape, and anything unexpected becomes `None` ("not something we can act on")
rather than an exception, so one odd event can never make Razorpay retry for a
day.

Events this application acts on:

    payment.authorized   the bank approved the payment (not captured yet)
    payment.captured     the money is ours
    payment.failed       that attempt failed
    order.paid           Razorpay's own summary that the order is fully paid
                         (treated exactly like payment.captured, using the
                         payment inside it)

Everything else (refunds, disputes, settlements...) is acknowledged and
ignored. The payload is NEVER stored or logged: it carries the customer's
e-mail and phone number.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

ORDER_ID_PATTERN = re.compile(r"^order_[A-Za-z0-9]{1,100}$")
PAYMENT_ID_PATTERN = re.compile(r"^pay_[A-Za-z0-9]{1,100}$")

EVENT_AUTHORIZED = "payment.authorized"
EVENT_CAPTURED = "payment.captured"
EVENT_FAILED = "payment.failed"
EVENT_ORDER_PAID = "order.paid"

HANDLED_EVENTS = frozenset({EVENT_AUTHORIZED, EVENT_CAPTURED, EVENT_FAILED, EVENT_ORDER_PAID})
CAPTURE_EVENTS = frozenset({EVENT_CAPTURED, EVENT_ORDER_PAID})

MAX_EVENT_TYPE = 100
MAX_REASON = 500


class MalformedWebhookError(ValueError):
    """The body is not a JSON object with an `event` string."""


@dataclass(frozen=True)
class WebhookEvent:
    type: str
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    amount_paise: Optional[int] = None
    currency: Optional[str] = None
    failure_reason: Optional[str] = None


def _dig(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _matching(value: Any, pattern: "re.Pattern[str]") -> Optional[str]:
    # fullmatch, not match: "$" would also accept a trailing newline
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _clean_reason(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = "".join(ch for ch in value if ch.isprintable()).strip()
    return text[:MAX_REASON] or None


def parse_webhook(raw_body: bytes) -> WebhookEvent:
    try:
        document = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise MalformedWebhookError("body is not JSON") from None
    event_type = document.get("event") if isinstance(document, dict) else None
    if not isinstance(event_type, str) or not event_type.strip():
        raise MalformedWebhookError("body has no event type")
    event_type = event_type.strip()[:MAX_EVENT_TYPE]

    if event_type not in HANDLED_EVENTS:
        return WebhookEvent(type=event_type)

    payment = _dig(document, "payload", "payment", "entity")
    amount = _dig(payment, "amount")
    return WebhookEvent(
        type=event_type,
        gateway_order_id=_matching(_dig(payment, "order_id"), ORDER_ID_PATTERN),
        gateway_payment_id=_matching(_dig(payment, "id"), PAYMENT_ID_PATTERN),
        amount_paise=amount if isinstance(amount, int) and not isinstance(amount, bool) else None,
        currency=_dig(payment, "currency") if isinstance(_dig(payment, "currency"), str) else None,
        failure_reason=_clean_reason(_dig(payment, "error_description")),
    )
