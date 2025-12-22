"""shipment import -> spec cache -> bom snapshots + exception queue (MVP)

Revision ID: 0017_shipment_import_bom_snapshots_mvp
Revises: 0016_line_variants_mvp
Create Date: 2025-12-22 00:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0017_shipment_import_bom_snapshots_mvp"
down_revision = "0016_line_variants_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shipment_import_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("export_date", sa.String(length=32), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processing"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exception_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_hash", name="uq_shipment_import_file_hash"),
    )
    op.create_index(
        "ix_shipment_import_batches_file_hash",
        "shipment_import_batches",
        ["file_hash"],
    )

    op.create_table(
        "shipment_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shipment_no", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("channel", sa.String(length=128), nullable=True),
        sa.Column("sku_code", sa.String(length=64), nullable=True),
        sa.Column("spec_text", sa.Text(), nullable=True),
        sa.Column("spec_hash", sa.String(length=64), nullable=True),
        sa.Column("qty", sa.Numeric(18, 6), nullable=True),
        sa.Column("revenue_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("external_line_key_hash", sa.String(length=64), nullable=False),
        sa.Column("revision_group_hash", sa.String(length=64), nullable=True),
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("raw_row", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("normalize_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["shipment_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["shipment_lines.id"]),
        sa.UniqueConstraint("external_line_key_hash", name="uq_shipment_external_line_hash"),
    )
    op.create_index("ix_shipment_lines_batch", "shipment_lines", ["batch_id"])
    op.create_index("ix_shipment_lines_sku", "shipment_lines", ["sku_code"])
    op.create_index("ix_shipment_lines_shipment_no", "shipment_lines", ["shipment_no"])
    op.create_index("ix_shipment_lines_spec_hash", "shipment_lines", ["spec_hash"])
    op.create_index("ix_shipment_lines_revision_group", "shipment_lines", ["revision_group_hash"])

    op.create_table(
        "spec_parse_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("spec_text", sa.Text(), nullable=False),
        sa.Column("tokens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("dimensions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("parser_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("parse", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("spec_hash", name="uq_spec_parse_spec_hash"),
    )
    op.create_index("ix_spec_parse_snapshots_spec_hash", "spec_parse_snapshots", ["spec_hash"])

    op.create_table(
        "bom_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("shipment_line_id", sa.String(length=36), nullable=False),
        sa.Column("shipment_no", sa.String(length=64), nullable=True),
        sa.Column("sku_code", sa.String(length=64), nullable=True),
        sa.Column("model_version_id", sa.String(length=36), nullable=True),
        sa.Column("spec_hash", sa.String(length=64), nullable=True),
        sa.Column("qty", sa.Numeric(18, 6), nullable=True),
        sa.Column("final_lines", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("trace", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["shipment_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shipment_line_id"], ["shipment_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_version_id"], ["product_model_versions.id"]),
    )
    op.create_index("ix_bom_snapshots_batch", "bom_snapshots", ["batch_id"])
    op.create_index("ix_bom_snapshots_line", "bom_snapshots", ["shipment_line_id"])
    op.create_index("ix_bom_snapshots_sku", "bom_snapshots", ["sku_code"])
    op.create_index("ix_bom_snapshots_shipment_no", "bom_snapshots", ["shipment_no"])
    op.create_index("ix_bom_snapshots_spec_hash", "bom_snapshots", ["spec_hash"])

    op.create_table(
        "shipment_exception_queue",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("shipment_line_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["shipment_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shipment_line_id"], ["shipment_lines.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_shipment_exception_batch", "shipment_exception_queue", ["batch_id"])
    op.create_index("ix_shipment_exception_reason", "shipment_exception_queue", ["reason"])


def downgrade() -> None:
    op.drop_index("ix_shipment_exception_reason", table_name="shipment_exception_queue")
    op.drop_index("ix_shipment_exception_batch", table_name="shipment_exception_queue")
    op.drop_table("shipment_exception_queue")
    op.drop_index("ix_bom_snapshots_spec_hash", table_name="bom_snapshots")
    op.drop_index("ix_bom_snapshots_shipment_no", table_name="bom_snapshots")
    op.drop_index("ix_bom_snapshots_sku", table_name="bom_snapshots")
    op.drop_index("ix_bom_snapshots_line", table_name="bom_snapshots")
    op.drop_index("ix_bom_snapshots_batch", table_name="bom_snapshots")
    op.drop_table("bom_snapshots")
    op.drop_index("ix_spec_parse_snapshots_spec_hash", table_name="spec_parse_snapshots")
    op.drop_table("spec_parse_snapshots")
    op.drop_index("ix_shipment_lines_revision_group", table_name="shipment_lines")
    op.drop_index("ix_shipment_lines_spec_hash", table_name="shipment_lines")
    op.drop_index("ix_shipment_lines_shipment_no", table_name="shipment_lines")
    op.drop_index("ix_shipment_lines_sku", table_name="shipment_lines")
    op.drop_index("ix_shipment_lines_batch", table_name="shipment_lines")
    op.drop_table("shipment_lines")
    op.drop_index("ix_shipment_import_batches_file_hash", table_name="shipment_import_batches")
    op.drop_table("shipment_import_batches")


