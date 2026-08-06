"""
Revoked-token repository - the only place that reads/writes the
refresh-token denylist (see app/models/revoked_token.py).
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import RevokedToken


class TokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def is_revoked(self, jti: uuid.UUID) -> bool:
        return self.db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None

    def revoke(self, jti: uuid.UUID, expires_at: datetime) -> None:
        """Idempotent by design: refresh rotation and logout can both
        legitimately try to revoke the same token in edge cases (e.g. a
        double-submitted logout request), so revoking an already-revoked
        jti is a no-op rather than a unique-constraint error.

        Stages the insert only - does NOT commit. The calling service
        owns the transaction boundary."""
        if self.is_revoked(jti):
            return
        self.db.add(RevokedToken(jti=jti, expires_at=expires_at))