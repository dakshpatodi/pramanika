"""
Address business logic (Phase 6: list + add; Phase 8: edit, delete, set default).

The owner is always the authenticated user's id handed in by the router.

The default-address rule, kept by every write here: a customer with at least
one address has EXACTLY one default (the first address added is the default;
the partial unique index in the database forbids a second one). Each write
that touches it is one transaction under the owner lock, so two tabs cannot
leave none or two.
"""

import uuid
from contextlib import contextmanager
from typing import Iterator, List

from sqlalchemy.orm import Session

from app.core.exceptions import AddressLimitReachedError, AddressNotFoundError
from app.models import Address
from app.repositories.address_repository import AddressRepository
from app.repositories.cart_repository import CartRepository
from app.schemas.address import AddressCreateRequest, AddressUpdateRequest

DEFAULT_COUNTRY = "India"
MAX_ADDRESSES_PER_USER = 20
"""The list endpoint is unbounded by design of the UI (a short list), so the
number of rows is capped instead."""


class AddressService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AddressRepository(db)
        self.carts = CartRepository(db)

    def list_addresses(self, user_id: uuid.UUID) -> List[Address]:
        return self.repository.list_for_user(user_id)

    def create_address(self, user_id: uuid.UUID, payload: AddressCreateRequest) -> Address:
        """Store a new address. The user's first address becomes their
        default automatically; asking for `is_default` on a later one moves
        the default to it (the old default is cleared in the same
        transaction, so there is never a moment with two - or none).

        Raises:
            AddressLimitReachedError: the user already has MAX_ADDRESSES_PER_USER.
        """
        with self._transaction():
            self.repository.lock_owner(user_id)

            existing = self.repository.count_for_user(user_id)
            if existing >= MAX_ADDRESSES_PER_USER:
                raise AddressLimitReachedError(MAX_ADDRESSES_PER_USER)
            make_default = payload.is_default or existing == 0
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

    # --- Phase 8 -----------------------------------------------------------

    def update_address(self, user_id: uuid.UUID, address_id: uuid.UUID, payload: AddressUpdateRequest) -> Address:
        """Change the fields that were sent. Never touches `is_default`,
        `user_id` or `country`, and never touches any order: an order placed
        with this address keeps its own copy of the old details.

        Raises:
            AddressNotFoundError: not found, or it belongs to someone else.
        """
        with self._transaction():
            self.repository.lock_owner(user_id)
            address = self.repository.get_for_user(address_id, user_id)
            if address is None:
                raise AddressNotFoundError()
            for name in payload.model_fields_set:
                value = getattr(payload, name)
                if name == "address_line_2":
                    value = value or None  # "" and null both clear the optional line
                setattr(address, name, value)

        self.db.refresh(address)
        return address

    def set_default(self, user_id: uuid.UUID, address_id: uuid.UUID) -> List[Address]:
        """Make this address the default (the previous one stops being it in
        the same transaction). Already the default: nothing changes. Returns
        the user's addresses in list order.

        Raises:
            AddressNotFoundError: not found, or it belongs to someone else.
        """
        with self._transaction():
            self.repository.lock_owner(user_id)
            address = self.repository.get_for_user(address_id, user_id)
            if address is None:
                raise AddressNotFoundError()
            if not address.is_default:
                self.repository.clear_default(user_id)
                address.is_default = True
        self.db.expire_all()
        return self.repository.list_for_user(user_id)

    def delete_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> List[Address]:
        """Delete one saved address and return the ones that remain.

        * Orders already placed with it are untouched: they keep their own
          copy of the delivery address; only the optional link back to the
          saved address is cleared by the database.
        * If it was the default, the most recently added remaining address
          becomes the default in the same transaction.
        * The user's cart row is locked first, exactly as checkout locks it
          before it reads the address, so a delete can never slip in between
          checkout choosing an address and saving the order (which would
          otherwise fail that checkout). A delete that wins the race makes the
          checkout answer "address not found"; one that loses waits, then
          deletes.

        Raises:
            AddressNotFoundError: not found, or it belongs to someone else.
        """
        with self._transaction():
            self.repository.lock_owner(user_id)
            self.carts.get_by_user_id(user_id, for_update=True)  # same lock order as checkout
            address = self.repository.get_for_user(address_id, user_id)
            if address is None:
                raise AddressNotFoundError()
            was_default = address.is_default

            if self.repository.delete_for_user(address_id, user_id) != 1:  # pragma: no cover - locked above
                raise AddressNotFoundError()
            self.db.expunge(address)

            if was_default:
                replacement = self.repository.newest_for_user(user_id)
                if replacement is not None:
                    replacement.is_default = True

        self.db.expire_all()
        return self.repository.list_for_user(user_id)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
