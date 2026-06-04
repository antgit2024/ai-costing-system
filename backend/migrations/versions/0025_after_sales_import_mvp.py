"""after-sales import (xlsx) + exception queue (MVP, analytics-ready)

Revision ID: 0025_after_sales_import_mvp
Revises: 0024_shipping_rules
Create Date: 2026-01-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0025_after_sales_import_mvp"
down_revision = "0024_shipping_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    json_obj_default = sa.text("'{}'::json") if dialect == "postgresql" else sa.text("'{}'")
    json_arr_default = sa.text("'[]'::json") if dialect == "postgresql" else sa.text("'[]'")
    bool_false = sa.text("false") if dialect == "postgresql" else sa.text("0")
    bool_true = sa.text("true") if dialect == "postgresql" else sa.text("1")
    now_default = sa.text("now()") if dialect == "postgresql" else sa.text("CURRENT_TIMESTAMP")

    op.create_table(
        "after_sales_import_batches",
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
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("result", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.UniqueConstraint("file_hash", name="uq_after_sales_import_file_hash"),
    )
    op.create_index(
        "ix_after_sales_import_batches_file_hash",
        "after_sales_import_batches",
        ["file_hash"],
    )

    op.create_table(
        "after_sales_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("after_sales_no", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("channel", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("product_code", sa.String(length=128), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("spec_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("sale_unit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("return_qty", sa.Numeric(18, 6), nullable=True),
        sa.Column("actual_return_qty", sa.Numeric(18, 6), nullable=True),
        sa.Column("refund_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("allocated_refund_amount", sa.Numeric(18, 6), nullable=True),
        # Optional: resolved sku_code from SkuMaster for analytics & model-level attribution
        sa.Column("sku_code", sa.String(length=64), nullable=True),
        sa.Column("external_line_key_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_row", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("normalize_warnings", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["batch_id"], ["after_sales_import_batches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("external_line_key_hash", name="uq_after_sales_external_line_hash"),
    )
    op.create_index("ix_after_sales_lines_batch", "after_sales_lines", ["batch_id"])
    op.create_index("ix_after_sales_lines_after_sales_no", "after_sales_lines", ["after_sales_no"])
    op.create_index("ix_after_sales_lines_channel", "after_sales_lines", ["channel"])
    op.create_index("ix_after_sales_lines_product_code", "after_sales_lines", ["product_code"])
    op.create_index("ix_after_sales_lines_sku_code", "after_sales_lines", ["sku_code"])
    op.create_index("ix_after_sales_lines_occurred_at", "after_sales_lines", ["occurred_at"])

    op.create_table(
        "after_sales_exception_queue",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("after_sales_line_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["batch_id"], ["after_sales_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["after_sales_line_id"], ["after_sales_lines.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_after_sales_exception_batch", "after_sales_exception_queue", ["batch_id"])
    op.create_index("ix_after_sales_exception_reason", "after_sales_exception_queue", ["reason"])


def downgrade() -> None:
    op.drop_index("ix_after_sales_exception_reason", table_name="after_sales_exception_queue")
    op.drop_index("ix_after_sales_exception_batch", table_name="after_sales_exception_queue")
    op.drop_table("after_sales_exception_queue")
    op.drop_index("ix_after_sales_lines_occurred_at", table_name="after_sales_lines")
    op.drop_index("ix_after_sales_lines_sku_code", table_name="after_sales_lines")
    op.drop_index("ix_after_sales_lines_product_code", table_name="after_sales_lines")
    op.drop_index("ix_after_sales_lines_channel", table_name="after_sales_lines")
    op.drop_index("ix_after_sales_lines_after_sales_no", table_name="after_sales_lines")
    op.drop_index("ix_after_sales_lines_batch", table_name="after_sales_lines")
    op.drop_table("after_sales_lines")
    op.drop_index("ix_after_sales_import_batches_file_hash", table_name="after_sales_import_batches")
    op.drop_table("after_sales_import_batches")

