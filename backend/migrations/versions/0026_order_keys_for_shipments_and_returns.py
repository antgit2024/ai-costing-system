"""add order_no & product_link_id for shipments and after-sales

Revision ID: 0026_order_keys_for_shipments_and_returns
Revises: 0025_after_sales_import_mvp
Create Date: 2026-01-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0026_order_keys_for_shipments_and_returns"
down_revision = "0025_after_sales_import_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    # shipments: add original order no + product link id (for strong join with returns)
    with op.batch_alter_table("shipment_lines") as batch:
        batch.add_column(sa.Column("order_no", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("product_link_id", sa.String(length=128), nullable=True))
        batch.create_index("ix_shipment_lines_order_no", ["order_no"])
        batch.create_index("ix_shipment_lines_product_link_id", ["product_link_id"])

    # after-sales: add order_no + product_link_id + applied_at
    with op.batch_alter_table("after_sales_lines") as batch:
        batch.add_column(sa.Column("order_no", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("product_link_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("applied_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_after_sales_lines_order_no", ["order_no"])
        batch.create_index("ix_after_sales_lines_product_link_id", ["product_link_id"])
        batch.create_index("ix_after_sales_lines_applied_at", ["applied_at"])


def downgrade() -> None:
    with op.batch_alter_table("after_sales_lines") as batch:
        batch.drop_index("ix_after_sales_lines_applied_at")
        batch.drop_index("ix_after_sales_lines_product_link_id")
        batch.drop_index("ix_after_sales_lines_order_no")
        batch.drop_column("applied_at")
        batch.drop_column("product_link_id")
        batch.drop_column("order_no")

    with op.batch_alter_table("shipment_lines") as batch:
        batch.drop_index("ix_shipment_lines_product_link_id")
        batch.drop_index("ix_shipment_lines_order_no")
        batch.drop_column("product_link_id")
        batch.drop_column("order_no")

