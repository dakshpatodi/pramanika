"""add coupon_id to carts

Revision ID: bc49db06a267
Revises: 20a281139110
Create Date: 2026-09-10 09:00:00.000000

Phase 5, Decision B: a Cart can now carry an applied coupon, persisting
across page reloads until removed or the cart is cleared. Mirrors
Order.coupon_id's exact column shape (nullable, ON DELETE SET NULL, no
separate index) - if a coupon is later deactivated/deleted, any cart
referencing it just quietly loses the reference rather than the cart
itself being affected.

Purely additive: one nullable column and one FK. No existing data is
touched, nothing is dropped or altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "bc49db06a267"
down_revision: Union[str, None] = "20a281139110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("carts", sa.Column("coupon_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_carts_coupon_id_coupons"),
        "carts",
        "coupons",
        ["coupon_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_carts_coupon_id_coupons"), "carts", type_="foreignkey")
    op.drop_column("carts", "coupon_id")