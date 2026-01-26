"""shipment costing results + inventory deduction lines (for 2025 no-snapshot mode)

Revision ID: 0027_shipment_costing_results_no_snapshot
Revises: 0026_order_keys_for_shipments_and_returns
Create Date: 2026-01-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0027_shipment_costing_results_no_snapshot"
down_revision = "0026_order_keys_for_shipments_and_returns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    json_obj_default = sa.text("'{}'::json") if dialect == "postgresql" else sa.text("'{}'")
    now_default = sa.text("now()") if dialect == "postgresql" else sa.text("CURRENT_TIMESTAMP")

    op.create_table(
        "shipment_costing_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("shipment_line_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="2026"),
        sa.Column("sku_code", sa.String(length=64), nullable=True),
        sa.Column("model_version_id", sa.String(length=36), nullable=True),
        sa.Column("spec_hash", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=True),
        sa.Column("qty", sa.Numeric(18, 6), nullable=True),
        sa.Column("cost_total", sa.Numeric(18, 6), nullable=True),
        sa.Column("cost_material_total", sa.Numeric(18, 6), nullable=True),
        sa.Column("cost_process_total", sa.Numeric(18, 6), nullable=True),
        sa.Column("cost_overhead_total", sa.Numeric(18, 6), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.Column("deduction_job_id", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["shipment_line_id"], ["shipment_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["shipment_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_version_id"], ["product_model_versions.id"]),
        sa.UniqueConstraint("shipment_line_id", name="uq_shipment_costing_results_line"),
    )
    # indexes are created automatically by SQLAlchemy when using `index=True` in models,
    # but we explicitly create the ones we rely on in queries.
    op.create_index("ix_shipment_costing_results_batch_id", "shipment_costing_results", ["batch_id"])
    op.create_index("ix_shipment_costing_results_mode", "shipment_costing_results", ["mode"])
    op.create_index("ix_shipment_costing_results_model_version_id", "shipment_costing_results", ["model_version_id"])
    op.create_index("ix_shipment_costing_results_sku_code", "shipment_costing_results", ["sku_code"])
    op.create_index("ix_shipment_costing_results_spec_hash", "shipment_costing_results", ["spec_hash"])
    op.create_index("ix_shipment_costing_results_computed_at", "shipment_costing_results", ["computed_at"])

    op.create_table(
        "shipment_inventory_deduction_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("shipment_line_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="2026"),
        sa.Column("material_id", sa.String(length=36), nullable=True),
        sa.Column("material_code", sa.String(length=64), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["shipment_line_id"], ["shipment_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["shipment_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
    )
    op.create_index("ix_shipment_inventory_deduction_lines_line", "shipment_inventory_deduction_lines", ["shipment_line_id"])
    op.create_index("ix_shipment_inventory_deduction_lines_batch_id", "shipment_inventory_deduction_lines", ["batch_id"])
    op.create_index("ix_shipment_inventory_deduction_lines_mode", "shipment_inventory_deduction_lines", ["mode"])
    op.create_index(
        "ix_shipment_inventory_deduction_lines_material_id", "shipment_inventory_deduction_lines", ["material_id"]
    )
    op.create_index(
        "ix_shipment_inventory_deduction_lines_material_code", "shipment_inventory_deduction_lines", ["material_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_shipment_inventory_deduction_lines_material_code", table_name="shipment_inventory_deduction_lines")
    op.drop_index("ix_shipment_inventory_deduction_lines_material_id", table_name="shipment_inventory_deduction_lines")
    op.drop_index("ix_shipment_inventory_deduction_lines_mode", table_name="shipment_inventory_deduction_lines")
    op.drop_index("ix_shipment_inventory_deduction_lines_batch_id", table_name="shipment_inventory_deduction_lines")
    op.drop_index("ix_shipment_inventory_deduction_lines_line", table_name="shipment_inventory_deduction_lines")
    op.drop_table("shipment_inventory_deduction_lines")

    op.drop_index("ix_shipment_costing_results_computed_at", table_name="shipment_costing_results")
    op.drop_index("ix_shipment_costing_results_spec_hash", table_name="shipment_costing_results")
    op.drop_index("ix_shipment_costing_results_sku_code", table_name="shipment_costing_results")
    op.drop_index("ix_shipment_costing_results_model_version_id", table_name="shipment_costing_results")
    op.drop_index("ix_shipment_costing_results_mode", table_name="shipment_costing_results")
    op.drop_index("ix_shipment_costing_results_batch_id", table_name="shipment_costing_results")
    op.drop_table("shipment_costing_results")

