"""add last_login to users

Revision ID: a58e21f7c3d4
Revises: f27c1d8e9a3b
Create Date: 2026-08-06 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a58e21f7c3d4"
down_revision: Union[str, None] = "f27c1d8e9a3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_login")