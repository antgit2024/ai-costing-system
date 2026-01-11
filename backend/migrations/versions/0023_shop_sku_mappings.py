"""shop sku mappings (preserve platform_sku_id dimension)

Revision ID: 0023_shop_sku_mappings
Revises: 0022_bundle_templates
Create Date: 2026-01-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0023_shop_sku_mappings"
down_revision = "0022_bundle_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_sku_mappings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel", sa.String(length=128), nullable=True),
        sa.Column("platform_product_id", sa.String(length=64), nullable=True),
        sa.Column("platform_sku_id", sa.String(length=64), nullable=False),
        sa.Column("erp_sku_barcode", sa.String(length=64), nullable=True),
        sa.Column("shop_spec_code", sa.String(length=128), nullable=True),
        sa.Column("production_process", sa.Text(), nullable=True),
        sa.Column("match_status", sa.String(length=64), nullable=True),
        sa.Column("match_method", sa.String(length=64), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("channel", "platform_sku_id", "is_archived", name="uq_shop_sku_channel_platform_sku_active"),
    )
    op.create_index("ix_shop_sku_platform_sku", "shop_sku_mappings", ["platform_sku_id"])
    op.create_index("ix_shop_sku_barcode", "shop_sku_mappings", ["erp_sku_barcode"])
    op.create_index("ix_shop_sku_channel", "shop_sku_mappings", ["channel"])
    op.create_index("ix_shop_sku_platform_product", "shop_sku_mappings", ["platform_product_id"])


def downgrade() -> None:
    op.drop_index("ix_shop_sku_platform_product", table_name="shop_sku_mappings")
    op.drop_index("ix_shop_sku_channel", table_name="shop_sku_mappings")
    op.drop_index("ix_shop_sku_barcode", table_name="shop_sku_mappings")
    op.drop_index("ix_shop_sku_platform_sku", table_name="shop_sku_mappings")
    op.drop_table("shop_sku_mappings")


