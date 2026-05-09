"""expand tag columns to text

Revision ID: 0031_expand_tag_columns_to_text
Revises: 0030_add_tag_to_shipment_and_aftersales
Create Date: 2026-03-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0031_expand_tag_columns_to_text"
down_revision = "0030_add_tag_to_shipment_and_aftersales"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "shipment_lines",
        "tag",
        type_=sa.Text(),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )
    op.alter_column(
        "after_sales_lines",
        "tag",
        type_=sa.Text(),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "after_sales_lines",
        "tag",
        type_=sa.String(length=64),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "tag",
        type_=sa.String(length=64),
        existing_type=sa.Text(),
        existing_nullable=True,
    )

