"""
Wishlist endpoints (Phase 8). Every route depends on `get_current_active_user`;
the owner is always the user in the JWT - no route accepts a user id.

    GET     /api/wishlist                      the wishlist, newest first, paginated
    GET     /api/wishlist/product-ids          just the product ids (for heart buttons)
    POST    /api/wishlist/items                save a product; 201 new, 200 already saved
    DELETE  /api/wishlist/items/{product_id}   remove a product; 200 whether or not it was there
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.wishlist import (
    WishlistAddRequest,
    WishlistItemResponse,
    WishlistListResponse,
    WishlistProductIdsResponse,
)
from app.services.wishlist_service import WishlistService

router = APIRouter(prefix="/api/wishlist", tags=["Wishlist"])

MAX_PAGE_SIZE = 50


def get_wishlist_service(db: Session = Depends(get_db)) -> WishlistService:
    return WishlistService(db)


@router.get(
    "",
    response_model=APIResponse[WishlistListResponse],
    summary="List the current user's wishlist, most recently added first",
)
def list_wishlist(
    page: int = Query(1, ge=1, description="Page number, starting at 1"),
    page_size: int = Query(12, ge=1, le=MAX_PAGE_SIZE, description=f"Items per page, max {MAX_PAGE_SIZE}"),
    current_user: User = Depends(get_current_active_user),
    service: WishlistService = Depends(get_wishlist_service),
) -> APIResponse[WishlistListResponse]:
    return APIResponse(
        success=True,
        message="Wishlist retrieved.",
        data=service.list_items(current_user.id, page=page, page_size=page_size),
    )


@router.get(
    "/product-ids",
    response_model=APIResponse[WishlistProductIdsResponse],
    summary="The ids of every product on the current user's wishlist",
)
def wishlist_product_ids(
    current_user: User = Depends(get_current_active_user),
    service: WishlistService = Depends(get_wishlist_service),
) -> APIResponse[WishlistProductIdsResponse]:
    return APIResponse(success=True, message="Wishlist retrieved.", data=service.product_ids(current_user.id))


@router.post(
    "/items",
    response_model=APIResponse[WishlistItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Save a product to the wishlist (safe to repeat)",
)
def add_to_wishlist(
    payload: WishlistAddRequest,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    service: WishlistService = Depends(get_wishlist_service),
) -> APIResponse[WishlistItemResponse]:
    result = service.add(current_user.id, payload.product_id)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return APIResponse(
        success=True,
        message="Added to your wishlist." if result.created else "Already on your wishlist.",
        data=result.item,
    )


@router.delete(
    "/items/{product_id}",
    response_model=APIResponse[None],
    summary="Remove a product from the wishlist (safe to repeat)",
)
def remove_from_wishlist(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: WishlistService = Depends(get_wishlist_service),
) -> APIResponse[None]:
    removed = service.remove(current_user.id, product_id)
    return APIResponse(
        success=True,
        message="Removed from your wishlist." if removed else "It was not on your wishlist.",
    )
