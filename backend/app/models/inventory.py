"""
Inventory ORM model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Inventory(Base):
    """Stock levels for a single product - one row per product (see the
    unique constraint on `product_id`)."""

    __tablename__ = "inventory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    """Unique = exactly one inventory record per product, per the brief.
    CASCADE: an inventory row has no meaning once its product is gone."""

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    """Reserved but not yet fulfilled - e.g. sitting in someone's cart
    during checkout. Column exists now so `available = quantity -
    reserved_quantity` is a well-defined concept the moment checkout
    stock reservation is actually built; that logic itself is out of
    scope for Phase 3."""

    low_stock_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=10, server_default="10")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    product: Mapped["Product"] = relationship("Product", back_populates="inventory")

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved_quantity_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Inventory product_id={self.product_id} quantity={self.quantity}>"