"""
User-related request/response schemas.
"""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import UserRole

# Loose E.164-style check: optional leading "+", first digit 1-9, then
# 6-14 more digits (7-15 digits total). Intentionally not stricter than
# this - real-world phone formats vary too much by country to hardcode
# further here; tighten per-market if/when that's actually needed.
_PHONE_PATTERN = r"^\+?[1-9]\d{6,14}$"


class UserCreate(BaseModel):
    """Registration request payload (POST /api/auth/register).

    Deliberately has NO `role` field. Every self-registered account is a
    `customer` - that's the `User` model's database-level default. If a
    `role` field existed here, any client could POST `{"role": "admin"}`
    and grant themselves admin access; admin accounts must be provisioned
    out of band, never through this endpoint.
    """

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(
        pattern=_PHONE_PATTERN,
        description="Digits only, optional leading '+', e.g. +919876543210",
    )
    password: str = Field(min_length=8, max_length=72)
    confirm_password: str

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password must contain at least one special character.")
        return value

    @model_validator(mode="after")
    def _passwords_match(self) -> "UserCreate":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match.")
        return self


class UserResponse(BaseModel):
    """Public-facing user representation - notably excludes `password_hash`.

    `from_attributes=True` lets this be built directly from the
    SQLAlchemy `User` ORM instance (`UserResponse.model_validate(user)`)
    without manually mapping every field.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    role: UserRole
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime] = None
    created_at: datetime