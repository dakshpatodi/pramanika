"""Invoice list shapes (Phase 8). The invoice itself is a PDF, not JSON."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.product import PaginationMeta


class InvoiceSummary(BaseModel):
    order_id: uuid.UUID
    order_number: Optional[str] = None
    order_date: datetime
    total: float
    item_count: int
    """Total units across all lines."""
    line_count: int


class InvoiceListResponse(BaseModel):
    invoices: List[InvoiceSummary]
    pagination: PaginationMeta
