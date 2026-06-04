"""Schema-level checks for the integration layer.

Uses the ORM metadata reflected via ``create_all()`` to confirm that the new
generic integration tables and per-business-table provenance columns are
registered correctly. This avoids depending on SQLite-incompatible legacy
migrations (e.g. 0031 ``ALTER COLUMN ... TYPE``) and keeps the test fast.
"""

from __future__ import annotations

from sqlalchemy import inspect


def test_generic_integration_tables_registered(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for name in (
        "integration_sync_runs",
        "integration_api_records",
        "integration_api_call_logs",
        "integration_writeback_jobs",
    ):
        assert name in tables, f"missing integration table: {name}"


def test_business_tables_have_source_provenance_columns(engine):
    inspector = inspect(engine)

    shipment_cols = {c["name"] for c in inspector.get_columns("shipment_lines")}
    for col in (
        "source_system",
        "source_record_id",
        "source_line_id",
        "source_payload_id",
        "erp_order_no",
        "platform_order_no",
        "sent_at",
        "logistic_no",
        "logistic_name",
        "warehouse_code",
        "warehouse_name",
        "seller_memo",
        "buyer_memo",
    ):
        assert col in shipment_cols, f"shipment_lines missing {col}"

    after_sales_cols = {c["name"] for c in inspector.get_columns("after_sales_lines")}
    for col in (
        "source_system",
        "source_record_id",
        "source_line_id",
        "source_payload_id",
        "erp_order_no",
        "platform_order_no",
        "warehouse_code",
        "warehouse_name",
        "status",
        "status_name",
    ):
        assert col in after_sales_cols, f"after_sales_lines missing {col}"

    sku_cols = {c["name"] for c in inspector.get_columns("sku_master")}
    for col in ("source_system", "source_record_id", "source_payload_id"):
        assert col in sku_cols, f"sku_master missing {col}"

    shop_sku_cols = {c["name"] for c in inspector.get_columns("shop_sku_mappings")}
    for col in (
        "source_system",
        "source_record_id",
        "source_line_id",
        "source_payload_id",
        "writeback_status",
        "last_writeback_at",
        "last_writeback_message",
    ):
        assert col in shop_sku_cols, f"shop_sku_mappings missing {col}"


def test_jackyun_client_registered_in_registry():
    from src.integrations.base.registry import available_clients

    assert "jackyun" in available_clients()
