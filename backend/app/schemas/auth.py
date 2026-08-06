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


class LoginResponse(TokenResponse):
    """Extends TokenResponse with the user's own profile - used ONLY by
    /login, not /refresh. Kept as a separate schema (rather than making
    `user` an optional field on TokenResponse) so /refresh's response
    shape never has to account for a field it doesn't have a value for.

    Included so the frontend doesn't have to immediately follow login
    with a GET /users/me call just to render a name/avatar/role. Reuses
    the same UserResponse as the registration endpoint (never includes
    password_hash) rather than a second, slimmer schema - it's the
    account owner's own data being returned to them, so there's no
    reason to trim it further here.
    """

    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str