"""
Administrator API (Phase 9), mounted at /api/admin.

THE GUARD LIVES HERE. The parent router carries `Depends(require_admin)`, and
FastAPI applies a router's dependencies to every route included in it. So a
new admin route cannot be left unprotected by forgetting a decorator argument:
401 without a valid login, 403 for a customer or a deactivated account, decided
on the server from the database role on every request.

Add each new admin module with `router.include_router(...)` below and nothing
else; tests/test_p9_admin_auth.py walks every /api/admin route and fails if
one is not behind the guard.
"""

from fastapi import APIRouter, Depends

from app.api.admin import account, audit, categories, dashboard, inventory, orders, products
from app.api.deps import require_admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

router.include_router(account.router)
router.include_router(audit.router)
router.include_router(dashboard.router)
router.include_router(categories.router)
router.include_router(products.router)
router.include_router(inventory.router)
router.include_router(orders.router)
