"""
RevokedToken ORM model.

Backs the refresh-token denylist described in Milestone 4: a row here
means the token with this `jti` must be rejected even if its signature
and `exp` claim are still otherwise valid. Only refresh tokens are ever
recorded here - access tokens are short-lived (30 min) and are never
checked against this table, since doing so on every authenticated
request would defeat the point of using stateless JWTs for access
tokens (see Milestone 4 notes).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class RevokedToken(Base):
    """A denylisted refresh token, keyed by its `jti` claim."""

    __tablename__ = "revoked_tokens"

    jti: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    """Mirrors the token's own `exp` claim. Lets a future cleanup job
    delete rows once the token would have expired naturally anyway -
    there's no need to keep denylisting a token past the point it
    couldn't be replayed even without this table."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RevokedToken jti={self.jti}>"