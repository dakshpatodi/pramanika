"""
Admin inventory schemas (Phase 9 M4).

Stock is changed in exactly one of two ways, never both in one request:
  - SET   `quantity` + `expected_quantity` (what the admin saw). If stock moved
          in the meantime (a sale consumed units) the request is refused.
  - ADJUST `adjust_by` (+received / -written off). Applied atomically on the
          database's current value, so concurrent adjustments never get lost.
`reserved_quantity` is never accepted: reservations belong to checkout.
Numbers must be real integers (strings, floats and booleans are refused).
"""

import enum
import uuid
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.admin_catalog import AdminCategoryRef
from app.schemas.product import PaginationMeta

MAX_QUANTITY = 1_000_000

Quantity = Annotated[int, Field(strict=True, ge=0, le=MAX_QUANTITY)]
Delta = Annotated[int, Field(strict=True, ge=-MAX_QUANTITY, le=MAX_QUANTITY)]


class InventoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: Optional[Quantity] = None
    expected_quantity: Optional[Quantity] = None
    adjust_by: Optional[Delta] = None
    low_stock_threshold: Optional[Quantity] = None
    reason: Optional[str] = Field(None, max_length=200)

    @field_validator("reason", mode="before")
    @classmethod
    def _strip_reason(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _one_way_to_change_stock(self):
        sent = self.model_fields_set
        changes_stock = "quantity" in sent or "adjust_by" in sent
        if not (changes_stock or "low_stock_threshold" in sent):
            raise ValueError("Send quantity, adjust_by or low_stock_threshold.")
        for name in ("quantity", "adjust_by", "low_stock_threshold"):
            if name in sent and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        if "quantity" in sent and "adjust_by" in sent:
            raise ValueError("Send either quantity (set) or adjust_by (adjust), not both.")
        if "quantity" in sent and self.expected_quantity is None:
            raise ValueError("expected_quantity is required when setting quantity (the value you saw).")
        if "expected_quantity" in sent and "quantity" not in sent:
            raise ValueError("expected_quantity only goes with quantity.")
        if "adjust_by" in sent and self.adjust_by == 0:
            raise ValueError("adjust_by cannot be 0.")
        if self.reason is not None and not changes_stock:
            raise ValueError("reason only goes with a stock change.")
        return self


class InventorySortKey(str, enum.Enum):
    NAME = "name"
    SKU = "sku"
    AVAILABLE = "available"
    QUANTITY = "quantity"
    UPDATED_AT = "updated_at"


class AdminInventoryItem(BaseModel):
    product_id: uuid.UUID
    name: str
    sku: str
    is_active: bool
    category: AdminCategoryRef
    quantity: int
    reserved_quantity: int
    available_quantity: int
    low_stock_threshold: Optional[int]
    stock_status: str
    updated_at: datetime


class AdminInventoryDetail(AdminInventoryItem):
    """Adds what is holding the reservation: the open (unpaid, still reserved)
    orders. `open_order_units` should equal `reserved_quantity`; if it does not
    the books have drifted and `reservations_match` is false."""

    open_order_count: int
    open_order_units: int
    reservations_match: bool


class AdminInventoryListResponse(BaseModel):
    items: List[AdminInventoryItem]
    pagination: PaginationMeta
