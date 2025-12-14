"""Phase 3.5 integrations tables"""

from alembic import op
import sqlalchemy as sa


revision = "0004_phase35_integrations"
down_revision = "0003_audit_logs_and_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("trace_id", sa.String(length=64), nullable=False, server_default=""),
    )

    op.create_table(
        "scenario_favorites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("scenario_id", "user_id", name="uq_scenario_favorite_user"),
    )

    op.create_table(
        "benchmark_favorites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("benchmark_key", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("benchmark_key", "user_id", name="uq_benchmark_favorite_user"),
    )

    op.create_table(
        "planner_executor_callbacks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("callback_url", sa.String(length=255), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("trace_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_versions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_executor_callbacks_scenario",
        "planner_executor_callbacks",
        ["scenario_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_executor_callbacks_scenario", table_name="planner_executor_callbacks")
    op.drop_table("planner_executor_callbacks")
    op.drop_table("benchmark_favorites")
    op.drop_table("scenario_favorites")
    op.drop_column("audit_logs", "trace_id")
