"""
User ORM model.

This is the first real table in the schema. Phase 1 shipped `models/`
empty on purpose (see models/__init__.py) - this migration is the first
one ever applied to the database.

Only authentication-relevant fields live here. Addresses, order history,
wishlists, etc. belong to later phases and will reference `User.id` as a
foreign key rather than being added as columns on this table.
"""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional


from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.cart import Cart
    from app.models.order import Order
    from app.models.review import Review
    from app.models.wishlist import Wishlist

class UserRole(str, enum.Enum):
    """Authorization roles.

    Only two roles exist in Phase 2. Inheriting from `str` means the enum
    serializes cleanly to JSON (`UserRole.CUSTOMER == "customer"`) without
    a custom Pydantic encoder. Adding a role later (e.g. `STAFF`) is a
    non-breaking, additive migration - existing rows are unaffected.
    """

    CUSTOMER = "customer"
    ADMIN = "admin"


class User(Base):
    """A registered account (customer or admin)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    """UUID rather than an auto-increment integer: this id ends up inside
    JWTs and, later, in URLs (e.g. order lookups) - a UUID doesn't leak
    "how many users have signed up" the way a sequential id would."""

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    """Bcrypt hash only - the plaintext password is never persisted or logged."""

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.CUSTOMER,
        server_default=UserRole.CUSTOMER.value,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    """Soft "disable this account" flag - distinct from deletion. Login is
    refused when False, even with a correct password (see auth dependency
    in Milestone 5)."""

    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    """Reserved for email/phone verification. Phase 2 does not implement a
    verification flow yet, but the column exists now so it doesn't require
    a second migration later; it defaults to False and is simply unused
    until that flow is built."""

    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

        # --- Phase 3 additions: relationships only, no new columns on `users`. ---
    addresses: Mapped[List["Address"]] = relationship(
        "Address", back_populates="user", cascade="all, delete-orphan"
    )
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user")
    cart: Mapped[Optional["Cart"]] = relationship(
        "Cart", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    wishlist: Mapped[Optional["Wishlist"]] = relationship(
        "Wishlist", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"