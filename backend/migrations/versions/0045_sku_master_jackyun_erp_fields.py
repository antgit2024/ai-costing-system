"""sku_master — Jackyun ERP goods master sync (7 L2 physical columns)

Revision ID: 0045_sku_master_jackyun_erp_fields
Revises: 0044_taxonomy_items_name_512
Create Date: 2026-05-16

Background
----------
Blueprint ``DOC/costing/blueprints/jackyun_erp_goods_master_sync_backlog.md``
§3 (JSONB 全收 + L2 物理列升级) + §15 (Phase0 命名对齐) defines 7 L2
physical columns that ``sku_master`` needs to absorb the 43.6 万行 Jackyun
ERP goods master:

5 new columns:
- ``out_sku_code``            — VARCHAR(128), nullable, unique where not null
                                — ERP 外部编码 / 反写匹配键
- ``erp_goods_id``            — VARCHAR(64),  nullable, indexed
                                — ERP 货品 ID (API 反查 + ``maxGoodsId`` 锚点)
- ``erp_sku_id``              — VARCHAR(64),  nullable, indexed
                                — ERP 规格 ID (API ``maxSkuId`` cursor)
- ``is_blocked``              — BOOLEAN,      not null default false, partial index
                                — ERP 是否停用
- ``is_deleted_at_source``    — BOOLEAN,      not null default false, partial index
                                — ERP 是否已删除

2 upgrade columns (metadata_json → physical column with backfill):
- ``shop_spec_code``          — VARCHAR(128), nullable
                                — 商家编码 / 模型编码（从 metadata['shop_spec_code'] 提取）
- ``production_process``      — TEXT,         nullable
                                — 生产工艺（从 metadata['production_process'] 提取）

Backfill: COALESCE(metadata->>'shop_spec_code', NULL) → new column;
metadata key is NOT removed in this migration (Stage D in blueprint will
sunset the metadata fallback after frontend switches to physical column).
This preserves rollback safety — downgrade just drops columns, metadata
is still intact.

Compatibility: works on both Postgres (production) and SQLite (tests).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0045_sku_master_jackyun_erp_fields"
down_revision = "0044_taxonomy_items_name_512"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def upgrade() -> None:
    dialect = _dialect_name()

    # ---- 1. Add 5 new + 2 upgrade columns ----
    with op.batch_alter_table("sku_master") as batch_op:
        batch_op.add_column(sa.Column("out_sku_code", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("erp_goods_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("erp_sku_id", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_blocked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_deleted_at_source",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(sa.Column("shop_spec_code", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("production_process", sa.Text(), nullable=True))

    # ---- 2. Backfill 2 upgrade columns from metadata_json ----
    # Both Postgres and SQLite support JSON_EXTRACT for the read path. We use
    # raw SQL with dialect-specific operators to avoid SQLAlchemy quirks.
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE sku_master
               SET shop_spec_code = NULLIF(TRIM(metadata::jsonb->>'shop_spec_code'), '')
             WHERE shop_spec_code IS NULL
               AND metadata::jsonb->>'shop_spec_code' IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE sku_master
               SET production_process = NULLIF(TRIM(metadata::jsonb->>'production_process'), '')
             WHERE production_process IS NULL
               AND metadata::jsonb->>'production_process' IS NOT NULL
            """
        )
    else:
        op.execute(
            """
            UPDATE sku_master
               SET shop_spec_code = NULLIF(TRIM(json_extract(metadata, '$.shop_spec_code')), '')
             WHERE shop_spec_code IS NULL
               AND json_extract(metadata, '$.shop_spec_code') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE sku_master
               SET production_process = NULLIF(TRIM(json_extract(metadata, '$.production_process')), '')
             WHERE production_process IS NULL
               AND json_extract(metadata, '$.production_process') IS NOT NULL
            """
        )

    # ---- 3. Create indexes (partial where supported) ----
    # 3a. unique partial on out_sku_code (Postgres-style WHERE clause)
    if dialect == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX ux_sku_master_out_sku_code
                ON sku_master(out_sku_code)
             WHERE out_sku_code IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX ix_sku_master_blocked_active
                ON sku_master(is_blocked)
             WHERE is_blocked = true
            """
        )
        op.execute(
            """
            CREATE INDEX ix_sku_master_deleted_active
                ON sku_master(is_deleted_at_source)
             WHERE is_deleted_at_source = true
            """
        )
    else:
        # SQLite also supports partial indexes (>= 3.8.0). Same SQL works.
        op.execute(
            """
            CREATE UNIQUE INDEX ux_sku_master_out_sku_code
                ON sku_master(out_sku_code)
             WHERE out_sku_code IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX ix_sku_master_blocked_active
                ON sku_master(is_blocked)
             WHERE is_blocked = 1
            """
        )
        op.execute(
            """
            CREATE INDEX ix_sku_master_deleted_active
                ON sku_master(is_deleted_at_source)
             WHERE is_deleted_at_source = 1
            """
        )

    # 3b. plain indexes on ERP id columns
    op.create_index(
        "ix_sku_master_erp_goods_id",
        "sku_master",
        ["erp_goods_id"],
    )
    op.create_index(
        "ix_sku_master_erp_sku_id",
        "sku_master",
        ["erp_sku_id"],
    )


def downgrade() -> None:
    # 1. Drop indexes
    op.drop_index("ix_sku_master_erp_sku_id", table_name="sku_master")
    op.drop_index("ix_sku_master_erp_goods_id", table_name="sku_master")
    op.execute("DROP INDEX IF EXISTS ix_sku_master_deleted_active")
    op.execute("DROP INDEX IF EXISTS ix_sku_master_blocked_active")
    op.execute("DROP INDEX IF EXISTS ux_sku_master_out_sku_code")

    # 2. Drop columns (metadata fallback for shop_spec_code/production_process
    #    is preserved — old read paths via metadata_json still work)
    with op.batch_alter_table("sku_master") as batch_op:
        batch_op.drop_column("production_process")
        batch_op.drop_column("shop_spec_code")
        batch_op.drop_column("is_deleted_at_source")
        batch_op.drop_column("is_blocked")
        batch_op.drop_column("erp_sku_id")
        batch_op.drop_column("erp_goods_id")
        batch_op.drop_column("out_sku_code")
