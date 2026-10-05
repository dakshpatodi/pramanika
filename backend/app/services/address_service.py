"""
Address business logic (Phase 6: list + add).

The owner is always the authenticated user's id handed in by the router.
"""

import uuid
from contextlib import contextmanager
from typing import Iterator, List

from sqlalchemy.orm import Session

from app.models import Address
from app.repositories.address_repository import AddressRepository
from app.schemas.address import AddressCreateRequest

DEFAULT_COUNTRY = "India"


class AddressService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AddressRepository(db)

    def list_addresses(self, user_id: uuid.UUID) -> List[Address]:
        return self.repository.list_for_user(user_id)

    def create_address(self, user_id: uuid.UUID, payload: AddressCreateRequest) -> Address:
        """Store a new address. The user's first address becomes their
        default automatically; asking for `is_default` on a later one moves
        the default to it (the old default is cleared in the same
        transaction, so there is never a moment with two - or none)."""
        with self._transaction():
            self.repository.lock_owner(user_id)

            make_default = payload.is_default or self.repository.count_for_user(user_id) == 0
            if make_default:
                self.repository.clear_default(user_id)

            address = Address(
                user_id=user_id,
                full_name=payload.full_name,
                phone_number=payload.phone_number,
                address_line_1=payload.address_line_1,
                address_line_2=payload.address_line_2 or None,
                city=payload.city,
                state=payload.state,
                postal_code=payload.postal_code,
                country=DEFAULT_COUNTRY,
                is_default=make_default,
            )
            self.repository.add(address)

        self.db.refresh(address)
        return address

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise