"""
User profile endpoints.

    GET    /api/users/me     the authenticated user's own profile      (Phase 2)
    PATCH  /api/users/me     change first name, last name or phone     (Phase 8)

Everything these need (the current user, already loaded and confirmed active)
comes from `get_current_active_user`; no route accepts a user id, so a
customer can only ever read or change themselves.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.user import UserResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["Users"])


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Get the authenticated user's own profile",
)
def get_me(current_user: User = Depends(get_current_active_user)) -> APIResponse[UserResponse]:
    return APIResponse(
        success=True,
        message="User profile retrieved successfully.",
        data=UserResponse.model_validate(current_user),
    )


@router.patch(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Update the authenticated user's own profile (first name, last name, phone number)",
)
def update_me(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(get_user_service),
) -> APIResponse[UserResponse]:
    user = service.update_profile(current_user, payload)
    return APIResponse(
        success=True,
        message="Profile updated.",
        data=UserResponse.model_validate(user),
    )
