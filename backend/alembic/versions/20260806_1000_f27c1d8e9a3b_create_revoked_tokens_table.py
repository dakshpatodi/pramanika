"""create revoked_tokens table

Revision ID: f27c1d8e9a3b
Revises: 813754ecafab
Create Date: 2026-08-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f27c1d8e9a3b"
down_revision: Union[str, None] = "813754ecafab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_revoked_tokens")),
    )
    op.create_index(op.f("ix_revoked_tokens_expires_at"), "revoked_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_revoked_tokens_expires_at"), table_name="revoked_tokens")
    op.drop_table("revoked_tokens")