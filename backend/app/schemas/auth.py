"""
Authentication request/response schemas: login, token issuance, refresh,
and logout. Kept separate from schemas/user.py, which covers the User
resource itself rather than the auth flow around it.
"""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    """No strength/length validation here on purpose - those rules only
    make sense at registration time, when a password is being *chosen*.
    At login, an overlong or oddly-shaped password should just fail
    authentication like any other wrong password (verify_password
    already handles this safely), not surface a different-shaped 422
    that could hint at why it failed."""


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    """Included so the frontend doesn't have to immediately follow login
    with a GET /users/me call just to render a name/avatar/role. Reuses
    the same UserResponse as the registration endpoint (never includes
    password_hash) rather than a second, slimmer schema - it's the
    account owner's own data being returned to them, so there's no
    reason to trim it further here."""


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str