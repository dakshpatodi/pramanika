"""
Reusable FastAPI dependencies for authentication and authorization.

Unlike app/core/exceptions.py (framework-agnostic DomainErrors, raised by
the service layer), everything here is allowed to know about HTTP and
FastAPI directly - these functions ARE the boundary that turns a token
problem into an actual HTTP response, via `Depends(...)` in route
signatures.
"""

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, TokenType, decode_token
from app.database.session import get_db
from app.models import User, UserRole
from app.repositories.user_repository import UserRepository

# `auto_error=False` (rather than HTTPBearer's default `True`) so a
# missing Authorization header is handled explicitly below as a 401 -
# HTTPBearer's own default behavior raises 403 for a missing header,
# which is the wrong status code: 401 means "you're not authenticated
# at all", 403 means "you are, but you're not allowed to do this."
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolves the caller's `User` from the `Authorization: Bearer <access_token>`
    header. This is the base dependency every other one here builds on.

    Looks the user up in the database on every call (rather than trusting
    the token's claims alone) for two reasons: the token doesn't carry
    `is_active`, and using the DB's `role` rather than the token's `role`
    claim means a role change takes effect on the user's very next
    request instead of staying stale until their access token expires.

    Raises:
        HTTPException(401): header missing, token malformed/expired/wrong
            type, or the user it points to no longer exists.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError):
        # ValueError/KeyError cover a token that decodes fine but has a
        # malformed or missing `sub` claim - defensive, shouldn't happen
        # with tokens this app itself issued, but never trust input blindly.
        raise unauthorized

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise unauthorized

    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Same as `get_current_user`, but also rejects a deactivated account.

    Split into its own dependency (rather than folding the check into
    `get_current_user`) so a future endpoint that genuinely needs to
    identify a deactivated user (e.g. a "reactivate my account" flow)
    can depend on the plain `get_current_user` without this check
    getting in the way.

    Raises:
        HTTPException(403): credentials are valid, but `is_active` is False.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )
    return current_user


def require_roles(*allowed_roles: UserRole):
    """Dependency factory for role-based authorization.

    Usage:
        @router.get("/reports", dependencies=[Depends(require_roles(UserRole.ADMIN))])
        # or, to accept the result:
        def reports(user: User = Depends(require_roles(UserRole.ADMIN))): ...

    Builds on `get_current_active_user` (not `get_current_user`) so a
    deactivated admin is still rejected before the role check even runs.
    """

    def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return dependency


# The single most common case, provided as a ready-to-use dependency
# rather than making every admin-only route write require_roles(UserRole.ADMIN)
# itself. Equivalent to require_roles(UserRole.ADMIN).
require_admin = require_roles(UserRole.ADMIN)