"""
Product ORM model.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.inventory import Inventory
    from app.models.cart import CartItem
    from app.models.order import OrderItem
    from app.models.review import Review
    from app.models.wishlist import WishlistItem


class WeightUnit(str, enum.Enum):
    """Small, controlled vocabulary - a native enum here catches typos
    ("Kg" vs "kg" vs "kilo") that a free-text column would silently allow,
    the same reasoning as UserRole in Phase 2."""

    GRAM = "g"
    KILOGRAM = "kg"
    MILLILITRE = "ml"
    LITRE = "l"


class Product(Base):
    """A sellable item (cereal, ready mix, etc.).

    Multiple product images: NOT modeled as a separate `ProductImage`
    table in Phase 3. A photo gallery is a real, self-contained feature
    that belongs with whichever phase actually builds product-detail
    pages - adding the table now, with no UI or upload flow to populate
    it, would be schema for a feature that doesn't exist yet. A single
    `image_url` (matching the brief's field list, and consistent with
    Category's single `image_url`) is enough for a catalogue listing.
    Revisit this the moment a real gallery requirement shows up.
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    """RESTRICT rather than CASCADE: deleting a category that still has
    products should fail loudly, not silently vaporize a chunk of the
    catalogue. A future admin flow can require re-assigning products
    before a category can be removed."""

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    short_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    """The "was" price shown struck through next to a discounted `price` -
    named to match the frontend's existing `compareAtPrice` field
    (see frontend/src/types/index.ts from Phase 1) rather than the
    brief's alternate suggestion `original_price`, so the two layers
    share one vocabulary for the same concept."""

    weight: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    weight_unit: Mapped[Optional[WeightUnit]] = mapped_column(
        Enum(WeightUnit, name="weight_unit", native_enum=True, values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )

    ingredients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nutritional_information: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    """Free-text for Phase 3. If a later phase needs to query/filter on
    specific nutrients (e.g. "show me products under 5g sugar"), this
    should become JSONB with a defined shape at that point - not before
    there's a real query to support."""

    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    category: Mapped["Category"] = relationship("Category", back_populates="products")
    inventory: Mapped[Optional["Inventory"]] = relationship(
        "Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="product")
    cart_items: Mapped[List["CartItem"]] = relationship("CartItem", back_populates="product")
    order_items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="product")
    wishlist_items: Mapped[List["WishlistItem"]] = relationship("WishlistItem", back_populates="product")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product id={self.id} sku={self.sku!r} name={self.name!r}>"