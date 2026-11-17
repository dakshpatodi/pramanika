"""
Admin category and product schemas (Phase 9 M3).

Every write body forbids unknown keys (`extra="forbid"`), so nothing can be
smuggled into a model: there is no way to send an id, timestamp, stock count
(outside product creation) or `is_active` through an edit body. Activation has
its own endpoints; stock is changed only through the inventory endpoints.
Text is stripped, blank optional text becomes null, money must have at most 2
decimals (never silently rounded), weight at most 3.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import WeightUnit
from app.schemas.product import PaginationMeta
from app.services.catalog_rules import (
    clean_text,
    normalise_sku,
    normalise_slug,
    validate_image_url,
)

MAX_STOCK_FIELD = 1_000_000


def _strip_str(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------- categories


class _CategoryFields(_Body):
    @field_validator("name", "slug", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, value):
        return _strip_str(value)

    @field_validator("slug", check_fields=False)
    @classmethod
    def _slug(cls, value):
        return None if value is None else normalise_slug(value)

    @field_validator("description", check_fields=False)
    @classmethod
    def _description(cls, value):
        return clean_text(value)

    @field_validator("image_url", check_fields=False)
    @classmethod
    def _image(cls, value):
        value = clean_text(value)
        return None if value is None else validate_image_url(value)


class CategoryCreate(_CategoryFields):
    name: str = Field(min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=120, description="Defaults to a slug made from the name")
    description: Optional[str] = Field(None, max_length=2000)
    image_url: Optional[str] = Field(None, max_length=500)
    is_active: bool = True


class CategoryUpdate(_CategoryFields):
    """Only the fields sent are changed. `name` and `slug` cannot be cleared."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    image_url: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        for required in ("name", "slug"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be cleared.")
        return self


class AdminCategorySort(str, enum.Enum):
    NAME = "name"
    CREATED_AT = "created_at"
    PRODUCT_COUNT = "product_count"


class SortOrder(str, enum.Enum):
    ASC = "asc"
    DESC = "desc"


class AdminCategoryItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    image_url: Optional[str]
    is_active: bool
    product_count: int
    active_product_count: int
    created_at: datetime
    updated_at: datetime


class AdminCategoryListResponse(BaseModel):
    categories: List[AdminCategoryItem]
    pagination: PaginationMeta


# ----------------------------------------------------------------- products


class _ProductFields(_Body):
    @field_validator("name", "slug", "sku", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, value):
        return _strip_str(value)

    @field_validator("slug", check_fields=False)
    @classmethod
    def _slug(cls, value):
        return None if value is None else normalise_slug(value)

    @field_validator("sku", check_fields=False)
    @classmethod
    def _sku(cls, value):
        return None if value is None else normalise_sku(value)

    @field_validator("short_description", "description", "ingredients", "nutritional_information", check_fields=False)
    @classmethod
    def _text(cls, value):
        return clean_text(value)

    @field_validator("image_url", check_fields=False)
    @classmethod
    def _image(cls, value):
        value = clean_text(value)
        return None if value is None else validate_image_url(value)

    @field_validator("price", "compare_at_price", "weight", mode="before", check_fields=False)
    @classmethod
    def _no_bools(cls, value):
        if isinstance(value, bool):
            raise ValueError("Must be a number.")
        return value

    def _check_pairs(self, price, compare_at_price, weight, weight_unit):
        if compare_at_price is not None and price is not None and compare_at_price <= price:
            raise ValueError("compare_at_price must be greater than price.")
        if (weight is None) != (weight_unit is None):
            raise ValueError("weight and weight_unit must be given together.")


_MONEY = dict(gt=0, max_digits=10, decimal_places=2)
_WEIGHT = dict(gt=0, max_digits=10, decimal_places=3)


class ProductCreate(_ProductFields):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=220, description="Defaults to a slug made from the name")
    sku: str = Field(min_length=1, max_length=50)
    price: Decimal = Field(**_MONEY)
    compare_at_price: Optional[Decimal] = Field(None, **_MONEY)
    short_description: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=10000)
    weight: Optional[Decimal] = Field(None, **_WEIGHT)
    weight_unit: Optional[WeightUnit] = None
    ingredients: Optional[str] = Field(None, max_length=5000)
    nutritional_information: Optional[str] = Field(None, max_length=5000)
    image_url: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    initial_quantity: int = Field(0, ge=0, le=MAX_STOCK_FIELD)
    low_stock_threshold: int = Field(10, ge=0, le=MAX_STOCK_FIELD)

    @model_validator(mode="after")
    def _pairs(self):
        self._check_pairs(self.price, self.compare_at_price, self.weight, self.weight_unit)
        return self


class ProductUpdate(_ProductFields):
    """Only the fields sent are changed. Required fields cannot be cleared;
    optional ones can be set to null. No stock and no `is_active` here."""

    category_id: Optional[uuid.UUID] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=220)
    sku: Optional[str] = Field(None, min_length=1, max_length=50)
    price: Optional[Decimal] = Field(None, **_MONEY)
    compare_at_price: Optional[Decimal] = Field(None, **_MONEY)
    short_description: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=10000)
    weight: Optional[Decimal] = Field(None, **_WEIGHT)
    weight_unit: Optional[WeightUnit] = None
    ingredients: Optional[str] = Field(None, max_length=5000)
    nutritional_information: Optional[str] = Field(None, max_length=5000)
    image_url: Optional[str] = Field(None, max_length=500)

    REQUIRED: ClassVar[Tuple[str, ...]] = ("category_id", "name", "slug", "sku", "price")

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        for required in self.REQUIRED:
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be cleared.")
        return self


class AdminProductSort(str, enum.Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    NAME = "name"
    SKU = "sku"
    PRICE = "price"
    AVAILABLE = "available"


class StockFilter(str, enum.Enum):
    OK = "ok"
    LOW = "low"
    OUT = "out"


class AdminCategoryRef(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool


class AdminProductItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    sku: str
    price: float
    compare_at_price: Optional[float]
    image_url: Optional[str]
    is_active: bool
    category: AdminCategoryRef
    quantity: int
    reserved_quantity: int
    available_quantity: int
    low_stock_threshold: Optional[int]
    stock_status: str
    created_at: datetime
    updated_at: datetime


class AdminProductDetail(AdminProductItem):
    short_description: Optional[str]
    description: Optional[str]
    weight: Optional[float]
    weight_unit: Optional[str]
    ingredients: Optional[str]
    nutritional_information: Optional[str]


class AdminProductListResponse(BaseModel):
    products: List[AdminProductItem]
    pagination: PaginationMeta
