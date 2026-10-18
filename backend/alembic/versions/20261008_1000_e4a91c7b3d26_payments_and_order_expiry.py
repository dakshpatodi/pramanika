"""payments and order expiry: payment constraints, webhook events, order expires_at

Revision ID: e4a91c7b3d26
Revises: c7d2e91a4b58
Create Date: 2026-10-08 10:00:00.000000

Phase 7 (Razorpay). Extends the Phase 3 `payments` table instead of
creating a second payment table, and adds what order expiry needs.

payments (existing table, extended)
  status        gains the value 'expired'
  paid_at       when the money was captured
  refund_required
                a captured payment that does not pay a live order
                (customer paid after cancel/expiry, or paid twice)
  constraints   amount > 0; 3-letter currency; a Razorpay row has a
                gateway order id; paid_at is set exactly for captured /
                refunded rows, which must have a gateway payment id;
                refund_required only on captured rows
  indexes       gateway_order_id unique; gateway_payment_id unique;
                at most ONE open (initiated/authorized) payment per order -
                the database-level guarantee behind idempotent payment
                creation

payment_webhook_events (new)
  one row per processed Razorpay webhook delivery, unique on the event id,
  so a re-delivered webhook is a no-op

orders
  expires_at            when an unpaid order releases its stock
  cancellation_reason   customer | expired; set exactly when status is
                        'cancelled' (CHECK)
  ix_orders_open_expires_at
                        partial index for the expiry sweep

Data changes (the only ones):
  - existing cancelled orders get reason 'customer'
  - existing unpaid, still-reserved orders get expires_at = now() + 30 min,
    i.e. a grace period from the moment of deployment, not an immediate
    expiry of orders created long ago
  - existing captured/refunded payment rows (there should be none) get
    paid_at = updated_at so the new CHECK can hold

If the `payments` table already holds rows that break a new constraint
(for example a razorpay row without a gateway order id) the migration stops
with a clear constraint error instead of changing anything.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4a91c7b3d26"
down_revision: Union[str, None] = "c7d2e91a4b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


order_cancellation_reason_enum = postgresql.ENUM("customer", "expired", name="order_cancellation_reason")

OPEN_ORDER_PREDICATE = "status = 'pending' AND payment_status = 'pending' AND inventory_state = 'reserved'"


def upgrade() -> None:
    bind = op.get_bind()

    # A new enum value cannot be used in the transaction that adds it, and
    # on older PostgreSQL versions cannot be added inside one at all.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_transaction_status ADD VALUE IF NOT EXISTS 'expired'")

    order_cancellation_reason_enum.create(bind, checkfirst=True)

    # --- payments -------------------------------------------------------
    op.add_column("payments", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("refund_required", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute("UPDATE payments SET paid_at = updated_at WHERE status IN ('captured', 'refunded') AND paid_at IS NULL")

    op.create_check_constraint(op.f("ck_payments_amount_positive"), "payments", "amount > 0")
    op.create_check_constraint(op.f("ck_payments_currency_three_letters"), "payments", "char_length(currency) = 3")
    op.create_check_constraint(
        op.f("ck_payments_razorpay_has_gateway_order_id"),
        "payments",
        "payment_gateway <> 'razorpay' OR gateway_order_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_payments_paid_at_matches_status"),
        "payments",
        "(status IN ('captured', 'refunded')) = (paid_at IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_payments_paid_has_gateway_payment_id"),
        "payments",
        "status NOT IN ('captured', 'refunded') OR gateway_payment_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_payments_refund_required_only_when_captured"),
        "payments",
        "NOT refund_required OR status = 'captured'",
    )
    op.create_index(
        "uq_payments_gateway_order_id",
        "payments",
        ["gateway_order_id"],
        unique=True,
        postgresql_where=sa.text("gateway_order_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_gateway_payment_id",
        "payments",
        ["gateway_payment_id"],
        unique=True,
        postgresql_where=sa.text("gateway_payment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_one_open_per_order",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('initiated', 'authorized')"),
    )

    # --- payment_webhook_events ----------------------------------------
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("gateway_order_id", sa.String(length=255), nullable=True),
        sa.Column("gateway_payment_id", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=50), server_default="received", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_webhook_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_payment_webhook_events_event_id")),
    )

    # --- orders ---------------------------------------------------------
    op.add_column("orders", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "cancellation_reason",
            postgresql.ENUM("customer", "expired", name="order_cancellation_reason", create_type=False),
            nullable=True,
        ),
    )
    op.execute("UPDATE orders SET cancellation_reason = 'customer' WHERE status = 'cancelled'")
    op.execute(f"UPDATE orders SET expires_at = now() + interval '30 minutes' WHERE {OPEN_ORDER_PREDICATE}")

    op.create_check_constraint(
        op.f("ck_orders_cancellation_reason_matches_status"),
        "orders",
        "(status = 'cancelled') = (cancellation_reason IS NOT NULL)",
    )
    op.create_index(
        "ix_orders_open_expires_at",
        "orders",
        ["expires_at"],
        postgresql_where=sa.text(OPEN_ORDER_PREDICATE),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_orders_open_expires_at", table_name="orders")
    op.drop_constraint(op.f("ck_orders_cancellation_reason_matches_status"), "orders", type_="check")
    op.drop_column("orders", "cancellation_reason")
    op.drop_column("orders", "expires_at")
    order_cancellation_reason_enum.drop(bind, checkfirst=True)

    op.drop_table("payment_webhook_events")

    op.drop_index("uq_payments_one_open_per_order", table_name="payments")
    op.drop_index("uq_payments_gateway_payment_id", table_name="payments")
    op.drop_index("uq_payments_gateway_order_id", table_name="payments")
    op.drop_constraint(op.f("ck_payments_refund_required_only_when_captured"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_paid_has_gateway_payment_id"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_paid_at_matches_status"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_razorpay_has_gateway_order_id"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_currency_three_letters"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_amount_positive"), "payments", type_="check")
    op.drop_column("payments", "refund_required")
    op.drop_column("payments", "paid_at")

    # PostgreSQL cannot drop one value from an enum: rebuild the type
    # without 'expired'. Any expired attempt becomes 'failed' (the closest
    # pre-Phase-7 meaning: an attempt that did not succeed).
    op.execute("UPDATE payments SET status = 'failed' WHERE status = 'expired'")
    op.execute("ALTER TABLE payments ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE payment_transaction_status RENAME TO payment_transaction_status_old")
    postgresql.ENUM(
        "initiated", "authorized", "captured", "failed", "refunded", name="payment_transaction_status"
    ).create(bind)
    op.execute(
        "ALTER TABLE payments ALTER COLUMN status TYPE payment_transaction_status "
        "USING status::text::payment_transaction_status"
    )
    op.execute("ALTER TABLE payments ALTER COLUMN status SET DEFAULT 'initiated'")
    op.execute("DROP TYPE payment_transaction_status_old")
