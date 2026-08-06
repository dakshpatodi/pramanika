"""
Authentication endpoints.

Milestone 3 added POST /api/auth/register. Milestone 4 adds
POST /api/auth/login, POST /api/auth/refresh, and POST /api/auth/logout
to this same router. None of these three require an Authorization
header - login takes credentials directly, and refresh/logout both take
the refresh token in the request body. Protecting routes with an access
token (a dependency like get_current_user) is Milestone 5's job.
"""


from fastapi import APIRouter, Depends, Request, status
from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, LogoutRequest, RefreshRequest, TokenResponse
from app.schemas.common import APIResponse
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> APIResponse[UserResponse]:
    service = AuthService(db)
    user = service.register_user(payload)
    return APIResponse(
        success=True,
        message="Registration successful.",
        data=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive an access/refresh token pair",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> APIResponse[LoginResponse]:
    service = AuthService(db)
    access_token, refresh_token, user = service.login(payload.email, payload.password)
    return APIResponse(
        success=True,
        message="Login successful.",
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        ),
    )


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token for a new access/refresh token pair",
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> APIResponse[TokenResponse]:
    service = AuthService(db)
    access_token, refresh_token = service.refresh(payload.refresh_token)
    return APIResponse(
        success=True,
        message="Token refreshed successfully.",
        data=TokenResponse(access_token=access_token, refresh_token=refresh_token),
    )


@router.post(
    "/logout",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Revoke a refresh token",
)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> APIResponse[None]:
    service = AuthService(db)
    service.logout(payload.refresh_token)
    return APIResponse(success=True, message="Logged out successfully.", data=None)