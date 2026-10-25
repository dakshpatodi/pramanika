"""
Invoice endpoints (Phase 8). Both depend on `get_current_active_user`; the
owner is always the user in the JWT.

    GET  /api/invoices              the user's paid orders (one invoice each), paginated
    GET  /api/invoices/{order_id}   the invoice as a PDF download
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.invoice import InvoiceListResponse
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])

MAX_PAGE_SIZE = 50


def get_invoice_service(db: Session = Depends(get_db)) -> InvoiceService:
    return InvoiceService(db)


@router.get(
    "",
    response_model=APIResponse[InvoiceListResponse],
    summary="List the current user's invoices (paid orders), newest first",
)
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(get_invoice_service),
):
    data = service.list_invoices(current_user.id, page=page, page_size=page_size)
    return APIResponse(success=True, message="Invoices retrieved.", data=data)


@router.get(
    "/{order_id}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Download the invoice for a paid order as a PDF",
)
def download_invoice(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(get_invoice_service),
):
    invoice = service.get_invoice_pdf(current_user, order_id)
    return Response(
        content=invoice.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
