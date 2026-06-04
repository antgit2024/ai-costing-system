"""Add planner job types and payload/result columns"""

from alembic import op
import sqlalchemy as sa


revision = "0002_phase2_jobs"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planner_import_jobs",
        sa.Column("job_type", sa.String(length=64), nullable=False, server_default="line_item_import"),
    )
    op.add_column(
        "planner_import_jobs",
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "planner_import_jobs",
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.execute(
        "UPDATE planner_import_jobs SET job_type='line_item_import' WHERE job_type IS NULL"
    )
def downgrade() -> None:
    op.drop_column("planner_import_jobs", "result")
    op.drop_column("planner_import_jobs", "payload")
    op.drop_column("planner_import_jobs", "job_type")
