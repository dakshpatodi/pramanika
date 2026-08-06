"""create users table

Revision ID: 813754ecafab
Revises:
Create Date: 2026-08-02 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "813754ecafab"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Defined once and reused in both upgrade() and downgrade() so the two
# stay in sync - this is the standard pattern for native Postgres enums
# in Alembic, since `op.create_table` does not create/drop the enum TYPE
# for you the way `Base.metadata.create_all()` would.
user_role_enum = postgresql.ENUM("customer", "admin", name="user_role")


def upgrade() -> None:
    # The enum type must exist before any column can reference it.
    user_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("customer", "admin", name="user_role", create_type=False),
            server_default="customer",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("phone_number", name=op.f("uq_users_phone_number")),
    )


def downgrade() -> None:
    op.drop_table("users")

    # Drop the enum type only after the column/table that depends on it is gone.
    user_role_enum.drop(op.get_bind(), checkfirst=True)