"""shipment_lines: backfill full Jackyun wms.order.query-info.page.v2 fields

Revision ID: 0036_shipment_line_jackyun_full_fields
Revises: 0035_long_tail_cogs_rate_strategy
Create Date: 2026-05-07 12:30:00.000000

Background
----------
Until 0035 the mapper only persisted a small subset of Jackyun fields as
typed columns (everything else lived in ``raw_row_json``). Per ops feedback
2026-05-07, we want the following operational fields as first-class columns
so they can be filtered/displayed in the 发货台账 / 待处理 UIs without
parsing JSON every render:

Header (from Jackyun shipment header):
- order_status_name        VARCHAR(64)   -- orderStatusName
- logistic_type_name       VARCHAR(64)   -- logisticTypeName
- logistic_code            VARCHAR(32)   -- LogisticCode
- wave_no                  VARCHAR(64)   -- waveNo
- customer_name            VARCHAR(255)  -- customerName
- picker                   VARCHAR(64)   -- picker
- packer                   VARCHAR(64)   -- packer
- checker                  VARCHAR(64)   -- checker
- check_started_at         DATETIME      -- checkStartTime
- paid_at                  DATETIME      -- payTime
- ordered_at               DATETIME      -- orderTime
- trade_type               INTEGER       -- tradeType
- trade_type_msg           VARCHAR(64)   -- tradeTypeMsg

Detail (from Jackyun goodsDetail[i]):
- unit_price               NUMERIC(18,6) -- sellPrice
- unit_of_measure          VARCHAR(32)   -- unit
- category_name            VARCHAR(128)  -- cateName
- goods_name               VARCHAR(255)  -- goodsName
- goods_no                 VARCHAR(128)  -- goodsNo
- is_gift                  BOOLEAN       -- isGift (1 -> True)
- actual_qty               NUMERIC(18,6) -- actualCount

All columns are NULLABLE — historical rows will be backfilled from
``raw_row_json`` by ``backend/scripts/backfill_shipment_line_jackyun_fields.py``
which is idempotent and safe to re-run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0036_shipment_line_jackyun_full_fields"
down_revision = "0035_long_tail_cogs_rate_strategy"
branch_labels = None
depends_on = None


# (column_name, type, indexed)
_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, bool]] = [
    # header
    ("order_status_name", sa.String(64), True),
    ("logistic_type_name", sa.String(64), True),
    ("logistic_code", sa.String(32), True),
    ("wave_no", sa.String(64), True),
    ("customer_name", sa.String(255), False),
    ("picker", sa.String(64), False),
    ("packer", sa.String(64), False),
    ("checker", sa.String(64), False),
    ("check_started_at", sa.DateTime(), False),
    ("paid_at", sa.DateTime(), True),
    ("ordered_at", sa.DateTime(), True),
    ("trade_type", sa.Integer(), True),
    ("trade_type_msg", sa.String(64), False),
    # detail
    ("unit_price", sa.Numeric(18, 6), False),
    ("unit_of_measure", sa.String(32), False),
    ("category_name", sa.String(128), True),
    ("goods_name", sa.String(255), False),
    ("goods_no", sa.String(128), True),
    ("is_gift", sa.Boolean(), False),
    ("actual_qty", sa.Numeric(18, 6), False),
]


def upgrade() -> None:
    for name, type_, _indexed in _NEW_COLUMNS:
        op.add_column("shipment_lines", sa.Column(name, type_, nullable=True))
    for name, _type, indexed in _NEW_COLUMNS:
        if indexed:
            op.create_index(
                f"ix_shipment_lines_{name}",
                "shipment_lines",
                [name],
            )


def downgrade() -> None:
    for name, _type, indexed in reversed(_NEW_COLUMNS):
        if indexed:
            op.drop_index(f"ix_shipment_lines_{name}", table_name="shipment_lines")
    for name, _type, _indexed in reversed(_NEW_COLUMNS):
        op.drop_column("shipment_lines", name)
