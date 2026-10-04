"""
Cart endpoints.

Every route depends on `get_current_active_user`, so the cart always
belongs to the user in the JWT - no route accepts a user id, price, GST,
discount or delivery value from the client. Routes stay thin: they pass
the authenticated user's id to CartService and wrap its result in the
standard APIResponse envelope. Every mutation returns the full, freshly
priced cart so the frontend can just render what it gets back.

    GET    /api/cart                 current cart with totals
    POST   /api/cart/items           add a product (increments if already in cart)
    PATCH  /api/cart/items/{id}      set a line's quantity
    DELETE /api/cart/items/{id}      remove a line
    DELETE /api/cart                 clear the cart (and its coupon)
    POST   /api/cart/coupon          apply a coupon code
    DELETE /api/cart/coupon          remove the coupon
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartResponse,
    CouponApplyRequest,
)
from app.schemas.common import APIResponse
from app.services.cart_service import CartService

router = APIRouter(prefix="/api/cart", tags=["Cart"])


def get_cart_service(db: Session = Depends(get_db)) -> CartService:
    return CartService(db)


@router.get(
    "",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Get the current user's cart with server-calculated totals",
)
def get_cart(
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    return APIResponse(success=True, message="Cart retrieved.", data=service.get_cart(current_user.id))


@router.post(
    "/items",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Add a product to the cart (quantity is added to any existing line)",
)
def add_item(
    payload: CartItemAddRequest,
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    cart = service.add_item(current_user.id, payload.product_id, payload.quantity)
    return APIResponse(success=True, message="Item added to cart.", data=cart)


@router.patch(
    "/items/{item_id}",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Set the quantity of a cart line",
)
def update_item(
    item_id: uuid.UUID,
    payload: CartItemUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    cart = service.update_item(current_user.id, item_id, payload.quantity)
    return APIResponse(success=True, message="Cart item updated.", data=cart)


@router.delete(
    "/items/{item_id}",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove a line from the cart",
)
def remove_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    cart = service.remove_item(current_user.id, item_id)
    return APIResponse(success=True, message="Item removed from cart.", data=cart)


@router.delete(
    "",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove every item and any coupon from the cart",
)
def clear_cart(
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    return APIResponse(success=True, message="Cart cleared.", data=service.clear_cart(current_user.id))


@router.post(
    "/coupon",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Apply a coupon code to the cart",
)
def apply_coupon(
    payload: CouponApplyRequest,
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    cart = service.apply_coupon(current_user.id, payload.code)
    return APIResponse(success=True, message="Coupon applied.", data=cart)


@router.delete(
    "/coupon",
    response_model=APIResponse[CartResponse],
    status_code=status.HTTP_200_OK,
    summary="Remove the coupon from the cart",
)
def remove_coupon(
    current_user: User = Depends(get_current_active_user),
    service: CartService = Depends(get_cart_service),
) -> APIResponse[CartResponse]:
    return APIResponse(success=True, message="Coupon removed.", data=service.remove_coupon(current_user.id))