"""bundle template published versions

Revision ID: 0029_bundle_template_versions
Revises: 0028_returns_rate_indexes
Create Date: 2026-01-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0029_bundle_template_versions"
down_revision = "0028_returns_rate_indexes"
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
        "bundle_template_versions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "template_id",
            sa.String(length=36),
            sa.ForeignKey("bundle_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_code", sa.String(length=32), nullable=False),
        sa.Column("template_name", sa.String(length=128), nullable=True),
        sa.Column("version_status", sa.String(length=32), nullable=False, server_default="published"),
        sa.Column("version_label", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("published_by", sa.String(length=64), nullable=True),
        sa.Column("components", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_index("ix_bundle_template_versions_template_id", "bundle_template_versions", ["template_id"], unique=False)
    op.create_index("ix_bundle_template_versions_template_code", "bundle_template_versions", ["template_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bundle_template_versions_template_code", table_name="bundle_template_versions")
    op.drop_index("ix_bundle_template_versions_template_id", table_name="bundle_template_versions")
    op.drop_table("bundle_template_versions")

