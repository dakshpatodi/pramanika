"""Admin category endpoints (Phase 9 M3). There is deliberately no DELETE:
deactivate instead (refused while the category still has active products)."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database.session import get_db
from app.models import User
from app.schemas.admin_catalog import (
    AdminCategoryItem,
    AdminCategoryListResponse,
    AdminCategorySort,
    CategoryCreate,
    CategoryUpdate,
    SortOrder,
)
from app.schemas.common import APIResponse
from app.services.admin_category_service import AdminCategoryService

router = APIRouter(prefix="/categories", tags=["Admin - Categories"])
MAX_PAGE_SIZE = 100


def _service(db: Session = Depends(get_db)) -> AdminCategoryService:
    return AdminCategoryService(db)


@router.get("", response_model=APIResponse[AdminCategoryListResponse], summary="List categories (any state)")
def list_categories(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    search: Optional[str] = Query(None, min_length=1, max_length=100),
    is_active: Optional[bool] = Query(None),
    sort: AdminCategorySort = Query(AdminCategorySort.NAME),
    order: SortOrder = Query(SortOrder.ASC),
    service: AdminCategoryService = Depends(_service),
):
    data = service.list(search=search, is_active=is_active, sort=sort, order=order, page=page, page_size=page_size)
    return APIResponse(success=True, message="OK", data=data)


@router.get("/{category_id}", response_model=APIResponse[AdminCategoryItem], summary="One category")
def get_category(category_id: uuid.UUID, service: AdminCategoryService = Depends(_service)):
    return APIResponse(success=True, message="OK", data=service.get(category_id))


@router.post("", response_model=APIResponse[AdminCategoryItem], status_code=status.HTTP_201_CREATED, summary="Create a category")
def create_category(payload: CategoryCreate, admin: User = Depends(require_admin), service: AdminCategoryService = Depends(_service)):
    return APIResponse(success=True, message="Category created.", data=service.create(admin, payload))


@router.patch("/{category_id}", response_model=APIResponse[AdminCategoryItem], summary="Edit name, slug, description or image")
def update_category(category_id: uuid.UUID, payload: CategoryUpdate, admin: User = Depends(require_admin), service: AdminCategoryService = Depends(_service)):
    return APIResponse(success=True, message="Category updated.", data=service.update(admin, category_id, payload))


@router.post("/{category_id}/activate", response_model=APIResponse[AdminCategoryItem], summary="Show the category in the shop")
def activate_category(category_id: uuid.UUID, admin: User = Depends(require_admin), service: AdminCategoryService = Depends(_service)):
    return APIResponse(success=True, message="Category activated.", data=service.set_active(admin, category_id, True))


@router.post("/{category_id}/deactivate", response_model=APIResponse[AdminCategoryItem], summary="Hide the category (409 while it has active products)")
def deactivate_category(category_id: uuid.UUID, admin: User = Depends(require_admin), service: AdminCategoryService = Depends(_service)):
    return APIResponse(success=True, message="Category deactivated.", data=service.set_active(admin, category_id, False))
