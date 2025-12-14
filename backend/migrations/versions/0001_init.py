"""Initial planner schema"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cost_initiatives",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("sponsor", sa.String(length=128)),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("target_launch_date", sa.Date()),
        sa.Column("tags", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "cost_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("initiative_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64)),
        sa.Column("parent_package_id", sa.String(length=36)),
        sa.Column("owner_id", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["initiative_id"], ["cost_initiatives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_package_id"], ["cost_packages.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_cost_packages_initiative", "cost_packages", ["initiative_id"])

    op.create_table(
        "cost_line_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("reference_code", sa.String(length=64)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_cost_estimate", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("supplier_id", sa.String(length=64)),
        sa.Column("preferred_quote_id", sa.String(length=36)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["package_id"], ["cost_packages.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_cost_line_items_package", "cost_line_items", ["package_id"])

    op.create_table(
        "supplier_quotes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("contact", sa.String(length=255)),
        sa.Column("line_item_id", sa.String(length=36), nullable=False),
        sa.Column("quote_version", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("moq", sa.Integer()),
        sa.Column("lead_time_days", sa.Integer()),
        sa.Column("valid_through", sa.Date()),
        sa.Column("attachments", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["line_item_id"], ["cost_line_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("line_item_id", "quote_version", name="uq_quote_line_version"),
    )

    op.create_table(
        "input_assumptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("initiative_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(length=32)),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=128)),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["initiative_id"], ["cost_initiatives.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("initiative_id", "type", "effective_date", name="uq_assumption_version"),
    )

    op.create_table(
        "scenario_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("initiative_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("baseline_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("assumption_set_id", sa.String(length=36)),
        sa.Column("total_cost", sa.Numeric(18, 4), server_default="0"),
        sa.Column("variance_vs_baseline", sa.Numeric(18, 4)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["initiative_id"], ["cost_initiatives.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "scenario_line_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("line_item_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("fx_rate_used", sa.Numeric(18, 6)),
        sa.Column("markup_percent", sa.Numeric(5, 2)),
        sa.Column("total_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("drivers", sa.JSON(), server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["line_item_id"], ["cost_line_items.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "approval_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index("ix_approval_target", "approval_records", ["target_type", "target_id"])

    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=64)),
        sa.Column("uploader_id", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("category", sa.String(length=32)),
    )

    op.create_index("ix_attachments_target", "attachments", ["target_type", "target_id"])

    op.create_table(
        "planner_import_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("initiative_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default="0"),
        sa.Column("processed_rows", sa.Integer(), server_default="0"),
        sa.Column("error_rows", sa.Integer(), server_default="0"),
        sa.Column("errors", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["initiative_id"], ["cost_initiatives.id"], ondelete="CASCADE"),
    )


def downgrade():
    op.drop_table("planner_import_jobs")
    op.drop_index("ix_attachments_target", table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("ix_approval_target", table_name="approval_records")
    op.drop_table("approval_records")
    op.drop_table("scenario_line_snapshots")
    op.drop_table("scenario_versions")
    op.drop_table("input_assumptions")
    op.drop_table("supplier_quotes")
    op.drop_index("ix_cost_line_items_package", table_name="cost_line_items")
    op.drop_table("cost_line_items")
    op.drop_index("ix_cost_packages_initiative", table_name="cost_packages")
    op.drop_table("cost_packages")
    op.drop_table("cost_initiatives")
