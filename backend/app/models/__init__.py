"""
ORM models package.

Every model module is imported here so that:
1. `Base.metadata` is fully populated the moment `app.models` is imported
   anywhere (Alembic's env.py relies on this for autogenerate).
2. Other layers can do `from app.models import Product` instead of
   reaching into `app.models.product` directly.

Import order matters only in the sense that every module uses TYPE_CHECKING
guards + string-based relationship() targets (e.g. relationship("Product")),
so there is no circular-import constraint here - Python can import these
in any order and SQLAlchemy resolves the string references once every
class has been registered.
"""

from app.models.address import Address
from app.models.cart import Cart, CartItem
from app.models.category import Category
from app.models.coupon import Coupon, DiscountType
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderPaymentStatus, OrderStatus
from app.models.payment import Payment, PaymentTransactionStatus
from app.models.product import Product, WeightUnit
from app.models.review import Review
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.models.wishlist import Wishlist, WishlistItem

__all__ = [
    "User",
    "UserRole",
    "RevokedToken",
    "Category",
    "Product",
    "WeightUnit",
    "Inventory",
    "Address",
    "Cart",
    "CartItem",
    "Wishlist",
    "WishlistItem",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderPaymentStatus",
    "Coupon",
    "DiscountType",
    "Payment",
    "PaymentTransactionStatus",
    "Review",
]