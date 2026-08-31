"""fix redundant unique constraints on slug/sku/code columns

Revision ID: 20a281139110
Revises: b591f4838690
Create Date: 2026-08-24 09:00:00.000000

`Category.slug`, `Product.slug`, `Product.sku`, and `Coupon.code` are all
declared in their models with BOTH `unique=True` and `index=True` on the
same column - SQLAlchemy's convention for that combination is a single
index that is itself unique, not a separate UniqueConstraint plus a
separate plain (non-unique) Index.

The original migration (b591f4838690) created both objects for these 4
columns - redundant, and the plain index was non-unique, which didn't
actually match what the models declare. `alembic revision --autogenerate`
caught this discrepancy. This migration reconciles the database to match
the models exactly: drop each redundant UniqueConstraint, then recreate
the corresponding index with `unique=True`.

No data is affected - these are purely index/constraint-level changes.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20a281139110"
down_revision: Union[str, None] = "b591f4838690"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, unique_constraint_name, index_name)
_TARGETS = [
    ("categories", "slug", "uq_categories_slug", "ix_categories_slug"),
    ("products", "slug", "uq_products_slug", "ix_products_slug"),
    ("products", "sku", "uq_products_sku", "ix_products_sku"),
    ("coupons", "code", "uq_coupons_code", "ix_coupons_code"),
]


def upgrade() -> None:
    for table, column, constraint_name, index_name in _TARGETS:
        op.drop_constraint(constraint_name, table, type_="unique")
        op.drop_index(index_name, table_name=table)
        op.create_index(index_name, table, [column], unique=True)


def downgrade() -> None:
    for table, column, constraint_name, index_name in _TARGETS:
        op.drop_index(index_name, table_name=table)
        op.create_index(index_name, table, [column], unique=False)
        op.create_unique_constraint(constraint_name, table, [column])