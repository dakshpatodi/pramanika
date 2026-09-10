"""
Product endpoints - public, read-only browsing (listing, detail, related
products). No authentication required - customer product browsing
doesn't need a logged-in user; Phase 5's cart is where auth starts
mattering again for the shopping flow.
"""

from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.product import ProductDetail, ProductListResponse, ProductSort
from app.services.product_service import ProductService

router = APIRouter(prefix="/api/products", tags=["Products"])

MAX_PAGE_SIZE = 100


def get_validated_price_range(
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price (inclusive)"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price (inclusive)"),
) -> Tuple[Optional[float], Optional[float]]:
    """Cross-field validation (min <= max) doesn't fit into a single
    Query(...) constraint, since it depends on two parameters together -
    a small sub-dependency is the simplest way to validate this before
    it ever reaches the service/repository layer. FastAPI exposes this
    function's own parameters as query params of whichever endpoint
    depends on it - min_price/max_price show up on GET /api/products
    exactly as if declared directly there."""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_price cannot be greater than max_price.",
        )
    return min_price, max_price


@router.get(
    "",
    response_model=APIResponse[ProductListResponse],
    summary="List products with search, filtering, sorting, and pagination",
)
def list_products(
    page: int = Query(1, ge=1, description="Page number, starting at 1"),
    page_size: int = Query(12, ge=1, le=MAX_PAGE_SIZE, description=f"Items per page, max {MAX_PAGE_SIZE}"),
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    category: Optional[str] = Query(None, description="Category slug to filter by"),
    sort: ProductSort = Query(ProductSort.NEWEST),
    price_range: Tuple[Optional[float], Optional[float]] = Depends(get_validated_price_range),
    db: Session = Depends(get_db),
) -> APIResponse[ProductListResponse]:
    min_price, max_price = price_range
    service = ProductService(db)
    products, pagination = service.list_products(
        search=search,
        category_slug=category,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return APIResponse(
        success=True,
        message="Products retrieved successfully.",
        data=ProductListResponse(products=products, pagination=pagination),
    )


@router.get(
    "/{slug}",
    response_model=APIResponse[ProductDetail],
    summary="Get product detail by slug, including related products",
)
def get_product(slug: str, db: Session = Depends(get_db)) -> APIResponse[ProductDetail]:
    service = ProductService(db)
    product = service.get_product_detail(slug)
    return APIResponse(success=True, message="Product retrieved successfully.", data=product)