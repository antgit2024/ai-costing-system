"""shipping rules (conditional materials by shipment/order context)

Revision ID: 0024_shipping_rules
Revises: 0023_shop_sku_mappings
Create Date: 2026-01-12 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0024_shipping_rules"
down_revision = "0023_shop_sku_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    json_obj_default = sa.text("'{}'::json") if dialect == "postgresql" else sa.text("'{}'")
    json_arr_default = sa.text("'[]'::json") if dialect == "postgresql" else sa.text("'[]'")
    bool_false = sa.text("false") if dialect == "postgresql" else sa.text("0")
    bool_true = sa.text("true") if dialect == "postgresql" else sa.text("1")
    now_default = sa.text("now()") if dialect == "postgresql" else sa.text("CURRENT_TIMESTAMP")

    op.create_table(
        "shipping_rules",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("outputs", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_index("ix_shipping_rules_rule_name", "shipping_rules", ["rule_name"])
    op.create_index("ix_shipping_rules_is_active", "shipping_rules", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_shipping_rules_is_active", table_name="shipping_rules")
    op.drop_index("ix_shipping_rules_rule_name", table_name="shipping_rules")
    op.drop_table("shipping_rules")


