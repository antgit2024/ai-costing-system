"""taxonomy dictionary management (categories/scopes + external mappings)

Revision ID: 0019_taxonomy_management
Revises: 0018_sku_master_import_mvp
Create Date: 2025-12-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0019_taxonomy_management"
down_revision = "0018_sku_master_import_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "taxonomy_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'local'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("domain", "name", name="uq_taxonomy_items_domain_name"),
    )
    op.create_index("ix_taxonomy_items_domain", "taxonomy_items", ["domain"])
    op.create_index("ix_taxonomy_items_active", "taxonomy_items", ["domain", "is_active"])

    op.create_table(
        "taxonomy_mappings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("external_system", sa.String(length=32), nullable=False, server_default=sa.text("'yida'")),
        sa.Column("external_value", sa.String(length=255), nullable=False),
        sa.Column("taxonomy_item_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["taxonomy_item_id"],
            ["taxonomy_items.id"],
            name="fk_taxonomy_mappings_item",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "domain",
            "external_system",
            "external_value",
            name="uq_taxonomy_mappings_domain_system_value",
        ),
    )
    op.create_index("ix_taxonomy_mappings_domain", "taxonomy_mappings", ["domain"])
    op.create_index("ix_taxonomy_mappings_item", "taxonomy_mappings", ["taxonomy_item_id"])


def downgrade() -> None:
    op.drop_index("ix_taxonomy_mappings_item", table_name="taxonomy_mappings")
    op.drop_index("ix_taxonomy_mappings_domain", table_name="taxonomy_mappings")
    op.drop_table("taxonomy_mappings")

    op.drop_index("ix_taxonomy_items_active", table_name="taxonomy_items")
    op.drop_index("ix_taxonomy_items_domain", table_name="taxonomy_items")
    op.drop_table("taxonomy_items")


