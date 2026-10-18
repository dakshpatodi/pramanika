"""
Access to the Razorpay credentials, with one rule: callers never read the
secrets straight off `settings`. They ask here, and get either usable
credentials or a `PaymentsNotConfiguredError` (HTTP 503, generic message).

Why a separate module: it is the single place that decides what may leave
the server. `public_key_id()` is the only credential-derived value that is
ever returned in an API response; the key secret and webhook secret are
reachable only through `get_razorpay_credentials()` /
`get_razorpay_webhook_secret()`, which are used by the gateway client and
the signature checks - never by a response schema.
"""

import logging
from dataclasses import dataclass, field

from app.core.config import Settings, settings as default_settings
from app.core.exceptions import PaymentsNotConfiguredError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RazorpayCredentials:
    key_id: str
    # repr=False: printing or logging this object never shows the secret.
    key_secret: str = field(repr=False)


def get_razorpay_credentials(config: Settings = default_settings) -> RazorpayCredentials:
    """Key id + key secret, or `PaymentsNotConfiguredError` if either is missing."""
    key_id = config.RAZORPAY_KEY_ID.strip()
    key_secret = config.RAZORPAY_KEY_SECRET.get_secret_value().strip()
    missing = [
        name
        for name, value in (("RAZORPAY_KEY_ID", key_id), ("RAZORPAY_KEY_SECRET", key_secret))
        if not value
    ]
    if missing:
        # Names only - never values.
        logger.error("Razorpay is not configured; missing: %s", ", ".join(missing))
        raise PaymentsNotConfiguredError()
    return RazorpayCredentials(key_id=key_id, key_secret=key_secret)


def get_razorpay_webhook_secret(config: Settings = default_settings) -> str:
    """The webhook signing secret, or `PaymentsNotConfiguredError` if unset."""
    secret = config.RAZORPAY_WEBHOOK_SECRET.get_secret_value().strip()
    if not secret:
        logger.error("Razorpay webhook is not configured; missing: RAZORPAY_WEBHOOK_SECRET")
        raise PaymentsNotConfiguredError()
    return secret


def public_key_id(config: Settings = default_settings) -> str:
    """The key id that is safe to send to the browser."""
    return get_razorpay_credentials(config).key_id
