"""
JWT utilities: issuing and verifying access/refresh tokens.

Deliberately kept separate from password.py (single responsibility) and
from FastAPI entirely - this module has zero knowledge of HTTP, requests,
or dependency injection. It only knows how to mint and read tokens. That
makes it trivially unit-testable and reusable from anywhere (a CLI, a
background job) that might need to issue or check a token outside of a
request/response cycle.

The Milestone 5 FastAPI dependency (get_current_user, etc.) is the layer
that translates the exceptions raised here into HTTP 401 responses - this
module itself never raises an HTTPException.
"""

import enum
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings


class TokenType(str, enum.Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    """Base class for all token failures.

    Callers catch this (or a subclass) instead of reaching into
    python-jose's own exception hierarchy - that keeps python-jose an
    implementation detail of this module rather than a leaky abstraction
    the rest of the app has to know about.
    """


class TokenExpiredError(TokenError):
    """The token's signature is valid, but its `exp` claim has passed."""


class InvalidTokenError(TokenError):
    """The token is malformed, has a bad signature, or has the wrong `type` claim."""


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        # Unique per token. Not enforced anywhere yet in Phase 2, but
        # having it from day one means a future refresh-token denylist
        # (e.g. on logout, see Milestone 4/5) doesn't require reissuing
        # every token format again - it can just start checking `jti`
        # against a store.
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Short-lived token sent with every authenticated request.

    Carries `role` as a claim so authorization checks (Milestone 5's
    "Admin Only" / role-based dependency) can read it straight off the
    token without a database round-trip on every request.
    """
    return _create_token(
        subject=str(user_id),
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"role": role},
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Long-lived token whose only job is minting new access tokens via
    POST /api/auth/refresh. Deliberately does NOT carry a `role` claim -
    if a user's role changes, the next access token they mint will reflect
    it, rather than a stale role baked into a week-long-lived token."""
    return _create_token(
        subject=str(user_id),
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token, enforcing that it's the expected type.

    The `expected_type` check is what stops a refresh token (long-lived,
    more sensitive if leaked) from being usable as a bearer token on
    ordinary protected routes, and stops an access token from being
    usable at the /refresh endpoint.

    Raises:
        TokenExpiredError: signature is valid, but `exp` has passed.
        InvalidTokenError: bad signature, malformed token, or wrong `type` claim.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Token has expired.") from exc
    except JWTError as exc:
        raise InvalidTokenError("Token is invalid.") from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token.")

    return payload