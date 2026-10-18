"""
Payment ORM models.

`Payment` is one Razorpay order (one payment ATTEMPT SET) for a Pramanika
order; `PaymentWebhookEvent` remembers which Razorpay webhook deliveries
have been processed so a re-delivery is a no-op.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.order import Order


class PaymentTransactionStatus(str, enum.Enum):
    """Gateway-level transaction status - deliberately a SEPARATE, more
    granular enum from Order.payment_status (order.py). One order can
    have several Payment rows (a failed attempt, then a successful
    retry), so this describes one attempt, not the order's overall state.

    Phase 7 meaning of each value (the allowed moves between them live in
    `app/services/payment_rules.py`):

      INITIATED   Razorpay order created, customer has not paid yet (PENDING)
      AUTHORIZED  Razorpay authorised the payment, not captured yet
      CAPTURED    money taken - the only state that can mark an order paid (SUCCESS)
      FAILED      the attempt failed (the order may still be paid by a retry)
      EXPIRED     the Pramanika order expired before this was paid
      REFUNDED    a captured payment was refunded
    """

    INITIATED = "initiated"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class Payment(Base):
    """A single payment gateway transaction attempt against an order.

    `order_id` is intentionally NOT unique - Phase 7's Razorpay
    integration needs to record every attempt (a failed charge followed
    by a successful retry produces two rows here, not one row overwritten).
    What IS unique: each Razorpay order id, each Razorpay payment id, and
    - the database-level guarantee behind idempotent payment creation -
    at most ONE open (initiated/authorized) attempt per order.

    Security: only gateway-issued *references* are stored
    (gateway_order_id / gateway_payment_id / gateway_signature, all
    opaque strings Razorpay itself generates) - never card numbers, CVV,
    or any other raw payment credential. That data never touches this
    database in the Razorpay model (or any standard hosted gateway) -
    the gateway's own hosted checkout handles it directly.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    payment_gateway: Mapped[str] = mapped_column(String(50), nullable=False)
    """Plain string, not an enum - unlike internal status fields, this is
    an open-ended, extensible identifier ("razorpay" today, possibly
    others later) rather than a fixed internal vocabulary worth
    constraining at the DB level."""

    gateway_order_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gateway_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gateway_signature: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    """Used to verify a gateway webhook/callback is authentic (Razorpay's
    HMAC signature) - itself not sensitive the way a card number is, but
    still just an opaque reference string, never card data."""

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")

    status: Mapped[PaymentTransactionStatus] = mapped_column(
        Enum(
            PaymentTransactionStatus,
            name="payment_transaction_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=PaymentTransactionStatus.INITIATED,
        server_default=PaymentTransactionStatus.INITIATED.value,
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    """When the money was captured. Set exactly when status is CAPTURED or
    REFUNDED (enforced by a CHECK)."""

    refund_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    """True for a CAPTURED payment that does NOT pay a live order - the
    customer paid after their order was cancelled or expired, or paid a
    second time. The money is recorded, the order is NOT revived, and the
    shop refunds it manually (e.g. from the Razorpay dashboard)."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint("char_length(currency) = 3", name="ck_payments_currency_three_letters"),
        CheckConstraint(
            "payment_gateway <> 'razorpay' OR gateway_order_id IS NOT NULL",
            name="ck_payments_razorpay_has_gateway_order_id",
        ),
        CheckConstraint(
            "(status IN ('captured', 'refunded')) = (paid_at IS NOT NULL)",
            name="ck_payments_paid_at_matches_status",
        ),
        CheckConstraint(
            "status NOT IN ('captured', 'refunded') OR gateway_payment_id IS NOT NULL",
            name="ck_payments_paid_has_gateway_payment_id",
        ),
        CheckConstraint(
            "NOT refund_required OR status = 'captured'",
            name="ck_payments_refund_required_only_when_captured",
        ),
        Index(
            "uq_payments_gateway_order_id",
            "gateway_order_id",
            unique=True,
            postgresql_where=text("gateway_order_id IS NOT NULL"),
        ),
        Index(
            "uq_payments_gateway_payment_id",
            "gateway_payment_id",
            unique=True,
            postgresql_where=text("gateway_payment_id IS NOT NULL"),
        ),
        Index(
            "uq_payments_one_open_per_order",
            "order_id",
            unique=True,
            postgresql_where=text("status IN ('initiated', 'authorized')"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment id={self.id} order_id={self.order_id} status={self.status.value}>"


class PaymentWebhookEvent(Base):
    """One processed Razorpay webhook delivery.

    Razorpay sends a unique id with every delivery (the `X-Razorpay-Event-Id`
    header) and re-sends the SAME id when it retries. The unique constraint
    on `event_id` makes processing idempotent: the row is inserted in the
    same transaction as the state change, so either both happen or neither,
    and two simultaneous deliveries of one event cannot both get in.

    Only identifiers are stored - never the payload, which carries the
    customer's email and phone number.
    """

    __tablename__ = "payment_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    gateway_order_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gateway_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False, default="received", server_default="received")
    """What the handler did: applied, ignored, rejected, ... (free text key,
    kept as a string so adding an outcome never needs a migration)."""
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PaymentWebhookEvent event_id={self.event_id} type={self.event_type}>"
