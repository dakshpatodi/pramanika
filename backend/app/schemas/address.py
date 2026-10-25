"""
Address request / response schemas.

Phase 6 added list + add; Phase 8 adds edit (`AddressUpdateRequest`), delete and
set-default (those two take no body). The requests deliberately have NO `user_id`
(the owner is always the authenticated user) and NO `country` (Pramanika
delivers within India for now, so every address is stored as "India" and
the 6-digit PIN rule below is always the right one).
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Same phone rule as registration (schemas/user.py) so a number that was
# valid at sign-up is valid here.
from app.schemas.user import _PHONE_PATTERN

# Indian PIN codes are six digits and never start with 0.
_PIN_PATTERN = r"^[1-9][0-9]{5}$"


class AddressCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=150)
    phone_number: str = Field(
        pattern=_PHONE_PATTERN,
        description="Digits only, optional leading '+', e.g. 9876543210 or +919876543210",
    )
    address_line_1: str = Field(min_length=1, max_length=255)
    address_line_2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(pattern=_PIN_PATTERN, description="6-digit Indian PIN code")
    is_default: bool = Field(
        default=False,
        description="Make this the default address. The first address a user adds is always the default.",
    )


class AddressUpdateRequest(BaseModel):
    """Edit one saved address (PATCH /api/addresses/{id}). Send only what changes.

    Same rules as `AddressCreateRequest`. Extra keys (`user_id`, `country`,
    `is_default`, `id`...) are refused with a 422: the owner and country are
    never client-controlled, and the default address changes only through
    its own endpoint so there is exactly one way to move it.

    `address_line_2` may be sent as null or "" to clear it; every other field
    is required on the saved address and so can be changed but not cleared.
    Editing an address never changes an order already placed with it: orders
    keep their own copy of the delivery address.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    phone_number: Optional[str] = Field(default=None, pattern=_PHONE_PATTERN)
    address_line_1: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address_line_2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, min_length=1, max_length=100)
    state: Optional[str] = Field(default=None, min_length=1, max_length=100)
    postal_code: Optional[str] = Field(default=None, pattern=_PIN_PATTERN, description="6-digit Indian PIN code")

    @model_validator(mode="after")
    def _something_to_change(self) -> "AddressUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Send at least one field to update.")
        for name in self.model_fields_set - {"address_line_2"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class AddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_number: str
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime
