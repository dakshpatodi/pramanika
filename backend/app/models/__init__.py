"""
ORM models package.

Every model module is imported here so that:
1. `Base.metadata` is fully populated the moment `app.models` is imported
   anywhere (Alembic's env.py relies on this for autogenerate).
2. Other layers (repositories, services) can do `from app.models import User`
   instead of reaching into `app.models.user` directly.

Phase 3+ will add one line here per new entity, e.g. `from app.models.product import Product`.
"""

from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole

__all__ = ["User", "UserRole", "RevokedToken"]