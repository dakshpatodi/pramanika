"""
Creating and removing administrators (Phase 9) - the logic behind
`python -m scripts.create_admin`.

There is deliberately no HTTP route for any of this: an administrator is an
already-registered account promoted from the command line by someone with
access to the server. No password is read, stored or printed here, and no
credential exists in code.

Every change is audited in the same transaction as the role change.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from app.core.exceptions import (
    AdminAccountError,
    DomainError,
    AdminAccountNotFoundError,
    LastAdminError,
)
from app.models import User, UserRole
from app.repositories.admin_account_repository import AdminAccountRepository
from app.services.audit_service import CLI_ACTOR, AuditService


@dataclass(frozen=True)
class AccountChange:
    user: User
    changed: bool  # False when the account already had the requested role (idempotent)


class AdminAccountService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminAccountRepository(db)
        self.audit = AuditService(db)

    def _find(self, email: str, *, lock: bool = True) -> User:
        cleaned = (email or "").strip()
        if not cleaned:
            raise AdminAccountError("An email address is required.")
        matches = self.repository.find_by_email(cleaned, lock=lock)
        if not matches:
            raise AdminAccountNotFoundError(cleaned)
        if len(matches) > 1:
            raise AdminAccountError(
                f"More than one account matches '{cleaned}' when case is ignored; refusing to guess which one."
            )
        return matches[0]

    def promote(self, email: str) -> AccountChange:
        try:
            return self._promote(email)
        except DomainError:
            self.db.rollback()  # a refusal must not leave row locks behind
            raise

    def _promote(self, email: str) -> AccountChange:
        """Make a registered, active account an administrator. Promoting an
        administrator again changes nothing and is not an error."""
        user = self._find(email)
        if not user.is_active:
            raise AdminAccountError("That account is deactivated; it cannot be made an administrator.")
        if user.role == UserRole.ADMIN:
            self.db.rollback()
            return AccountChange(user, changed=False)
        before = {"role": user.role.value}
        user.role = UserRole.ADMIN
        self.audit.record(
            admin=None,
            actor_label=CLI_ACTOR,
            action="user.promote_admin",
            entity_type="user",
            entity_id=user.id,
            before=before,
            after={"role": UserRole.ADMIN.value},
        )
        self._commit()
        return AccountChange(user, changed=True)

    def revoke(self, email: str) -> AccountChange:
        try:
            return self._revoke(email)
        except DomainError:
            self.db.rollback()
            raise

    def _revoke(self, email: str) -> AccountChange:
        user = self._find(email, lock=False)
        if user.role != UserRole.ADMIN:
            self.db.rollback()
            return AccountChange(user, changed=False)
        # Lock order matters: every administrator row first (in id order, the
        # same for every caller), THEN the target. Locking the target first
        # lets two simultaneous revocations each wait for the other's row.
        active_admins = self.repository.lock_active_admins()
        self.db.refresh(user, with_for_update=True)
        if user.role != UserRole.ADMIN:  # changed while we waited
            self.db.rollback()
            return AccountChange(user, changed=False)
        if user.is_active and len(active_admins) <= 1:
            raise LastAdminError()
        user.role = UserRole.CUSTOMER
        self.audit.record(
            admin=None,
            actor_label=CLI_ACTOR,
            action="user.revoke_admin",
            entity_type="user",
            entity_id=user.id,
            before={"role": UserRole.ADMIN.value},
            after={"role": UserRole.CUSTOMER.value},
        )
        self._commit()
        return AccountChange(user, changed=True)

    def list_admins(self) -> List[User]:
        return self.repository.list_admins()

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
