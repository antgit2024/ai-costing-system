"""expand shipment line id columns

Revision ID: 0032_expand_shipment_line_id_columns
Revises: 0031_expand_tag_columns_to_text
Create Date: 2026-03-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0032_expand_shipment_line_id_columns"
down_revision = "0031_expand_tag_columns_to_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "shipment_lines",
        "shipment_no",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "order_no",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "sku_code",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "product_link_id",
        type_=sa.String(length=255),
        existing_type=sa.String(length=128),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "channel",
        type_=sa.String(length=255),
        existing_type=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "shipment_lines",
        "channel",
        type_=sa.String(length=128),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "product_link_id",
        type_=sa.String(length=128),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "sku_code",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "order_no",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "shipment_lines",
        "shipment_no",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )

