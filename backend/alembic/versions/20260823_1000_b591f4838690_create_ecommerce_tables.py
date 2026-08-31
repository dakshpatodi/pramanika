"""create ecommerce catalogue, cart, wishlist, order, coupon, payment, review tables

Revision ID: b591f4838690
Revises: a58e21f7c3d4
Create Date: 2026-08-23 10:00:00.000000

Creates 14 new tables for Phase 3 (categories, products, inventory,
addresses, carts, cart_items, wishlists, wishlist_items, orders,
order_items, coupons, payments, reviews) plus 5 new Postgres enum types.

Does NOT touch `users` or `revoked_tokens` in any way - this migration
only adds new tables and one partial index; nothing here drops, alters,
or recreates existing Phase 1/2 objects.

Tables are created in FK-dependency order: a table only appears after
every table it references via ForeignKey. Enum types are created
immediately before the first table that uses them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b591f4838690"
down_revision: Union[str, None] = "a58e21f7c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


weight_unit_enum = postgresql.ENUM("g", "kg", "ml", "l", name="weight_unit")
order_status_enum = postgresql.ENUM(
    "pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded", name="order_status"
)
order_payment_status_enum = postgresql.ENUM("pending", "paid", "failed", "refunded", name="order_payment_status")
discount_type_enum = postgresql.ENUM("percentage", "fixed_amount", name="discount_type")
payment_transaction_status_enum = postgresql.ENUM(
    "initiated", "authorized", "captured", "failed", "refunded", name="payment_transaction_status"
)


def upgrade() -> None:
    bind = op.get_bind()

    # --- categories --------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_categories_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"])

    # --- products ------------------------------------------------------
    weight_unit_enum.create(bind, checkfirst=True)
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("short_description", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("weight", sa.Numeric(10, 3), nullable=True),
        sa.Column(
            "weight_unit", postgresql.ENUM("g", "kg", "ml", "l", name="weight_unit", create_type=False), nullable=True
        ),
        sa.Column("ingredients", sa.Text(), nullable=True),
        sa.Column("nutritional_information", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_products_category_id_categories"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("slug", name=op.f("uq_products_slug")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
    )
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"])
    op.create_index(op.f("ix_products_slug"), "products", ["slug"])
    op.create_index(op.f("ix_products_sku"), "products", ["sku"])
    op.create_index(op.f("ix_products_is_active"), "products", ["is_active"])

    # --- inventory -------------------------------------------------------
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), server_default="10", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_inventory_quantity_non_negative")),
        sa.CheckConstraint("reserved_quantity >= 0", name=op.f("ck_inventory_reserved_quantity_non_negative")),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_inventory_product_id_products"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory")),
        sa.UniqueConstraint("product_id", name=op.f("uq_inventory_product_id")),
    )

    # --- addresses -------------------------------------------------------
    op.create_table(
        "addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("address_line_1", sa.String(length=255), nullable=False),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("postal_code", sa.String(length=10), nullable=False),
        sa.Column("country", sa.String(length=100), server_default="India", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_addresses_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(op.f("ix_addresses_user_id"), "addresses", ["user_id"])
    # Partial unique index: at most one is_default=true row per user.
    op.create_index(
        "uq_addresses_one_default_per_user",
        "addresses",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    # --- carts / cart_items ------------------------------------------
    op.create_table(
        "carts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_carts_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carts")),
        sa.UniqueConstraint("user_id", name=op.f("uq_carts_user_id")),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_cart_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["carts.id"], name=op.f("fk_cart_items_cart_id_carts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_cart_items_product_id_products"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cart_items")),
        sa.UniqueConstraint("cart_id", "product_id", name=op.f("uq_cart_items_cart_id_product_id")),
    )

    # --- wishlists / wishlist_items -----------------------------------
    op.create_table(
        "wishlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_wishlists_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wishlists")),
        sa.UniqueConstraint("user_id", name=op.f("uq_wishlists_user_id")),
    )

    op.create_table(
        "wishlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wishlist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["wishlist_id"], ["wishlists.id"], name=op.f("fk_wishlist_items_wishlist_id_wishlists"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_wishlist_items_product_id_products"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wishlist_items")),
        sa.UniqueConstraint("wishlist_id", "product_id", name=op.f("uq_wishlist_items_wishlist_id_product_id")),
    )

    # --- coupons -----------------------------------------------------
    discount_type_enum.create(bind, checkfirst=True)
    op.create_table(
        "coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "discount_type",
            postgresql.ENUM("percentage", "fixed_amount", name="discount_type", create_type=False),
            nullable=False,
        ),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("minimum_order_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("maximum_discount_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("discount_value > 0", name=op.f("ck_coupons_discount_value_positive")),
        sa.CheckConstraint("used_count >= 0", name=op.f("ck_coupons_used_count_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coupons")),
        sa.UniqueConstraint("code", name=op.f("uq_coupons_code")),
    )
    op.create_index(op.f("ix_coupons_code"), "coupons", ["code"])

    # --- orders / order_items -----------------------------------------
    order_status_enum.create(bind, checkfirst=True)
    order_payment_status_enum.create(bind, checkfirst=True)
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_number", sa.String(length=30), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipping_address_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipping_full_name", sa.String(length=150), nullable=True),
        sa.Column("shipping_phone_number", sa.String(length=20), nullable=True),
        sa.Column("shipping_address_line_1", sa.String(length=255), nullable=True),
        sa.Column("shipping_address_line_2", sa.String(length=255), nullable=True),
        sa.Column("shipping_city", sa.String(length=100), nullable=True),
        sa.Column("shipping_state", sa.String(length=100), nullable=True),
        sa.Column("shipping_postal_code", sa.String(length=10), nullable=True),
        sa.Column("shipping_country", sa.String(length=100), nullable=True),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("tax_amount", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("delivery_charge", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("coupon_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded",
                name="order_status", create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "payment_status",
            postgresql.ENUM("pending", "paid", "failed", "refunded", name="order_payment_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("subtotal >= 0", name=op.f("ck_orders_subtotal_non_negative")),
        sa.CheckConstraint("total_amount >= 0", name=op.f("ck_orders_total_amount_non_negative")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_orders_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["shipping_address_id"],
            ["addresses.id"],
            name=op.f("fk_orders_shipping_address_id_addresses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["coupon_id"], ["coupons.id"], name=op.f("fk_orders_coupon_id_coupons"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("order_number", name=op.f("uq_orders_order_number")),
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])

    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_name_snapshot", sa.String(length=200), nullable=False),
        sa.Column("sku_snapshot", sa.String(length=50), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_items_quantity_positive")),
        sa.CheckConstraint("unit_price >= 0", name=op.f("ck_order_items_unit_price_non_negative")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_order_items_order_id_orders"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_order_items_product_id_products"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
    )

    # --- payments -------------------------------------------------------
    payment_transaction_status_enum.create(bind, checkfirst=True)
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_gateway", sa.String(length=50), nullable=False),
        sa.Column("gateway_order_id", sa.String(length=255), nullable=True),
        sa.Column("gateway_payment_id", sa.String(length=255), nullable=True),
        sa.Column("gateway_signature", sa.String(length=500), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "initiated", "authorized", "captured", "failed", "refunded",
                name="payment_transaction_status", create_type=False,
            ),
            server_default="initiated",
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_payments_order_id_orders"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"])

    # --- reviews -------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_verified_purchase", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name=op.f("ck_reviews_rating_range")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_reviews_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_reviews_product_id_products"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("user_id", "product_id", name=op.f("uq_reviews_user_id_product_id")),
    )


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("payments")
    payment_transaction_status_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("order_items")
    op.drop_table("orders")
    order_payment_status_enum.drop(op.get_bind(), checkfirst=True)
    order_status_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("coupons")
    discount_type_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("wishlist_items")
    op.drop_table("wishlists")
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_table("addresses")
    op.drop_table("inventory")
    op.drop_table("products")
    weight_unit_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("categories")