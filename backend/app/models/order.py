"""
Order and OrderItem ORM models.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.coupon import Coupon
    from app.models.payment import Payment
    from app.models.product import Product
    from app.models.user import User


class OrderStatus(str, enum.Enum):
    """Fulfillment lifecycle - independent of payment status (see
    OrderPaymentStatus below): an order can be CONFIRMED with payment
    still PENDING (e.g. cash on delivery), so these are deliberately two
    separate enums rather than one combined status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderPaymentStatus(str, enum.Enum):
    """A denormalized SUMMARY of this order's payment state - the source
    of truth for the full history of gateway attempts is the `Payment`
    table (payment.py), which can hold multiple rows per order (retries).
    This column exists so "is this order paid?" doesn't require joining
    and reducing over Payment rows on every read."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class Order(Base):
    """A placed order.

    Shipping address: extends the brief's own OrderItem philosophy
    ("preserve information at the time of purchase, don't rely on data
    that can change later") to the address too. `shipping_address_id` is
    a nullable FK for traceability back to the saved Address row, but the
    actual source of truth for fulfillment is the snapshot columns below -
    if the user edits or deletes that saved address afterward, this
    order's shipping details must not change.
    """

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    order_number: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    """Human-facing reference (e.g. "ORD-2026-000123") for support/tracking
    - not in the brief's field list, but a raw UUID is a poor thing to
    read over the phone to a customer-support agent. Nullable + generated
    at order-creation time by the future checkout service (out of scope
    for Phase 3, which only builds the schema); NULL for now on any row
    that predates that logic. Unique constraint still holds - Postgres
    treats multiple NULLs as distinct, so this doesn't block having many
    NULL rows before generation logic exists."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    """RESTRICT, not CASCADE: a user account being removed should never
    silently delete their order history - that's financial/legal record,
    not disposable user data."""

    shipping_address_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True
    )
    shipping_full_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    shipping_phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    shipping_address_line_1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipping_address_line_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    shipping_state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    shipping_postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    shipping_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    delivery_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    coupon_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", native_enum=True, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    payment_status: Mapped[OrderPaymentStatus] = mapped_column(
        Enum(
            OrderPaymentStatus,
            name="order_payment_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=OrderPaymentStatus.PENDING,
        server_default=OrderPaymentStatus.PENDING.value,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="orders")
    shipping_address: Mapped[Optional["Address"]] = relationship("Address", back_populates="orders")
    coupon: Mapped[Optional["Coupon"]] = relationship("Coupon", back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="order")

    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order id={self.id} status={self.status.value} total={self.total_amount}>"


class OrderItem(Base):
    """One product line within an order, with product details SNAPSHOTTED
    at purchase time.

    `product_id` is nullable with ON DELETE SET NULL (not CASCADE) - if
    the underlying Product row is ever hard-deleted, this line item must
    survive, since `product_name_snapshot`/`sku_snapshot`/`unit_price`
    already capture everything needed to know what was actually bought,
    independent of whether the live Product row still exists or has
    since changed its name/price.
    """

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)

    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    """Stored explicitly (unit_price * quantity) rather than computed on
    read - same "capture the truth at the time" philosophy as the rest of
    this table. Avoids any drift if the computation logic ever changes."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    """No `updated_at` - an order line item is written once at checkout
    and never edited afterward (a correction would be a refund/new order,
    not a mutation of history)."""

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="order_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OrderItem order_id={self.order_id} sku={self.sku_snapshot!r} qty={self.quantity}>"