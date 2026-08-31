"""
Payment ORM model.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.order import Order


class PaymentTransactionStatus(str, enum.Enum):
    """Gateway-level transaction status - deliberately a SEPARATE, more
    granular enum from Order.payment_status (order.py). One order can
    have several Payment rows (a failed attempt, then a successful
    retry), so this describes one attempt, not the order's overall state."""

    INITIATED = "initiated"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(Base):
    """A single payment gateway transaction attempt against an order.

    `order_id` is intentionally NOT unique - Phase 7's Razorpay
    integration needs to record every attempt (a failed charge followed
    by a successful retry produces two rows here, not one row overwritten).

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

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment id={self.id} order_id={self.order_id} status={self.status.value}>"