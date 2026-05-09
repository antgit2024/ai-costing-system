"""add tag column to shipment_lines and after_sales_lines

Revision ID: 0030_add_tag_to_shipment_and_aftersales
Revises: 0029_bundle_template_versions
Create Date: 2026-01-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0030_add_tag_to_shipment_and_aftersales"
down_revision = "0029_bundle_template_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipment_lines",
        sa.Column("tag", sa.String(64), nullable=True),
    )
    op.create_index("ix_shipment_lines_tag", "shipment_lines", ["tag"])

    op.add_column(
        "after_sales_lines",
        sa.Column("tag", sa.String(64), nullable=True),
    )
    op.create_index("ix_after_sales_lines_tag", "after_sales_lines", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_after_sales_lines_tag", table_name="after_sales_lines")
    op.drop_column("after_sales_lines", "tag")

    op.drop_index("ix_shipment_lines_tag", table_name="shipment_lines")
    op.drop_column("shipment_lines", "tag")
