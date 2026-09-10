"""
Category endpoints - public, read-only browsing. No authentication
required, matching the existing project decision that customer browsing
doesn't need a logged-in user.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.category import CategoryListItem, CategoryResponse
from app.schemas.common import APIResponse
from app.services.category_service import CategoryService

router = APIRouter(prefix="/api/categories", tags=["Categories"])


@router.get(
    "",
    response_model=APIResponse[List[CategoryListItem]],
    summary="List active categories with product counts",
)
def list_categories(db: Session = Depends(get_db)) -> APIResponse[List[CategoryListItem]]:
    service = CategoryService(db)
    categories = service.list_categories()
    return APIResponse(success=True, message="Categories retrieved successfully.", data=categories)


@router.get(
    "/{slug}",
    response_model=APIResponse[CategoryResponse],
    summary="Get a single category by slug",
)
def get_category(slug: str, db: Session = Depends(get_db)) -> APIResponse[CategoryResponse]:
    service = CategoryService(db)
    category = service.get_category(slug)
    return APIResponse(success=True, message="Category retrieved successfully.", data=category)