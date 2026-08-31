"""
Review ORM model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class Review(Base):
    """A user's rating/review of a product.

    One review per user per product (see the unique constraint below) -
    this was flagged as a design decision before building: it's the
    standard e-commerce default (prevents one account from posting
    unlimited reviews for the same product) and matches "editing" being
    an UPDATE to the existing row rather than a new one.
    """

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    """Moderation queue - defaults to unapproved/hidden until a future
    admin moderation flow reviews it. Same "reserved for a flow that
    doesn't exist yet" pattern as User.is_verified in Phase 2."""

    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    """Reserved per the brief's explicit ask ("prepare for future
    verified-purchase logic") - unused until a later phase can actually
    check the reviewer's order history for this product before setting it."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="reviews")
    product: Mapped["Product"] = relationship("Product", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_reviews_user_id_product_id"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Review user_id={self.user_id} product_id={self.product_id} rating={self.rating}>"