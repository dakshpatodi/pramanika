"""
User profile endpoints.

Milestone 5 adds GET /api/users/me - the first route in the project that
requires authentication. Everything it needs (the current user, already
loaded and confirmed active) comes from `get_current_active_user`;
the route itself does no token handling or database querying of its own.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_active_user
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/api/users", tags=["Users"])


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