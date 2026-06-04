"""long_tail_cogs_rate_strategies table (Issue 28)

Revision ID: 0035_long_tail_cogs_rate_strategy
Revises: 0034_integration_layer_tables
Create Date: 2026-05-07 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0035_long_tail_cogs_rate_strategy"
down_revision = "0034_integration_layer_tables"
branch_labels = None
depends_on = None


def _defaults() -> tuple[sa.TextClause, sa.TextClause, sa.TextClause]:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect == "postgresql":
        return (
            sa.text("'{}'::json"),
            sa.text("'[]'::json"),
            sa.text("now()"),
        )
    return sa.text("'{}'"), sa.text("'[]'"), sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    json_obj_default, json_arr_default, now_default = _defaults()

    op.create_table(
        "long_tail_cogs_rate_strategies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.UniqueConstraint("category", name="uq_long_tail_cogs_rate_category"),
    )
    op.create_index(
        "ix_long_tail_cogs_rate_strategies_priority",
        "long_tail_cogs_rate_strategies",
        ["priority"],
    )
    op.create_index(
        "ix_long_tail_cogs_rate_strategies_enabled",
        "long_tail_cogs_rate_strategies",
        ["enabled"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_long_tail_cogs_rate_strategies_enabled",
        table_name="long_tail_cogs_rate_strategies",
    )
    op.drop_index(
        "ix_long_tail_cogs_rate_strategies_priority",
        table_name="long_tail_cogs_rate_strategies",
    )
    op.drop_table("long_tail_cogs_rate_strategies")
