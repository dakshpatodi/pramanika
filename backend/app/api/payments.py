"""
Payment endpoints.

    POST  /api/orders/{order_id}/payment          start (or resume) paying for an order
    POST  /api/orders/{order_id}/payment/verify   verify what Razorpay Checkout returned, and pay the order
    POST  /api/payments/webhook                   Razorpay tells the server about a payment (M7, no login: signed)

Returns what Razorpay Checkout needs and nothing more: the Pramanika order
id, the Razorpay order id, the PUBLIC key id, the amount in paise and the
currency. The amount is computed on the server from the stored order; the
request has no body, so there is nothing for a client to tamper with.

Safe to call repeatedly: while the order has an open payment the same
Razorpay order is returned (HTTP 200); the call that created it returns 201.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_active_user
from app.core.exceptions import WebhookTooLargeError
from app.core.payment_config import get_razorpay_credentials, get_razorpay_webhook_secret
from app.database.session import get_db
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.order import OrderResponse
from app.schemas.payment import PaymentIntentResponse, PaymentVerifyRequest
from app.services.payment_service import PaymentService, VerifyOutcome
from app.services.payment_webhook_service import MAX_BODY_BYTES, PaymentWebhookService, WebhookOutcome
from app.services.razorpay_gateway import PaymentGateway, RazorpayGateway

router = APIRouter(tags=["Payments"])


def get_payment_gateway() -> PaymentGateway:
    """The real Razorpay client, or 503 if the server has no credentials.
    Tests replace this dependency with a fake."""
    return RazorpayGateway(get_razorpay_credentials())


def get_payment_service(
    # Declared first on purpose: an anonymous caller gets 401 and learns
    # nothing about whether payments are configured (which would be 503).
    _user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> PaymentService:
    return PaymentService(db, gateway)


@router.post(
    "/api/orders/{order_id}/payment",
    response_model=APIResponse[PaymentIntentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create (or resume) the Razorpay order for one of your unpaid orders",
)
def create_payment(
    order_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    service: PaymentService = Depends(get_payment_service),
) -> APIResponse[PaymentIntentResponse]:
    result = service.create_razorpay_order(current_user.id, order_id)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    # The Razorpay order id belongs to this customer's checkout only.
    response.headers["Cache-Control"] = "no-store"
    return APIResponse(
        success=True,
        message="Payment started." if result.created else "Payment is ready to continue.",
        data=result.intent,
    )


_VERIFY_MESSAGES = {
    VerifyOutcome.PAID: "Payment confirmed.",
    VerifyOutcome.ALREADY_PAID: "This payment was already confirmed.",
    VerifyOutcome.PENDING_CAPTURE: "Your payment is being confirmed.",
}


@router.post(
    "/api/orders/{order_id}/payment/verify",
    response_model=APIResponse[OrderResponse],
    summary="Verify the payment Razorpay Checkout reported; the order is paid only if the server confirms it",
)
def verify_payment(
    order_id: uuid.UUID,
    payload: PaymentVerifyRequest,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    service: PaymentService = Depends(get_payment_service),
) -> APIResponse[OrderResponse]:
    """The reply is the order as it now stands. Look at `payment_status`:
    only "paid" means the money is confirmed. A 200 alone does not - an
    authorized-but-not-yet-captured payment answers 200 with the order still
    unpaid (repeat the call, or wait for Razorpay's webhook)."""
    result = service.verify_payment(
        current_user.id,
        order_id,
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
    )
    response.headers["Cache-Control"] = "no-store"
    return APIResponse(success=True, message=_VERIFY_MESSAGES[result.outcome], data=result.order)


# --- Razorpay webhook (M7) ----------------------------------------------------


def get_webhook_secret() -> str:
    """The webhook signing secret, or 503 if the server has none. Tests replace
    this dependency. The secret goes to the service only - never to a response."""
    return get_razorpay_webhook_secret()


async def _read_capped_body(request: Request) -> bytes:
    """The raw body, refused as soon as it is larger than MAX_BODY_BYTES.

    The declared Content-Length turns an honest oversized request away before a
    byte is read; the running count catches the rest (chunked uploads declare no
    length at all), so nothing larger than the cap is ever held in memory - and
    this happens before the signature check, which needs the whole body."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise WebhookTooLargeError()
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise WebhookTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/api/payments/webhook",
    response_model=APIResponse[None],
    summary="Razorpay webhook receiver (authenticated by signature, not by login)",
    include_in_schema=True,
)
async def razorpay_webhook(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    secret: str = Depends(get_webhook_secret),
) -> APIResponse[None]:
    """Razorpay calls this; browsers never do. The signature is computed over
    the exact raw bytes, so the body is read raw here and only parsed after the
    check. Every outcome that retrying cannot improve (including events we
    ignore) is a 2xx, so Razorpay stops retrying; failures that might clear up
    (database down, 503) are not, so it tries again."""
    raw_body = await _read_capped_body(request)
    service = PaymentWebhookService(db, secret)
    outcome = await run_in_threadpool(
        service.handle,
        raw_body,
        request.headers.get("X-Razorpay-Signature"),
        request.headers.get("X-Razorpay-Event-Id"),
    )
    response.headers["Cache-Control"] = "no-store"
    message = "Event already processed." if outcome is WebhookOutcome.DUPLICATE else "Event received."
    return APIResponse(success=True, message=message)
