"""add composite indexes for returns-rate queries

Revision ID: 0028_returns_rate_indexes
Revises: 0027_shipment_costing_results_no_snapshot
Create Date: 2026-01-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0028_returns_rate_indexes"
down_revision = "0027_shipment_costing_results_no_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These analytics queries are dominated by:
    # - time window filter on shipment_lines.completed_at
    # - optional filters: channel / sku_code
    # - strong-key join: order_no + product_link_id + sku_code
    #
    # Single-column indexes exist, but composite indexes help the planner pick
    # better plans and avoid large hash joins/sequential scans on big datasets.
    with op.batch_alter_table("shipment_lines") as batch:
        batch.create_index(
            "ix_shipment_lines_completed_at_channel_sku_code",
            ["completed_at", "channel", "sku_code"],
        )
        batch.create_index(
            "ix_shipment_lines_order_no_product_link_id_sku_code",
            ["order_no", "product_link_id", "sku_code"],
        )
        batch.create_index("ix_shipment_lines_channel", ["channel"])

    with op.batch_alter_table("after_sales_lines") as batch:
        batch.create_index(
            "ix_after_sales_lines_order_no_product_link_id_sku_code",
            ["order_no", "product_link_id", "sku_code"],
        )


def downgrade() -> None:
    with op.batch_alter_table("after_sales_lines") as batch:
        batch.drop_index("ix_after_sales_lines_order_no_product_link_id_sku_code")

    with op.batch_alter_table("shipment_lines") as batch:
        batch.drop_index("ix_shipment_lines_channel")
        batch.drop_index("ix_shipment_lines_order_no_product_link_id_sku_code")
        batch.drop_index("ix_shipment_lines_completed_at_channel_sku_code")

