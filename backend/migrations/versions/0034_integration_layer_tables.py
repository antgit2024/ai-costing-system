"""generic integration layer tables and source provenance fields

Revision ID: 0034_integration_layer_tables
Revises: 0033_tmall_sku_generator_templates
Create Date: 2026-05-06 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0034_integration_layer_tables"
down_revision = "0033_tmall_sku_generator_templates"
branch_labels = None
depends_on = None


def _defaults() -> tuple[sa.TextClause, sa.TextClause, sa.TextClause]:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect == "postgresql":
        return (
            sa.text("'{}'::json"),
            sa.text("'[]'::json"),
            sa.text("now()"),
        )
    return sa.text("'{}'"), sa.text("'[]'"), sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    json_obj_default, _json_arr_default, now_default = _defaults()

    op.create_table(
        "integration_sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("sync_type", sa.String(length=64), nullable=False),
        sa.Column("api_method", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="pull"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("request_params", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor_start", sa.String(length=64), nullable=True),
        sa.Column("cursor_end", sa.String(length=64), nullable=True),
        sa.Column("context_id", sa.String(length=64), nullable=True),
        sa.Column("triggered_by", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_index("ix_integration_sync_runs_source_system", "integration_sync_runs", ["source_system"])
    op.create_index("ix_integration_sync_runs_sync_type", "integration_sync_runs", ["sync_type"])
    op.create_index("ix_integration_sync_runs_api_method", "integration_sync_runs", ["api_method"])
    op.create_index("ix_integration_sync_runs_direction", "integration_sync_runs", ["direction"])
    op.create_index("ix_integration_sync_runs_status", "integration_sync_runs", ["status"])
    op.create_index("ix_integration_sync_runs_context_id", "integration_sync_runs", ["context_id"])
    op.create_index("ix_integration_sync_runs_started_at", "integration_sync_runs", ["started_at"])

    op.create_table(
        "integration_api_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sync_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("api_method", sa.String(length=128), nullable=False),
        sa.Column("record_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_line_id", sa.String(length=255), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["sync_run_id"], ["integration_sync_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "source_system",
            "api_method",
            "record_type",
            "external_id",
            "external_line_id",
            "schema_version",
            name="uq_integration_api_record_identity",
        ),
    )
    op.create_index("ix_integration_api_records_sync_run_id", "integration_api_records", ["sync_run_id"])
    op.create_index("ix_integration_api_records_source_system", "integration_api_records", ["source_system"])
    op.create_index("ix_integration_api_records_api_method", "integration_api_records", ["api_method"])
    op.create_index("ix_integration_api_records_record_type", "integration_api_records", ["record_type"])
    op.create_index("ix_integration_api_records_external_id", "integration_api_records", ["external_id"])
    op.create_index("ix_integration_api_records_external_line_id", "integration_api_records", ["external_line_id"])
    op.create_index("ix_integration_api_records_payload_hash", "integration_api_records", ["payload_hash"])
    op.create_index("ix_integration_api_records_schema_version", "integration_api_records", ["schema_version"])
    op.create_index("ix_integration_api_records_fetched_at", "integration_api_records", ["fetched_at"])
    op.create_index("ix_integration_api_records_status", "integration_api_records", ["status"])

    op.create_table(
        "integration_sync_watermarks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("sync_type", sa.String(length=64), nullable=False),
        sa.Column("watermark_field", sa.String(length=64), nullable=False),
        sa.Column("watermark_value", sa.String(length=64), nullable=True),
        sa.Column("cursor_extra", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("last_sync_run_id", sa.String(length=36), nullable=True),
        sa.Column("last_advanced_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.UniqueConstraint("source_system", "sync_type", name="uq_integration_sync_watermark_identity"),
    )
    op.create_index("ix_integration_sync_watermarks_source_system", "integration_sync_watermarks", ["source_system"])
    op.create_index("ix_integration_sync_watermarks_sync_type", "integration_sync_watermarks", ["sync_type"])
    op.create_index("ix_integration_sync_watermarks_watermark_value", "integration_sync_watermarks", ["watermark_value"])
    op.create_index("ix_integration_sync_watermarks_last_advanced_at", "integration_sync_watermarks", ["last_advanced_at"])

    op.create_table(
        "integration_dead_letters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("api_method", sa.String(length=128), nullable=True),
        sa.Column("record_type", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="mapper"),
        sa.Column("sync_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_payload_id", sa.String(length=36), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_line_id", sa.String(length=255), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["sync_run_id"], ["integration_sync_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_payload_id"], ["integration_api_records.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_integration_dead_letters_source_system", "integration_dead_letters", ["source_system"])
    op.create_index("ix_integration_dead_letters_api_method", "integration_dead_letters", ["api_method"])
    op.create_index("ix_integration_dead_letters_record_type", "integration_dead_letters", ["record_type"])
    op.create_index("ix_integration_dead_letters_stage", "integration_dead_letters", ["stage"])
    op.create_index("ix_integration_dead_letters_sync_run_id", "integration_dead_letters", ["sync_run_id"])
    op.create_index("ix_integration_dead_letters_source_payload_id", "integration_dead_letters", ["source_payload_id"])
    op.create_index("ix_integration_dead_letters_external_id", "integration_dead_letters", ["external_id"])
    op.create_index("ix_integration_dead_letters_external_line_id", "integration_dead_letters", ["external_line_id"])
    op.create_index("ix_integration_dead_letters_error_type", "integration_dead_letters", ["error_type"])
    op.create_index("ix_integration_dead_letters_status", "integration_dead_letters", ["status"])
    op.create_index("ix_integration_dead_letters_last_attempt_at", "integration_dead_letters", ["last_attempt_at"])

    op.create_table(
        "integration_api_call_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sync_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("api_method", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="outbound"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("biz_code", sa.String(length=32), nullable=True),
        sa.Column("biz_sub_code", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("context_id", sa.String(length=64), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("response", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.ForeignKeyConstraint(["sync_run_id"], ["integration_sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_integration_api_call_logs_sync_run_id", "integration_api_call_logs", ["sync_run_id"])
    op.create_index("ix_integration_api_call_logs_source_system", "integration_api_call_logs", ["source_system"])
    op.create_index("ix_integration_api_call_logs_api_method", "integration_api_call_logs", ["api_method"])
    op.create_index("ix_integration_api_call_logs_direction", "integration_api_call_logs", ["direction"])
    op.create_index("ix_integration_api_call_logs_biz_code", "integration_api_call_logs", ["biz_code"])
    op.create_index("ix_integration_api_call_logs_biz_sub_code", "integration_api_call_logs", ["biz_sub_code"])
    op.create_index("ix_integration_api_call_logs_context_id", "integration_api_call_logs", ["context_id"])
    op.create_index("ix_integration_api_call_logs_requested_at", "integration_api_call_logs", ["requested_at"])

    op.create_table(
        "integration_writeback_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("api_method", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_index("ix_integration_writeback_jobs_source_system", "integration_writeback_jobs", ["source_system"])
    op.create_index("ix_integration_writeback_jobs_api_method", "integration_writeback_jobs", ["api_method"])
    op.create_index("ix_integration_writeback_jobs_target_type", "integration_writeback_jobs", ["target_type"])
    op.create_index("ix_integration_writeback_jobs_target_id", "integration_writeback_jobs", ["target_id"])
    op.create_index("ix_integration_writeback_jobs_status", "integration_writeback_jobs", ["status"])
    op.create_index("ix_integration_writeback_jobs_next_run_at", "integration_writeback_jobs", ["next_run_at"])

    # business table provenance fields (generic, not vendor-specific)
    with op.batch_alter_table("shipment_lines") as batch:
        batch.add_column(sa.Column("source_system", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_record_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_line_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_payload_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("erp_order_no", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("platform_order_no", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("sent_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("logistic_no", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("logistic_name", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("warehouse_code", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("warehouse_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("seller_memo", sa.Text(), nullable=True))
        batch.add_column(sa.Column("buyer_memo", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_shipment_lines_source_payload",
            "integration_api_records",
            ["source_payload_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_shipment_lines_source_system", ["source_system"])
        batch.create_index("ix_shipment_lines_source_record_id", ["source_record_id"])
        batch.create_index("ix_shipment_lines_source_line_id", ["source_line_id"])
        batch.create_index("ix_shipment_lines_source_payload_id", ["source_payload_id"])
        batch.create_index("ix_shipment_lines_erp_order_no", ["erp_order_no"])
        batch.create_index("ix_shipment_lines_platform_order_no", ["platform_order_no"])
        batch.create_index("ix_shipment_lines_sent_at", ["sent_at"])
        batch.create_index("ix_shipment_lines_logistic_no", ["logistic_no"])
        batch.create_index("ix_shipment_lines_warehouse_code", ["warehouse_code"])

    with op.batch_alter_table("after_sales_lines") as batch:
        batch.add_column(sa.Column("source_system", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_record_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_line_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_payload_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("erp_order_no", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("platform_order_no", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("warehouse_code", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("warehouse_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("status_name", sa.String(length=128), nullable=True))
        batch.create_foreign_key(
            "fk_after_sales_lines_source_payload",
            "integration_api_records",
            ["source_payload_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_after_sales_lines_source_system", ["source_system"])
        batch.create_index("ix_after_sales_lines_source_record_id", ["source_record_id"])
        batch.create_index("ix_after_sales_lines_source_line_id", ["source_line_id"])
        batch.create_index("ix_after_sales_lines_source_payload_id", ["source_payload_id"])
        batch.create_index("ix_after_sales_lines_erp_order_no", ["erp_order_no"])
        batch.create_index("ix_after_sales_lines_platform_order_no", ["platform_order_no"])
        batch.create_index("ix_after_sales_lines_warehouse_code", ["warehouse_code"])
        batch.create_index("ix_after_sales_lines_status", ["status"])

    with op.batch_alter_table("sku_master") as batch:
        batch.add_column(sa.Column("source_system", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_record_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_payload_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_sku_master_source_payload",
            "integration_api_records",
            ["source_payload_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_sku_master_source_system", ["source_system"])
        batch.create_index("ix_sku_master_source_record_id", ["source_record_id"])
        batch.create_index("ix_sku_master_source_payload_id", ["source_payload_id"])

    with op.batch_alter_table("shop_sku_mappings") as batch:
        batch.add_column(sa.Column("source_system", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_record_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_line_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("source_payload_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("writeback_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("last_writeback_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_writeback_message", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_shop_sku_mappings_source_payload",
            "integration_api_records",
            ["source_payload_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_shop_sku_mappings_source_system", ["source_system"])
        batch.create_index("ix_shop_sku_mappings_source_record_id", ["source_record_id"])
        batch.create_index("ix_shop_sku_mappings_source_line_id", ["source_line_id"])
        batch.create_index("ix_shop_sku_mappings_source_payload_id", ["source_payload_id"])
        batch.create_index("ix_shop_sku_mappings_writeback_status", ["writeback_status"])


def downgrade() -> None:
    with op.batch_alter_table("shop_sku_mappings") as batch:
        batch.drop_index("ix_shop_sku_mappings_writeback_status")
        batch.drop_index("ix_shop_sku_mappings_source_payload_id")
        batch.drop_index("ix_shop_sku_mappings_source_line_id")
        batch.drop_index("ix_shop_sku_mappings_source_record_id")
        batch.drop_index("ix_shop_sku_mappings_source_system")
        batch.drop_constraint("fk_shop_sku_mappings_source_payload", type_="foreignkey")
        batch.drop_column("last_writeback_message")
        batch.drop_column("last_writeback_at")
        batch.drop_column("writeback_status")
        batch.drop_column("source_payload_id")
        batch.drop_column("source_line_id")
        batch.drop_column("source_record_id")
        batch.drop_column("source_system")

    with op.batch_alter_table("sku_master") as batch:
        batch.drop_index("ix_sku_master_source_payload_id")
        batch.drop_index("ix_sku_master_source_record_id")
        batch.drop_index("ix_sku_master_source_system")
        batch.drop_constraint("fk_sku_master_source_payload", type_="foreignkey")
        batch.drop_column("source_payload_id")
        batch.drop_column("source_record_id")
        batch.drop_column("source_system")

    with op.batch_alter_table("after_sales_lines") as batch:
        batch.drop_index("ix_after_sales_lines_status")
        batch.drop_index("ix_after_sales_lines_warehouse_code")
        batch.drop_index("ix_after_sales_lines_platform_order_no")
        batch.drop_index("ix_after_sales_lines_erp_order_no")
        batch.drop_index("ix_after_sales_lines_source_payload_id")
        batch.drop_index("ix_after_sales_lines_source_line_id")
        batch.drop_index("ix_after_sales_lines_source_record_id")
        batch.drop_index("ix_after_sales_lines_source_system")
        batch.drop_constraint("fk_after_sales_lines_source_payload", type_="foreignkey")
        batch.drop_column("status_name")
        batch.drop_column("status")
        batch.drop_column("warehouse_name")
        batch.drop_column("warehouse_code")
        batch.drop_column("platform_order_no")
        batch.drop_column("erp_order_no")
        batch.drop_column("source_payload_id")
        batch.drop_column("source_line_id")
        batch.drop_column("source_record_id")
        batch.drop_column("source_system")

    with op.batch_alter_table("shipment_lines") as batch:
        batch.drop_index("ix_shipment_lines_warehouse_code")
        batch.drop_index("ix_shipment_lines_logistic_no")
        batch.drop_index("ix_shipment_lines_sent_at")
        batch.drop_index("ix_shipment_lines_platform_order_no")
        batch.drop_index("ix_shipment_lines_erp_order_no")
        batch.drop_index("ix_shipment_lines_source_payload_id")
        batch.drop_index("ix_shipment_lines_source_line_id")
        batch.drop_index("ix_shipment_lines_source_record_id")
        batch.drop_index("ix_shipment_lines_source_system")
        batch.drop_constraint("fk_shipment_lines_source_payload", type_="foreignkey")
        batch.drop_column("buyer_memo")
        batch.drop_column("seller_memo")
        batch.drop_column("warehouse_name")
        batch.drop_column("warehouse_code")
        batch.drop_column("logistic_name")
        batch.drop_column("logistic_no")
        batch.drop_column("sent_at")
        batch.drop_column("platform_order_no")
        batch.drop_column("erp_order_no")
        batch.drop_column("source_payload_id")
        batch.drop_column("source_line_id")
        batch.drop_column("source_record_id")
        batch.drop_column("source_system")

    op.drop_index("ix_integration_dead_letters_last_attempt_at", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_status", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_error_type", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_external_line_id", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_external_id", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_source_payload_id", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_sync_run_id", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_stage", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_record_type", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_api_method", table_name="integration_dead_letters")
    op.drop_index("ix_integration_dead_letters_source_system", table_name="integration_dead_letters")
    op.drop_table("integration_dead_letters")

    op.drop_index("ix_integration_sync_watermarks_last_advanced_at", table_name="integration_sync_watermarks")
    op.drop_index("ix_integration_sync_watermarks_watermark_value", table_name="integration_sync_watermarks")
    op.drop_index("ix_integration_sync_watermarks_sync_type", table_name="integration_sync_watermarks")
    op.drop_index("ix_integration_sync_watermarks_source_system", table_name="integration_sync_watermarks")
    op.drop_table("integration_sync_watermarks")

    op.drop_index("ix_integration_writeback_jobs_next_run_at", table_name="integration_writeback_jobs")
    op.drop_index("ix_integration_writeback_jobs_status", table_name="integration_writeback_jobs")
    op.drop_index("ix_integration_writeback_jobs_target_id", table_name="integration_writeback_jobs")
    op.drop_index("ix_integration_writeback_jobs_target_type", table_name="integration_writeback_jobs")
    op.drop_index("ix_integration_writeback_jobs_api_method", table_name="integration_writeback_jobs")
    op.drop_index("ix_integration_writeback_jobs_source_system", table_name="integration_writeback_jobs")
    op.drop_table("integration_writeback_jobs")

    op.drop_index("ix_integration_api_call_logs_requested_at", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_context_id", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_biz_sub_code", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_biz_code", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_direction", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_api_method", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_source_system", table_name="integration_api_call_logs")
    op.drop_index("ix_integration_api_call_logs_sync_run_id", table_name="integration_api_call_logs")
    op.drop_table("integration_api_call_logs")

    op.drop_index("ix_integration_api_records_status", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_fetched_at", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_schema_version", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_payload_hash", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_external_line_id", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_external_id", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_record_type", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_api_method", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_source_system", table_name="integration_api_records")
    op.drop_index("ix_integration_api_records_sync_run_id", table_name="integration_api_records")
    op.drop_table("integration_api_records")

    op.drop_index("ix_integration_sync_runs_started_at", table_name="integration_sync_runs")
    op.drop_index("ix_integration_sync_runs_context_id", table_name="integration_sync_runs")
    op.drop_index("ix_integration_sync_runs_status", table_name="integration_sync_runs")
    op.drop_index("ix_integration_sync_runs_direction", table_name="integration_sync_runs")
    op.drop_index("ix_integration_sync_runs_api_method", table_name="integration_sync_runs")
    op.drop_index("ix_integration_sync_runs_sync_type", table_name="integration_sync_runs")
    op.drop_index("ix_integration_sync_runs_source_system", table_name="integration_sync_runs")
    op.drop_table("integration_sync_runs")
