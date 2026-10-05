"""
Address repository - every query that touches the addresses table.

Every read is scoped by `user_id` in the same query, so an address id that
belongs to someone else is indistinguishable from one that does not exist
(the service never has to remember to compare owners). Like the other
repositories it only stages changes; the service commits.
"""

import uuid
from typing import List, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Address, User


class AddressRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: uuid.UUID) -> List[Address]:
        """Default address first, then newest first."""
        return (
            self.db.query(Address)
            .filter(Address.user_id == user_id)
            .order_by(Address.is_default.desc(), Address.created_at.desc(), Address.id.asc())
            .all()
        )

    def get_for_user(self, address_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Address]:
        return (
            self.db.query(Address)
            .filter(Address.id == address_id, Address.user_id == user_id)
            .first()
        )

    def count_for_user(self, user_id: uuid.UUID) -> int:
        return self.db.query(Address).filter(Address.user_id == user_id).count()

    def lock_owner(self, user_id: uuid.UUID) -> None:
        """Serialise address writes of ONE user (e.g. two tabs both adding a
        default address). FOR NO KEY UPDATE conflicts with itself but not
        with the key-share locks that inserts into carts / orders take on
        the user row, so it never blocks the user's shopping."""
        self.db.query(User.id).filter(User.id == user_id).with_for_update(key_share=True).first()

    def clear_default(self, user_id: uuid.UUID) -> None:
        self.db.execute(
            update(Address)
            .where(Address.user_id == user_id, Address.is_default.is_(True))
            .values(is_default=False)
            .execution_options(synchronize_session=False)
        )

    def add(self, address: Address) -> Address:
        self.db.add(address)
        self.db.flush()  # assigns id / timestamps without committing
        return address