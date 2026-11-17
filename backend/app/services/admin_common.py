"""Small helpers shared by the admin write services (Phase 9)."""

import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AdminConflictError

AUDIT_TEXT_LIMIT = 200


@contextmanager
def admin_transaction(
    db: Session,
    *,
    conflict_labels: Optional[Dict[str, str]] = None,
    check_messages: Optional[Dict[str, str]] = None,
):
    """Commit when the block succeeds, roll back when it raises. A database
    uniqueness race (two admins saving the same SKU at once) surfaces as a
    clean 409 naming the field, never a 500. `conflict_labels` maps a fragment
    of the violated constraint/index name to a field label. `check_messages`
    does the same for CHECK constraints, with a full message to show."""
    try:
        yield
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict_from(exc, conflict_labels or {}, check_messages or {}) from exc
    except BaseException:
        db.rollback()
        raise


def _conflict_from(exc: IntegrityError, labels: Dict[str, str], messages: Dict[str, str]) -> AdminConflictError:
    constraint = str(getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or "")
    detail = (constraint + " " + str(exc.orig)).lower()
    for fragment, message in messages.items():
        if fragment in detail:
            return AdminConflictError(message)
    for fragment, label in labels.items():
        if fragment in detail:
            return AdminConflictError(f"{label}: that value is already in use.")
    return AdminConflictError("This change conflicts with existing data. Refresh and try again.")


def audit_value(value: Any) -> Any:
    """Audit-safe value: UUIDs as text, long text cut at 200 characters."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) and len(value) > AUDIT_TEXT_LIMIT:
        return value[:AUDIT_TEXT_LIMIT] + "..."
    return value


def snapshot(obj: Any, fields: Iterable[str]) -> Dict[str, Any]:
    return {name: audit_value(getattr(obj, name)) for name in fields}
