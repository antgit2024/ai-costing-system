"""process feedback for AI corpus

Revision ID: 0021_process_feedback
Revises: 0020_merge_heads_0019_and_stub
Create Date: 2025-12-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0021_process_feedback"
down_revision = "0020_merge_heads_0019_and_stub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "process_feedback",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("process_id", sa.String(length=36), sa.ForeignKey("processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("product_line_tag", sa.String(length=64), nullable=True),
        sa.Column("team_name", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=True),
        sa.Column("actual_minutes", sa.Numeric(10, 2), nullable=True),
        sa.Column("actual_cost", sa.Numeric(18, 6), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_success", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_process_feedback_process_id", "process_feedback", ["process_id"])


def downgrade() -> None:
    op.drop_index("ix_process_feedback_process_id", table_name="process_feedback")
    op.drop_table("process_feedback")


