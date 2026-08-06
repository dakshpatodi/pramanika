"""
User repository - the only place in the codebase that writes SQLAlchemy
queries against the `users` table.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_phone(self, phone_number: str) -> Optional[User]:
        return self.db.query(User).filter(User.phone_number == phone_number).first()

    def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def create(self, user: User) -> User:
        """Stages the insert only - does NOT commit. The calling service
        owns the transaction boundary (see AuthService), so that a
        multi-step operation can commit or roll back as one unit rather
        than each repository call committing independently."""
        self.db.add(user)
        return user

    def save(self, user: User) -> User:
        """Stages an update to an already-persistent User (e.g. setting
        `last_login`). `db.add()` on an object already in the session is
        a no-op for identity purposes, but keeps the intent explicit:
        this method exists so the service layer never touches
        `self.db` directly for something the repository should own."""
        self.db.add(user)
        return user