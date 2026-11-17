"""admin audit events: an append-only trail of administrator changes

Revision ID: f7b3c9d15a42
Revises: e4a91c7b3d26
Create Date: 2026-10-25 10:00:00.000000

Phase 9 (Admin Dashboard). One new table and nothing else - no existing
table or row is touched.

admin_audit_events
  one row per administrator change, written in the same transaction as the
  change itself. admin_user_id is SET NULL if the user is ever deleted;
  admin_email keeps who it was. before/after hold only the changed fields.
  Indexed by (entity_type, entity_id, created_at) for "history of this
  order/product" and by created_at for the recent-activity list.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f7b3c9d15a42"
down_revision: Union[str, None] = "e4a91c7b3d26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("admin_email", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["users.id"], name=op.f("fk_admin_audit_events_admin_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_events")),
    )
    op.create_index(
        "ix_admin_audit_events_entity", "admin_audit_events", ["entity_type", "entity_id", "created_at"], unique=False
    )
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_admin_audit_events_created_at", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_entity", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
