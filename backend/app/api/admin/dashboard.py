"""Admin overview metrics (Phase 9 M2). Read-only."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.admin_dashboard import DashboardResponse
from app.schemas.common import APIResponse
from app.services.admin_dashboard_service import AdminDashboardService

router = APIRouter(tags=["Admin"])


@router.get(
    "/dashboard",
    response_model=APIResponse[DashboardResponse],
    summary="Shop overview: orders, customers, products, revenue, recent orders",
)
def dashboard(db: Session = Depends(get_db)) -> APIResponse[DashboardResponse]:
    """Revenue counts only orders that are PAID and not cancelled/refunded
    (gross: includes GST and delivery). Low/out-of-stock count active products
    only, by the shop's own rule. Everything is aggregated in SQL."""
    return APIResponse(success=True, message="OK", data=AdminDashboardService(db).build())
