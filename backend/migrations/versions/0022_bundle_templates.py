"""bundle templates addressed by BUNDLE:CODE

Revision ID: 0022_bundle_templates
Revises: 0021_process_feedback
Create Date: 2026-01-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0022_bundle_templates"
down_revision = "0021_process_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    json_obj_default = sa.text("'{}'::json") if dialect == "postgresql" else sa.text("'{}'")
    json_arr_default = sa.text("'[]'::json") if dialect == "postgresql" else sa.text("'[]'")
    bool_false = sa.text("false") if dialect == "postgresql" else sa.text("0")
    now_default = sa.text("now()") if dialect == "postgresql" else sa.text("CURRENT_TIMESTAMP")
    op.create_table(
        "bundle_templates",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("components", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_index("ix_bundle_templates_code", "bundle_templates", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_bundle_templates_code", table_name="bundle_templates")
    op.drop_table("bundle_templates")


