"""
Profile business logic (Phase 8). Authentication lives in `auth_service.py`.

The caller is the authenticated user, handed in by the router - there is no
way to name another user here.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicatePhoneError
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdateRequest


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)

    def update_profile(self, user: User, payload: UserUpdateRequest) -> User:
        """Apply the fields that were sent (first name, last name, phone).

        Nothing else on the user can change here: the request schema refuses
        any other key, and only these three attributes are ever written.
        Sending the values the user already has changes nothing (no write).

        Raises:
            DuplicatePhoneError: another account already uses that phone number.
        """
        changes = {
            name: getattr(payload, name)
            for name in payload.model_fields_set
            if getattr(user, name) != getattr(payload, name)
        }
        if not changes:
            return user

        phone = changes.get("phone_number")
        if phone is not None:
            other = self.repository.get_by_phone(phone)
            if other is not None and other.id != user.id:
                raise DuplicatePhoneError(phone)

        try:
            for name, value in changes.items():
                setattr(user, name, value)
            self.db.commit()
        except IntegrityError:
            # Someone registered or changed to this number between our check
            # and the commit: the unique constraint is the last line of defence.
            self.db.rollback()
            if phone is not None:
                other = self.repository.get_by_phone(phone)
                if other is not None and other.id != user.id:
                    raise DuplicatePhoneError(phone) from None
            raise
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(user)
        return user
