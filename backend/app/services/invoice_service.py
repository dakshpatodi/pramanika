"""
Invoice business logic (Phase 8): who may have an invoice, and for what.

Only a PAID order has one. The invoice is drawn from the order's stored
snapshots (see invoice_data.py), so asking again later gives the same
document. Read-only: nothing here writes, so there is no transaction to manage.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, settings as default_settings
from app.core.exceptions import InvoiceNotAvailableError, OrderNotFoundError
from app.core.money import money_to_float
from app.models import OrderPaymentStatus, User
from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.invoice import InvoiceListResponse, InvoiceSummary
from app.schemas.product import PaginationMeta
from app.services.invoice_data import build_invoice_data, invoice_filename, seller_from_settings
from app.services.invoice_pdf import render_invoice_pdf


@dataclass
class InvoiceFile:
    filename: str
    content: bytes


class InvoiceService:
    def __init__(self, db: Session, config: Settings = default_settings, *, compress: bool = True):
        self.invoices = InvoiceRepository(db)
        self.config = config
        self.compress = compress

    def list_invoices(self, user_id: uuid.UUID, *, page: int, page_size: int) -> InvoiceListResponse:
        orders, total = self.invoices.list_paid_for_user(user_id, page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return InvoiceListResponse(
            invoices=[
                InvoiceSummary(
                    order_id=o.id,
                    order_number=o.order_number,
                    order_date=o.created_at,
                    total=money_to_float(o.total_amount),
                    item_count=sum(i.quantity for i in o.items),
                    line_count=len(o.items),
                )
                for o in orders
            ],
            pagination=PaginationMeta(
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    def get_invoice_pdf(self, user: User, order_id: uuid.UUID) -> InvoiceFile:
        """404 for an unknown id or someone else's order; 409 until it is paid."""
        order = self.invoices.get_order_for_user(order_id, user.id)
        if order is None:
            raise OrderNotFoundError()
        if order.payment_status != OrderPaymentStatus.PAID:
            raise InvoiceNotAvailableError()
        paid_at = self.invoices.paid_at(order.id) or order.created_at
        data = build_invoice_data(order, user, paid_at=paid_at, seller=seller_from_settings(self.config))
        return InvoiceFile(filename=invoice_filename(order), content=render_invoice_pdf(data, compress=self.compress))
