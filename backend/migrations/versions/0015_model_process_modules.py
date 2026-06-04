"""Model versions + module components (catch-up for missing revisions)

Revision ID: 0015_model_process_modules
Revises: 0006_yida_sync_jobs
Create Date: 2025-12-22 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0015_model_process_modules"
down_revision = "0006_yida_sync_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- code generator counters ---
    op.create_table(
        "code_counters",
        sa.Column("prefix", sa.String(length=16), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # --- process module components ---
    op.create_table(
        "process_module_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("module_id", sa.String(length=36), nullable=False),
        sa.Column("material_kind", sa.String(length=16), nullable=False, server_default="real"),
        sa.Column("material_ref_id", sa.String(length=36), nullable=True),
        sa.Column("material_code", sa.String(length=64), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=True),
        sa.Column("calculation_method", sa.String(length=32), nullable=False, server_default="count"),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("loss_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_category", sa.String(length=128), nullable=True),
        sa.Column("selection_notes", sa.Text(), nullable=True),
        sa.Column("loss_notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["module_id"], ["process_modules.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_process_module_materials_module",
        "process_module_materials",
        ["module_id", "is_archived"],
    )

    op.create_table(
        "process_module_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("module_id", sa.String(length=36), nullable=False),
        sa.Column("process_id", sa.String(length=36), nullable=True),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("team_name", sa.String(length=128), nullable=True),
        sa.Column("pricing_method", sa.String(length=32), nullable=False, server_default="count"),
        sa.Column("work_minutes", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["module_id"], ["process_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_process_module_steps_module",
        "process_module_steps",
        ["module_id", "is_archived"],
    )

    # --- product model version snapshots (standard/published) ---
    op.create_table(
        "product_model_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("version_kind", sa.String(length=32), nullable=False, server_default="sample"),
        sa.Column("version_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version_label", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("published_by", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_id"], ["product_models.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_product_model_versions_model", "product_model_versions", ["model_id"])

    op.create_table(
        "model_version_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("material_type", sa.String(length=16), nullable=False, server_default="real"),
        sa.Column("material_ref_id", sa.String(length=36), nullable=False),
        sa.Column("material_code", sa.String(length=64), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=True),
        sa.Column("calculation_method", sa.String(length=32), nullable=False, server_default="count"),
        sa.Column("base_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("loss_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["version_id"], ["product_model_versions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_model_version_materials_version",
        "model_version_materials",
        ["version_id", "is_archived"],
    )

    op.create_table(
        "model_version_processes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("process_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["version_id"], ["product_model_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_model_version_processes_version",
        "model_version_processes",
        ["version_id", "is_archived"],
    )

    op.create_table(
        "model_version_modules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("module_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["version_id"], ["product_model_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["process_modules.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_model_version_modules_version",
        "model_version_modules",
        ["version_id", "is_archived"],
    )

    # --- sku_code -> version binding (published) ---
    op.create_table(
        "sku_model_version_mapping",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("model_version_id", sa.String(length=36), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_version_id"], ["product_model_versions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_sku_model_version_mapping_sku",
        "sku_model_version_mapping",
        ["sku_code", "is_archived"],
    )
    op.create_index(
        "ix_sku_model_version_mapping_version",
        "sku_model_version_mapping",
        ["model_version_id", "is_archived"],
    )

    # --- model -> process module bindings (to build version snapshots) ---
    op.create_table(
        "model_process_modules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("module_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_id"], ["product_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["process_modules.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_model_process_modules_model",
        "model_process_modules",
        ["model_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_process_modules_model", table_name="model_process_modules")
    op.drop_table("model_process_modules")
    op.drop_index("ix_sku_model_version_mapping_version", table_name="sku_model_version_mapping")
    op.drop_index("ix_sku_model_version_mapping_sku", table_name="sku_model_version_mapping")
    op.drop_table("sku_model_version_mapping")
    op.drop_index("ix_model_version_modules_version", table_name="model_version_modules")
    op.drop_table("model_version_modules")
    op.drop_index("ix_model_version_processes_version", table_name="model_version_processes")
    op.drop_table("model_version_processes")
    op.drop_index("ix_model_version_materials_version", table_name="model_version_materials")
    op.drop_table("model_version_materials")
    op.drop_index("ix_product_model_versions_model", table_name="product_model_versions")
    op.drop_table("product_model_versions")
    op.drop_index("ix_process_module_steps_module", table_name="process_module_steps")
    op.drop_table("process_module_steps")
    op.drop_index("ix_process_module_materials_module", table_name="process_module_materials")
    op.drop_table("process_module_materials")
    op.drop_table("code_counters")


