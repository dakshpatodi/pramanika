"""
Wishlist request / response schemas (Phase 8).

A wishlist row is shown with the product as it is NOW (name, price, stock) -
unlike an order it is not a record of something bought. A product that has
since been deactivated stays in the list, flagged `is_available = false`, so
the customer can see and remove it; the storefront no longer shows such a
product, so there is nothing to link to. Exact stock numbers never leave the
server (same rule as the catalogue): only `in_stock` / `low_stock`.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.product import PaginationMeta


class WishlistAddRequest(BaseModel):
    """The product to save. Nothing else is accepted: the owner is always the
    authenticated user."""

    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID


class WishlistItemResponse(BaseModel):
    product_id: uuid.UUID
    name: str
    slug: str
    price: float
    compare_at_price: Optional[float] = None
    image_url: Optional[str] = None
    is_available: bool
    """False once the product has been deactivated: it cannot be bought or
    opened in the shop any more, only removed from the wishlist."""
    in_stock: bool
    low_stock: bool
    added_at: datetime


class WishlistListResponse(BaseModel):
    items: List[WishlistItemResponse]
    pagination: PaginationMeta


class WishlistProductIdsResponse(BaseModel):
    """Every product id on the wishlist (at most MAX_WISHLIST_ITEMS), so a
    product page or card can draw its heart without one request per product."""

    product_ids: List[uuid.UUID]
