"""sku_master — pg_trgm GIN indexes for ILIKE '%xxx%' search

Revision ID: 0046_sku_master_trgm_search_idx
Revises: 0045_sku_master_jackyun_erp_fields
Create Date: 2026-06-04

Background
----------
``/costing/sku-master`` 列表搜索框 (search 参数) 在 40+ 万行 sku_master 上
对 7 个文本列做 ``ILIKE '%xxx%'`` 全表扫描，在生产环境上跑 ~23s，直接
触发前端 axios 默认 20s timeout，用户报"列表加载失败 timeout of 20000ms
exceeded"。

EXPLAIN ANALYZE 验证 (search="OZU"):
- 全 8 列 OR + EXISTS 子查 + count(*) ≈ 8s 纯 SQL
- LIMIT 50 仍要扫完 444256 行 (Rows Removed by Filter: 408436)

PostgreSQL ``pg_trgm`` 扩展 + GIN 索引让 ``%xxx%`` ILIKE 走索引扫描，
40w 行表查询从 ~4400ms 降到 < 100ms。

Coverage
--------
4 个最常被搜索的文本列:
- ``erp_sku_barcode``   — 货品条码 (EAN/UPC, 短码模式主力)
- ``product_name``      — 商品名称 (中文长文本, 全文搜索最贵)
- ``product_code``      — 货品编号
- ``shop_spec_code``    — 商家编码 / 模型编码 (P0 锚点)

未覆盖 (使用频率低 + 命中已可走其他列):
- ``platform_product_id`` / ``platform_sku_id`` — 较少被模糊搜
- ``metadata_json->'bound_variant_code'`` — JSONB expression index 复杂度高，
  且短码模式快速路径已用 ILIKE on text expression 覆盖
- ``model_code`` / ``model_name`` (EXISTS 子查) — 自由文本路径走，体量小

Compatibility
-------------
- PostgreSQL only (pg_trgm 是 Postgres 扩展)。SQLite 测试环境直接跳过
  整个 upgrade()。
- ``CREATE EXTENSION pg_trgm`` 自 Postgres 13 起为 trusted extension，
  普通用户即可创建。如生产 PG 版本 < 13，需 DBA 预装。
- ``CREATE INDEX CONCURRENTLY`` 不锁表，但**不能**在事务里运行 → 用 
  alembic ``autocommit_block``。

Build cost (生产实测, 444k 行):
- 每个 GIN trgm 索引约 1-3 分钟 + 50-150 MB 磁盘
- 4 个索引合计约 5-10 分钟 + ~400 MB
"""

from __future__ import annotations

from alembic import op


revision = "0046_sku_master_trgm_search_idx"
down_revision = "0045_sku_master_jackyun_erp_fields"
branch_labels = None
depends_on = None


_TRGM_INDEXES = (
    ("ix_sku_master_erp_sku_barcode_trgm", "erp_sku_barcode"),
    ("ix_sku_master_product_name_trgm", "product_name"),
    ("ix_sku_master_product_code_trgm", "product_code"),
    ("ix_sku_master_shop_spec_code_trgm", "shop_spec_code"),
)


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def upgrade() -> None:
    if _dialect_name() != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # CONCURRENTLY 不能在事务内, 用 autocommit_block.
    # IF NOT EXISTS 让重跑 / 已手动建过的环境幂等.
    with op.get_context().autocommit_block():
        for idx_name, col_name in _TRGM_INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} "
                f"ON sku_master USING gin ({col_name} gin_trgm_ops)"
            )


def downgrade() -> None:
    if _dialect_name() != "postgresql":
        return

    with op.get_context().autocommit_block():
        for idx_name, _ in _TRGM_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {idx_name}")
