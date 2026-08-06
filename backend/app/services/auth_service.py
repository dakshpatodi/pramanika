"""
Authentication business logic.

Route handlers (app/api/auth.py) stay thin and just call into this
service - duplicate checks, credential verification, token issuance, and
rotation all live here, independent of any HTTP concerns.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    AccountInactiveError,
    DuplicateEmailError,
    DuplicatePhoneError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class AuthService:
    """Depends on `UserRepository` and `TokenRepository` via constructor
    injection rather than talking to SQLAlchemy directly - this class
    only knows each repository's method names, not how they're implemented."""

    def __init__(self, db: Session):
        # Kept alongside the repositories (rather than only inside them)
        # because THIS class owns the transaction boundary now: each
        # repository method only stages changes (`db.add(...)`), and the
        # service commits once per logical operation, rolling back if any
        # step in that operation fails. See Milestone 4 review notes.
        self.db = db
        self.repository = UserRepository(db)
        self.token_repository = TokenRepository(db)

    def register_user(self, payload: UserCreate) -> User:
        """Create a new customer account.

        Raises:
            DuplicateEmailError: an account with this email already exists.
            DuplicatePhoneError: an account with this phone number already exists.
        """
        if self.repository.get_by_email(payload.email):
            raise DuplicateEmailError(payload.email)

        if self.repository.get_by_phone(payload.phone_number):
            raise DuplicatePhoneError(payload.phone_number)

        user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone_number=payload.phone_number,
            password_hash=hash_password(payload.password),
        )
        try:
            user = self.repository.create(user)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(user)
        return user

    def login(self, email: str, password: str) -> tuple[str, str, User]:
        """Authenticate a user, record the login, and issue a new
        access/refresh token pair.

        Raises:
            InvalidCredentialsError: no account with this email, or the
                password doesn't match - same error either way (see
                Milestone 4 notes on user enumeration).
            AccountInactiveError: credentials are correct, but the
                account has been deactivated.
        """
        user = self.repository.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise AccountInactiveError()

        try:
            user.last_login = datetime.now(timezone.utc)
            self.repository.save(user)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(user)

        access_token = create_access_token(user.id, user.role.value)
        refresh_token = create_refresh_token(user.id)
        return access_token, refresh_token, user

    def refresh(self, refresh_token: str) -> tuple[str, str]:
        """Validate a refresh token, revoke it (rotation), and issue a
        brand-new access/refresh pair.

        Rotation means the presented refresh token is revoked the moment
        it's used, regardless of whether the caller goes on to use the
        new pair - this limits a leaked refresh token to exactly one use
        before it's permanently dead.

        Raises:
            InvalidRefreshTokenError: the token is malformed, expired,
                the wrong type, already revoked, or belongs to a user
                that no longer exists or has been deactivated.
        """
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except TokenError:
            raise InvalidRefreshTokenError()

        jti = uuid.UUID(payload["jti"])
        if self.token_repository.is_revoked(jti):
            raise InvalidRefreshTokenError()

        user = self.repository.get_by_id(uuid.UUID(payload["sub"]))
        if not user or not user.is_active:
            raise InvalidRefreshTokenError()

        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        try:
            self.token_repository.revoke(jti, expires_at)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        new_access_token = create_access_token(user.id, user.role.value)
        new_refresh_token = create_refresh_token(user.id)
        return new_access_token, new_refresh_token

    def logout(self, refresh_token: str) -> None:
        """Revoke a refresh token so it can never be used again, even
        before it naturally expires.

        A token that's already invalid/expired/revoked is treated as a
        no-op success rather than an error - from the client's point of
        view, logging out with a token that's already dead should still
        just mean "you're logged out."
        """
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except TokenError:
            return

        jti = uuid.UUID(payload["jti"])
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        try:
            self.token_repository.revoke(jti, expires_at)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise