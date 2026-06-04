"""sku master table for ERP import + shipment backfill (MVP)

Revision ID: 0018_sku_master_import_mvp
Revises: 0017_shipment_import_bom_snapshots_mvp
Create Date: 2025-12-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0018_sku_master_import_mvp"
down_revision = "0017_shipment_import_bom_snapshots_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sku_master",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("erp_sku_barcode", sa.String(length=64), nullable=False),
        sa.Column("platform_product_id", sa.String(length=64), nullable=True),
        sa.Column("platform_sku_id", sa.String(length=64), nullable=True),
        sa.Column("channel", sa.String(length=128), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("product_code", sa.String(length=128), nullable=True),
        sa.Column("spec_text", sa.Text(), nullable=True),
        sa.Column("images", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("match_status", sa.String(length=64), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("erp_sku_barcode", name="uq_sku_master_barcode"),
    )
    op.create_index("ix_sku_master_barcode", "sku_master", ["erp_sku_barcode"])


def downgrade() -> None:
    op.drop_index("ix_sku_master_barcode", table_name="sku_master")
    op.drop_table("sku_master")


