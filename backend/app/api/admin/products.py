"""Admin product endpoints (Phase 9 M3). No DELETE (orders keep snapshots, but
carts, wishlists and history point at products): deactivate instead. Stock is
not editable here - see the inventory endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database.session import get_db
from app.models import User
from app.schemas.admin_catalog import (
    AdminProductDetail,
    AdminProductListResponse,
    AdminProductSort,
    ProductCreate,
    ProductUpdate,
    SortOrder,
    StockFilter,
)
from app.schemas.common import APIResponse
from app.services.admin_product_service import AdminProductService

router = APIRouter(prefix="/products", tags=["Admin - Products"])
MAX_PAGE_SIZE = 100


def _service(db: Session = Depends(get_db)) -> AdminProductService:
    return AdminProductService(db)


@router.get("", response_model=APIResponse[AdminProductListResponse], summary="List products (any state) with search, filters, sorting, paging")
def list_products(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Name, SKU or slug"),
    category_id: Optional[uuid.UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    stock: Optional[StockFilter] = Query(None, description="ok = above the low-stock threshold, low, out"),
    sort: AdminProductSort = Query(AdminProductSort.CREATED_AT),
    order: SortOrder = Query(SortOrder.DESC),
    service: AdminProductService = Depends(_service),
):
    data = service.list(
        search=search, category_id=category_id, is_active=is_active, stock=stock,
        sort=sort, order=order, page=page, page_size=page_size,
    )
    return APIResponse(success=True, message="OK", data=data)


@router.get("/{product_id}", response_model=APIResponse[AdminProductDetail], summary="One product with its stock")
def get_product(product_id: uuid.UUID, service: AdminProductService = Depends(_service)):
    return APIResponse(success=True, message="OK", data=service.get(product_id))


@router.post("", response_model=APIResponse[AdminProductDetail], status_code=status.HTTP_201_CREATED, summary="Create a product (and its inventory row)")
def create_product(payload: ProductCreate, admin: User = Depends(require_admin), service: AdminProductService = Depends(_service)):
    return APIResponse(success=True, message="Product created.", data=service.create(admin, payload))


@router.patch("/{product_id}", response_model=APIResponse[AdminProductDetail], summary="Edit product details (never stock, never active state)")
def update_product(product_id: uuid.UUID, payload: ProductUpdate, admin: User = Depends(require_admin), service: AdminProductService = Depends(_service)):
    return APIResponse(success=True, message="Product updated.", data=service.update(admin, product_id, payload))


@router.post("/{product_id}/activate", response_model=APIResponse[AdminProductDetail], summary="Show the product in the shop")
def activate_product(product_id: uuid.UUID, admin: User = Depends(require_admin), service: AdminProductService = Depends(_service)):
    return APIResponse(success=True, message="Product activated.", data=service.set_active(admin, product_id, True))


@router.post("/{product_id}/deactivate", response_model=APIResponse[AdminProductDetail], summary="Hide the product from the shop")
def deactivate_product(product_id: uuid.UUID, admin: User = Depends(require_admin), service: AdminProductService = Depends(_service)):
    return APIResponse(success=True, message="Product deactivated.", data=service.set_active(admin, product_id, False))
