"""
Category request/response schemas.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CategoryResponse(BaseModel):
    """Public-facing category representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str] = None
    image_url: Optional[str] = None


class CategoryListItem(CategoryResponse):
    """Adds a product count, used only by the listing endpoint.

    Built manually from a (Category, count) query tuple in the service
    layer - it can't be produced via CategoryResponse.model_validate()
    directly, since `product_count` isn't a real attribute on the
    Category ORM model, just a query-time aggregate.
    """

    product_count: int