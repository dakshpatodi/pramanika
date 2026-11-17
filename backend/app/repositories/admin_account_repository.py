"""Queries behind promoting/revoking administrators (Phase 9)."""

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User, UserRole


class AdminAccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_email(self, email: str, *, lock: bool = True) -> List[User]:
        """Case-insensitive, so `Admin@Example.com` finds the account registered
        as `admin@example.com`. Returns a list so the caller can refuse an
        ambiguous match (two accounts differing only by case).

        `lock=True` row-locks the match. A caller that will also call
        `lock_active_admins` must pass `lock=False` and lock the admins FIRST:
        taking locks in different orders is how two requests deadlock."""
        query = select(User).where(func.lower(User.email) == email.strip().lower())
        if lock:
            query = query.with_for_update()
        return list(self.db.execute(query).scalars().all())

    def lock_active_admins(self) -> List[User]:
        """Every active administrator, row-locked in id order, so two concurrent
        revocations cannot both see 'someone else is still an admin'."""
        return list(
            self.db.execute(
                select(User)
                .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
                .order_by(User.id)
                .with_for_update()
            )
            .scalars()
            .all()
        )

    def list_admins(self) -> List[User]:
        return list(self.db.execute(select(User).where(User.role == UserRole.ADMIN).order_by(User.email)).scalars().all())
