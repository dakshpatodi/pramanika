"""
Payment response schemas.

What may leave the server for a payment is deliberately tiny. The browser
needs exactly these to open Razorpay Checkout; it never receives the key
secret, the webhook secret, a signature, or anything about other attempts.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class PaymentIntentResponse(BaseModel):
    order_id: uuid.UUID
    order_number: Optional[str] = None
    razorpay_order_id: str
    razorpay_key_id: str = Field(description="The PUBLIC Razorpay key id. Never the secret.")
    amount_paise: int = Field(description="Amount in paise (Rs 406.21 -> 40621), as Razorpay Checkout expects.")
    currency: str


class PaymentVerifyRequest(BaseModel):
    """What Razorpay Checkout returned to the browser. The patterns only
    keep junk out early (and any path-like text away from the Razorpay URL);
    whether the signature is genuine is decided by the HMAC check, never by
    these."""

    razorpay_order_id: str = Field(pattern=r"^order_[A-Za-z0-9]{1,100}$")
    razorpay_payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]{1,100}$")
    razorpay_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
