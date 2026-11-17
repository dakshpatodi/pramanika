"""
Audit trail writer (Phase 9).

`AuditService.record(...)` adds one `AdminAuditEvent` to the CALLER'S session
and flushes it - it never commits. The service that makes the change commits
once, so the change and its audit row land together or not at all.

Guards (programming errors, so they raise ValueError, not a DomainError):
  - `action` must look like `entity.verb` (lower-case letters and underscores);
  - `before` / `after` may not contain a key that sounds like a secret
    (password, token, secret, hash, signature, authorization, key) at any depth;
  - values are made JSON-safe (Decimal, UUID, datetime, enum -> str/number).
"""

import enum
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AdminAuditEvent, User

_ACTION = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")
_ENTITY = re.compile(r"^[a-z][a-z_]*$")
_FORBIDDEN_KEY_PARTS = ("password", "token", "secret", "hash", "signature", "authorization", "key")

# Used as `admin_email` when the actor is the command line, not a signed-in admin.
CLI_ACTOR = "cli:create_admin"


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return _jsonable(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (uuid.UUID, datetime, date)):
        return str(value) if isinstance(value, uuid.UUID) else value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"Cannot store a {type(value).__name__} in an audit event.")


def _check_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
                raise ValueError(f"Audit event field '{key}' looks like a secret and may not be recorded.")
            _check_keys(inner)
    elif isinstance(value, (list, tuple, set)):
        for inner in value:
            _check_keys(inner)


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        admin: Optional[User],
        action: str,
        entity_type: str,
        entity_id: Optional[uuid.UUID] = None,
        before: Optional[Mapping[str, Any]] = None,
        after: Optional[Mapping[str, Any]] = None,
        actor_label: Optional[str] = None,
    ) -> AdminAuditEvent:
        """Add (and flush) one event. Pass `admin` for a signed-in administrator,
        or `actor_label` (e.g. `CLI_ACTOR`) when there is no user."""
        if not _ACTION.match(action):
            raise ValueError(f"Invalid audit action '{action}'; expected 'entity.verb'.")
        if not _ENTITY.match(entity_type):
            raise ValueError(f"Invalid audit entity type '{entity_type}'.")
        if admin is None and not actor_label:
            raise ValueError("An audit event needs an administrator or an actor label.")
        _check_keys(before)
        _check_keys(after)

        event = AdminAuditEvent(
            admin_user_id=admin.id if admin is not None else None,
            admin_email=admin.email if admin is not None else actor_label,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=_jsonable(before) if before is not None else None,
            after=_jsonable(after) if after is not None else None,
            # Stamped when written, not when the transaction began (now()): a request that
            # waited on a row lock must sort AFTER the change it waited for.
            created_at=func.clock_timestamp(),
        )
        self.db.add(event)
        self.db.flush()
        return event
