"""tmall sku generator templates

Revision ID: 0033_tmall_sku_generator_templates
Revises: 0032_expand_shipment_line_id_columns
Create Date: 2026-05-04 15:55:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0033_tmall_sku_generator_templates"
down_revision = "0032_expand_shipment_line_id_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tmall_sku_generator_templates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False, server_default="家居布艺"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("matrix_count", sa.Integer(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tmall_sku_generator_templates_type", "tmall_sku_generator_templates", ["type"])
    op.create_index("ix_tmall_sku_generator_templates_updated_at", "tmall_sku_generator_templates", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_tmall_sku_generator_templates_updated_at", table_name="tmall_sku_generator_templates")
    op.drop_index("ix_tmall_sku_generator_templates_type", table_name="tmall_sku_generator_templates")
    op.drop_table("tmall_sku_generator_templates")
