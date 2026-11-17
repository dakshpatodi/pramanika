"""Shared helpers for the Phase 9 (admin) tests."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import User, UserRole
from tests.pg_support import PostgresTestCase, new_session


def build_admin_app(*, with_public: bool = True, with_shop: bool = False) -> FastAPI:
    """A FastAPI app with the admin router (and, by default, the public auth/user
    routers) on test sessions. The sandbox `app.main` is a stub, so tests mount
    routers explicitly - exactly as main.py does."""
    from app.api import auth, users
    from app.api.admin import router as admin_router

    app = FastAPI()

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.http_status, content={"success": False, "message": exc.message})

    def override_get_db():
        session = new_session()
        try:
            yield session
        finally:
            session.close()

    app.include_router(admin_router)
    if with_shop:
        from app.api import cart, categories, orders, products

        for module in (categories, products, cart, orders):
            app.include_router(module.router)
    if with_public:
        app.include_router(auth.router)
        app.include_router(users.router)
    app.dependency_overrides[get_db] = override_get_db
    return app


def bearer(user: User, *, claim_role: str = None) -> dict:
    """Authorization header for `user`. `claim_role` forges the token's role
    claim (the server must ignore it)."""
    return {"Authorization": f"Bearer {create_access_token(user.id, claim_role or user.role.value)}"}


def expired_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "type": "access",
        "role": "admin",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class AdminTestCase(PostgresTestCase):
    def make_admin(self, *, active: bool = True) -> User:
        user = self.make_user()
        user.role = UserRole.ADMIN
        user.is_active = active
        self.db.commit()
        return user

    def set_role(self, user: User, role: UserRole = None, *, active: bool = None) -> None:
        with new_session() as s:
            row = s.get(User, user.id)
            if role is not None:
                row.role = role
            if active is not None:
                row.is_active = active
            s.commit()

    def role_in_db(self, user_id) -> UserRole:
        with new_session() as s:
            return s.get(User, user_id).role
