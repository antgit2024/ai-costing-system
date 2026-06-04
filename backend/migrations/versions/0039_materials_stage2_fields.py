"""materials Stage 2: tax / purchase entity / effective period fields

Revision ID: 0039_materials_stage2_fields
Revises: 0038_cost_rate_master
Create Date: 2026-05-10

Background
----------
Cost Rate Hub v1.3 §4.5 — extend ``materials`` with 6 nullable fields so
material cost can move from "approximate" to "auditable":

- ``purchase_entity_id``  采购法人（v1 用枚举字符串，Phase 2 换 UUID）
- ``tax_included_flag``   含税标志（默认 FALSE，最保守）
- ``tax_rate``            税率 (0.0~1.0, e.g. 0.13)
- ``price_source``        价格来源 ('manual' / 'po_avg_30d' / ...)
- ``effective_from``      生效期（NULL 表示立即生效）
- ``effective_to``        失效期（NULL 表示当前仍有效）

All 6 are nullable so old rows keep working (the only NOT NULL one is
``tax_included_flag`` with ``server_default=False``). BOM 计算 v1 仍直读
``materials.unit_price``，effective_from 取价是 Stage 3 的事，本次不接。

Strategy:
1. Add the 6 columns. Use batch_alter_table for SQLite friendliness.
2. Create a composite lookup index on
   ``(purchase_entity_id, effective_from DESC)`` to speed up
   "按采购主体 + 发货日期取最新有效价" queries that Stage 3 worker
   will use. PostgreSQL gets a partial index filtered to "still
   open-ended" rows (``effective_to IS NULL``) — that's IMMUTABLE,
   unlike ``CURRENT_DATE`` which postgres rejects in index predicates.
   SQLite gets a plain composite index (partial WHERE is harder to
   express portably and SQLite is only used for unit tests).

Tested with both PostgreSQL (production) and SQLite (planner_test
pytest fixtures). Downgrade fully reverses upgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0039_materials_stage2_fields"
down_revision = "0038_cost_rate_master"
branch_labels = None
depends_on = None


_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("purchase_entity_id", sa.String(36), {"nullable": True}),
    ("tax_included_flag", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("tax_rate", sa.Numeric(6, 4), {"nullable": True}),
    ("price_source", sa.String(32), {"nullable": True}),
    ("effective_from", sa.Date(), {"nullable": True}),
    ("effective_to", sa.Date(), {"nullable": True}),
]


_INDEX_NAME = "idx_materials_purchase_entity_effective"


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def upgrade() -> None:
    dialect = _dialect_name()

    with op.batch_alter_table("materials") as batch:
        for name, type_, kwargs in _NEW_COLUMNS:
            batch.add_column(sa.Column(name, type_, **kwargs))

    if dialect == "postgresql":
        # Partial index on "still open-ended" rows. We can NOT use CURRENT_DATE
        # in the predicate (postgres rejects non-IMMUTABLE functions) and we
        # don't want a date hard-coded to today, so the partial WHERE is just
        # `effective_to IS NULL`. Closed-period rows (effective_to set) still
        # exist; lookups on them just don't benefit from this partial index.
        op.create_index(
            _INDEX_NAME,
            "materials",
            ["purchase_entity_id", sa.text("effective_from DESC")],
            postgresql_where=sa.text("effective_to IS NULL"),
        )
    else:
        op.create_index(
            _INDEX_NAME,
            "materials",
            ["purchase_entity_id", "effective_from"],
        )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="materials")

    with op.batch_alter_table("materials") as batch:
        for name, _type, _kwargs in reversed(_NEW_COLUMNS):
            batch.drop_column(name)
