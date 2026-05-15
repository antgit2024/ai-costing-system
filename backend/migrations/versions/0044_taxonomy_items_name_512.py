"""taxonomy_items.name varchar(128) -> varchar(512)

Revision ID: 0044_taxonomy_items_name_512
Revises: 0043_cost_allocation_line
Create Date: 2026-05-15

Background
----------
report_snapshot_service.snapshot_key 把 dashboard 查询参数（含 ISO timestamp
+ group_by + view + start/end）拼成 name 存入 taxonomy_items（domain='report_snapshot'），
typical key 例如:
  insights.after_sales_dashboard?end=2026-05-15T01:28:01.240000+00:00&group_by=week&start=2026-05-15T01:28:01.240000+00:00&view=ops
长度 ~135 字符，超过原 varchar(128) → POST /reports/insights/after-sales-dashboard/refresh
INSERT 直接 500 (StringDataRightTruncation)。

修复方式：把 taxonomy_items.name 升到 varchar(512)（Postgres ALTER COLUMN TYPE
是无损 + 即时操作，所有现有数据原样保留）。其他 domain (e.g. ops_assumption_scheme,
material_category) 都是短名（≤32 字符），完全不受影响。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0044_taxonomy_items_name_512"
down_revision = "0043_cost_allocation_line"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("taxonomy_items") as batch_op:
        batch_op.alter_column(
            "name",
            existing_type=sa.String(128),
            type_=sa.String(512),
            existing_nullable=False,
        )


def downgrade() -> None:
    # 回滚有数据风险（>128 字符的 report_snapshot key 行会被截断 / 拒绝），
    # 实际不期望回滚——保留对称定义但建议先清理 domain='report_snapshot' 长行。
    with op.batch_alter_table("taxonomy_items") as batch_op:
        batch_op.alter_column(
            "name",
            existing_type=sa.String(512),
            type_=sa.String(128),
            existing_nullable=False,
        )
