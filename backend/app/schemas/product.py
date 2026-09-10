"""
Product request/response schemas.
"""

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models import WeightUnit
from app.schemas.category import CategoryResponse


class ProductSort(str, enum.Enum):
    """Whitelisted sort options - used directly as a query parameter's
    type in api/products.py, so FastAPI/Pydantic reject anything else
    with a 422 automatically. No arbitrary order-by strings ever reach
    the database - this is the actual enforcement mechanism for
    "Do NOT allow arbitrary SQL/order-by strings from the user."
    """

    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"


class ProductListItem(BaseModel):
    """Lightweight shape for GET /api/products - deliberately excludes
    description/ingredients/nutritional_information (only needed once
    someone is actually looking at one product), per the "don't return
    unnecessary database fields" instruction.

    `in_stock`/`low_stock` are plain booleans, never the raw
    quantity/reserved_quantity numbers - exact stock counts are exactly
    the kind of internal detail a competitor could scrape and act on.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    sku: str
    price: float
    compare_at_price: Optional[float] = None
    image_url: Optional[str] = None
    category: CategoryResponse
    in_stock: bool
    low_stock: bool


class ProductDetail(BaseModel):
    """Full shape for GET /api/products/{slug}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    sku: str
    short_description: Optional[str] = None
    description: Optional[str] = None
    price: float
    compare_at_price: Optional[float] = None
    weight: Optional[float] = None
    weight_unit: Optional[WeightUnit] = None
    ingredients: Optional[str] = None
    nutritional_information: Optional[str] = None
    image_url: Optional[str] = None
    category: CategoryResponse
    in_stock: bool
    low_stock: bool
    created_at: datetime
    related_products: List[ProductListItem] = []


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ProductListResponse(BaseModel):
    products: List[ProductListItem]
    pagination: PaginationMeta