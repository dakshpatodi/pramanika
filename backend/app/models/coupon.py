"""
Coupon ORM model.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.order import Order


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class Coupon(Base):
    """A discount code.

    Note: whether `discount_value` makes sense (e.g. a PERCENTAGE type
    capped at 100) is NOT enforced at the database level here - that
    would need a conditional CHECK constraint referencing `discount_type`,
    which is possible in Postgres but adds real complexity for a rule
    that's really about business logic, not data integrity. Left to the
    future coupon-calculation service to validate at creation time.
    """

    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="discount_type", native_enum=True, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    minimum_order_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    maximum_discount_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    """Caps a PERCENTAGE discount in absolute terms (e.g. "20% off, up to
    ₹200"). Meaningless for FIXED_AMOUNT coupons - left nullable rather
    than enforced, for the same reason noted in the class docstring."""

    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    """NULL = unlimited uses."""
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    orders: Mapped[List["Order"]] = relationship("Order", back_populates="coupon")

    __table_args__ = (
        CheckConstraint("discount_value > 0", name="ck_coupons_discount_value_positive"),
        CheckConstraint("used_count >= 0", name="ck_coupons_used_count_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Coupon code={self.code!r} type={self.discount_type.value}>"