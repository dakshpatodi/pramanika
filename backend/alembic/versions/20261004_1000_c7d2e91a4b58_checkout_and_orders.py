"""checkout and orders: pricing snapshot, reservation state, idempotency

Revision ID: c7d2e91a4b58
Revises: bc49db06a267
Create Date: 2026-10-04 10:00:00.000000

Phase 6 (checkout). Purely additive - nothing is dropped, no existing row
is rewritten.

orders
  taxable_amount, gst_rate   pricing snapshot (GST base and rate used)
  coupon_code                coupon code copied at checkout (coupon_id is
                             ON DELETE SET NULL, the code must survive)
  inventory_state            RESERVED / RELEASED / CONSUMED - the
                             compare-and-set gate that makes a reservation
                             release/consume happen at most once. Existing
                             rows (there are none from a real checkout
                             yet) become RELEASED: they hold nothing.
  idempotency_key,           duplicate-submission protection, enforced by a
  request_fingerprint        partial unique index on (user_id, key)
  cancelled_at

order_number_seq             source of human-facing order numbers

Database-level backstops:
  inventory   reserved_quantity <= quantity
  coupons     usage_limit IS NULL OR used_count <= usage_limit
  orders      taxable_amount >= 0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7d2e91a4b58"
down_revision: Union[str, None] = "bc49db06a267"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


order_inventory_state_enum = postgresql.ENUM("reserved", "released", "consumed", name="order_inventory_state")


def upgrade() -> None:
    bind = op.get_bind()
    order_inventory_state_enum.create(bind, checkfirst=True)

    op.execute(sa.schema.CreateSequence(sa.Sequence("order_number_seq", start=1)))

    op.add_column("orders", sa.Column("taxable_amount", sa.Numeric(10, 2), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("gst_rate", sa.Numeric(5, 4), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("coupon_code", sa.String(length=50), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "inventory_state",
            postgresql.ENUM("reserved", "released", "consumed", name="order_inventory_state", create_type=False),
            server_default="released",
            nullable=False,
        ),
    )
    op.add_column("orders", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(op.f("ck_orders_taxable_amount_non_negative"), "orders", "taxable_amount >= 0")
    op.create_index(
        "uq_orders_user_id_idempotency_key",
        "orders",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_check_constraint(
        op.f("ck_inventory_reserved_within_quantity"), "inventory", "reserved_quantity <= quantity"
    )
    op.create_check_constraint(
        op.f("ck_coupons_used_within_limit"), "coupons", "usage_limit IS NULL OR used_count <= usage_limit"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_coupons_used_within_limit"), "coupons", type_="check")
    op.drop_constraint(op.f("ck_inventory_reserved_within_quantity"), "inventory", type_="check")

    op.drop_index("uq_orders_user_id_idempotency_key", table_name="orders")
    op.drop_constraint(op.f("ck_orders_taxable_amount_non_negative"), "orders", type_="check")

    op.drop_column("orders", "cancelled_at")
    op.drop_column("orders", "request_fingerprint")
    op.drop_column("orders", "idempotency_key")
    op.drop_column("orders", "inventory_state")
    op.drop_column("orders", "coupon_code")
    op.drop_column("orders", "gst_rate")
    op.drop_column("orders", "taxable_amount")

    op.execute(sa.schema.DropSequence(sa.Sequence("order_number_seq")))
    order_inventory_state_enum.drop(op.get_bind(), checkfirst=True)